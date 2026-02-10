# invoices_export/ui/filters.py
from dataclasses import dataclass
from datetime import date
import re

import pandas as pd
import streamlit as st


@dataclass
class Filters:
    issue_from: date
    issue_to: date
    aging_min: int
    aging_max: int
    invoice_type: str
    internal_external: list[str]  # effective selection used for filtering
    buyer_selected: list[str]
    vendor_selected: list[str]


_COMPANY_NUM_RE = re.compile(r"^\s*(\d{4}-\d{4}|\d{7,10})\b")


def extract_company_number(name: str) -> str | None:
    """
    Extract leading company number from strings like:
      - "12433087 Canada Inc"
      - "9359-6633 Quebec Inc"
      - "2501308 Ontario Inc"
    Returns normalized company number (e.g., "12433087", "9359-6633") or None.
    """
    if not isinstance(name, str) or not name.strip():
        return None
    m = _COMPANY_NUM_RE.match(name)
    return m.group(1) if m else None


def _build_vendor_numbers_universe(df: pd.DataFrame) -> set[str]:
    """
    Build a set of vendor company numbers from the FULL dataset (unfiltered),
    so future buyer names matching a vendor number are classified as Internal.
    """
    vendor_numbers_all: set[str] = set()
    if "vendor_company_name" not in df.columns:
        return vendor_numbers_all

    for v in df["vendor_company_name"].dropna().astype(str):
        num = extract_company_number(v)
        if num:
            vendor_numbers_all.add(num)
    return vendor_numbers_all


def render_filters_sidebar(
    df: pd.DataFrame,
    min_issue: date,
    max_issue: date,
    min_aging: int,
    max_aging: int,
):
    # Stable state keys
    st.session_state.setdefault("issue_from", min_issue)
    st.session_state.setdefault("issue_to", max_issue)
    st.session_state.setdefault("aging_range", (int(min_aging), int(max_aging)))
    st.session_state.setdefault("invoice_type", "All")
    st.session_state.setdefault("internal_external", ["External"])  # default checked
    st.session_state.setdefault("buyer_selected", [])
    st.session_state.setdefault("vendor_selected", [])

    # Clamp aging_range in case min/max bounds changed between reruns
    lo, hi = st.session_state["aging_range"]
    lo = max(int(min_aging), int(lo))
    hi = min(int(max_aging), int(hi))
    if lo > hi:
        lo, hi = int(min_aging), int(max_aging)
    st.session_state["aging_range"] = (lo, hi)

    # Universe of vendor company numbers from FULL df (unfiltered)
    vendor_numbers_all = _build_vendor_numbers_universe(df)

    with st.sidebar:
        st.header("Filters")

        col1, col2 = st.columns(2)
        with col1:
            issue_from = st.date_input("Issue date from", key="issue_from")
        with col2:
            issue_to = st.date_input("Issue date to", key="issue_to")

        if issue_from > issue_to:
            issue_from, issue_to = issue_to, issue_from
            st.session_state["issue_from"] = issue_from
            st.session_state["issue_to"] = issue_to

        aging_min_val, aging_max_val = st.slider(
            "Aging (days_since_issue)",
            min_value=int(min_aging),
            max_value=int(max_aging),
            step=1,
            key="aging_range",
        )

        invoice_type = st.selectbox(
            "Invoice Type",
            ["All", "Regular", "One Shot"],
            index=["All", "Regular", "One Shot"].index(st.session_state["invoice_type"]),
            key="invoice_type",
        )

        # Internal/External multiselect:
        # - default: both selected (via setdefault above)
        # - if user clears all: treat as "no filter" WITHOUT writing to session_state
        internal_external_ui = st.multiselect(
            "Buyer Type",
            options=["Internal", "External"],
            key="internal_external",
        )
        internal_external_effective = internal_external_ui or ["Internal", "External"]

        # Build base df for dropdown options (matches apply_filters semantics)
        df_base = df.copy()

        df_base = df_base[df_base["issue_date"].notna()]
        df_base = df_base[(df_base["issue_date"] >= issue_from) & (df_base["issue_date"] <= issue_to)]

        df_base = df_base[df_base["days_since_issue"].notna()]
        df_base = df_base[df_base["days_since_issue"] >= int(aging_min_val)]
        df_base = df_base[df_base["days_since_issue"] <= int(aging_max_val)]

        if invoice_type != "All":
            df_base = df_base[df_base["invoice_type"] == invoice_type]

        df_base = df_base[df_base["payment_status_norm"] != "paid"]

        # Apply internal/external semantics to df_base using:
        # Internal iff buyer company-number ∈ vendor_numbers_all
        if "buyer_company_name" in df_base.columns and vendor_numbers_all:
            buyer_nums = df_base["buyer_company_name"].astype(str).map(extract_company_number)
            is_internal = buyer_nums.isin(vendor_numbers_all)
        else:
            is_internal = pd.Series(False, index=df_base.index)

        wanted_internal = "Internal" in internal_external_effective
        wanted_external = "External" in internal_external_effective

        if wanted_internal and not wanted_external:
            df_base = df_base[is_internal]
        elif wanted_external and not wanted_internal:
            df_base = df_base[~is_internal]
        # else: both (or none in UI => both effective): no filter

        buyer_current = list(st.session_state["buyer_selected"])
        vendor_current = list(st.session_state["vendor_selected"])

        # Cascading options
        if vendor_current:
            buyers_series = df_base.loc[df_base["vendor_company_name"].isin(vendor_current), "buyer_company_name"]
        else:
            buyers_series = df_base["buyer_company_name"]
        buyers = sorted(pd.Series(buyers_series.dropna().unique()).tolist())

        if buyer_current:
            vendors_series = df_base.loc[df_base["buyer_company_name"].isin(buyer_current), "vendor_company_name"]
        else:
            vendors_series = df_base["vendor_company_name"]
        vendors = sorted(pd.Series(vendors_series.dropna().unique()).tolist())

        # Sanitize selections so they remain valid
        buyer_sanitized = [b for b in buyer_current if b in buyers]
        vendor_sanitized = [v for v in vendor_current if v in vendors]

        changed = False
        if buyer_sanitized != buyer_current:
            st.session_state["buyer_selected"] = buyer_sanitized
            changed = True
        if vendor_sanitized != vendor_current:
            st.session_state["vendor_selected"] = vendor_sanitized
            changed = True
        if changed:
            st.rerun()

        buyer_selected = st.multiselect(
            "Client (Buyer) (leave empty = all)",
            options=buyers,
            key="buyer_selected",
        )

        vendor_selected = st.multiselect(
            "Vendor (leave empty = all)",
            options=vendors,
            key="vendor_selected",
        )

        refresh = st.button("Refresh", key="btn_refresh")

        st.divider()
        st.subheader("Reports")

        generate_report_full = st.button(
            "📄 Generate full report (HTML)",
            use_container_width=True,
            key="btn_generate_report_full",
        )
        generate_report_partitioned = st.button(
            "🗂️ Generate partitioned reports (ZIP)",
            use_container_width=True,
            key="btn_generate_report_partitioned",
        )

        st.download_button(
            label="⬇️ Download full report",
            data=st.session_state.get("html_report_bytes", b"") or b"",
            file_name=st.session_state.get("html_report_name", "accounts_receivable_report.html"),
            mime="text/html",
            disabled=not bool(st.session_state.get("html_report_bytes")),
            use_container_width=True,
            key="dl_html_report",
        )

        st.download_button(
            label="⬇️ Download partitioned reports (ZIP)",
            data=st.session_state.get("reports_zip_bytes", b"") or b"",
            file_name=st.session_state.get("reports_zip_name", "reports_by_vendor_buyer.zip"),
            mime="application/zip",
            disabled=not bool(st.session_state.get("reports_zip_bytes")),
            use_container_width=True,
            key="dl_reports_zip",
        )

        generate_invoices_zip = st.button(
            "📦 Generate invoices ZIP",
            use_container_width=True,
            key="btn_generate_invoices_zip",
        )

        st.download_button(
            label="⬇️ Download invoices ZIP",
            data=st.session_state.get("invoices_zip_bytes", b"") or b"",
            file_name=st.session_state.get("invoices_zip_name", "invoices.zip"),
            mime="application/zip",
            disabled=not bool(st.session_state.get("invoices_zip_bytes")),
            use_container_width=True,
            key="dl_invoices_zip",
        )

    f = Filters(
        issue_from=issue_from,
        issue_to=issue_to,
        aging_min=int(aging_min_val),
        aging_max=int(aging_max_val),
        invoice_type=invoice_type,
        internal_external=internal_external_effective,
        buyer_selected=buyer_selected,
        vendor_selected=vendor_selected,
    )

    return f, refresh, generate_report_full, generate_report_partitioned, generate_invoices_zip


def apply_filters(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    df_f = df.copy()

    df_f = df_f[df_f["issue_date"].notna()]
    df_f = df_f[(df_f["issue_date"] >= f.issue_from) & (df_f["issue_date"] <= f.issue_to)]

    df_f = df_f[df_f["days_since_issue"].notna()]
    df_f = df_f[df_f["days_since_issue"] >= f.aging_min]
    df_f = df_f[df_f["days_since_issue"] <= f.aging_max]

    if f.invoice_type != "All":
        df_f = df_f[df_f["invoice_type"] == f.invoice_type]

    if f.buyer_selected:
        df_f = df_f[df_f["buyer_company_name"].isin(f.buyer_selected)]

    if f.vendor_selected:
        df_f = df_f[df_f["vendor_company_name"].isin(f.vendor_selected)]

    df_f = df_f[df_f["payment_status_norm"] != "paid"].copy()

    # Internal/external filter using buyer company-number ∈ (all vendor company-numbers)
    vendor_numbers_all = _build_vendor_numbers_universe(df)

    if "buyer_company_name" in df_f.columns and vendor_numbers_all:
        buyer_nums = df_f["buyer_company_name"].astype(str).map(extract_company_number)
        is_internal = buyer_nums.isin(vendor_numbers_all)
    else:
        is_internal = pd.Series(False, index=df_f.index)

    wanted_internal = "Internal" in f.internal_external
    wanted_external = "External" in f.internal_external

    if wanted_internal and not wanted_external:
        df_f = df_f[is_internal].copy()
    elif wanted_external and not wanted_internal:
        df_f = df_f[~is_internal].copy()
    # else: both (or none in UI => both effective): no filter

    return df_f
