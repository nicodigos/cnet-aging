# invoices_export/ui/filters.py
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st


@dataclass
class Filters:
    issue_from: date
    issue_to: date
    aging_min: int
    aging_max: int
    invoice_type: str
    buyer_selected: list[str]
    vendor_selected: list[str]


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
    st.session_state.setdefault("buyer_selected", [])
    st.session_state.setdefault("vendor_selected", [])

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
            value=st.session_state["aging_range"],
            step=1,
            key="aging_range",
        )

        invoice_type = st.selectbox(
            "Invoice Type",
            ["All", "Regular", "One Shot"],
            index=["All", "Regular", "One Shot"].index(st.session_state["invoice_type"]),
            key="invoice_type",
        )

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

        # Two report generation buttons
        generate_report_full = st.button("📄 Generate full report (HTML)", use_container_width=True, key="btn_generate_report_full")
        generate_report_partitioned = st.button("🗂️ Generate partitioned reports (ZIP)", use_container_width=True, key="btn_generate_report_partitioned")

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
    return df_f
