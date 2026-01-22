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
    buyers = sorted(df["buyer_company_name"].unique().tolist())
    vendors = sorted(df["vendor_company_name"].unique().tolist())

    with st.sidebar:
        st.header("Filters")

        col1, col2 = st.columns(2)
        with col1:
            issue_from = st.date_input("Issue date from", value=min_issue)
        with col2:
            issue_to = st.date_input("Issue date to", value=max_issue)

        aging_min, aging_max = st.slider(
            "Aging (days_since_issue)",
            min_value=int(min_aging),
            max_value=int(max_aging),
            value=(int(min_aging), int(max_aging)),
            step=1,
        )

        invoice_type = st.selectbox("Invoice Type", ["All", "Regular", "One Shot"], index=0)

        buyer_selected = st.multiselect(
            "Client (Buyer) (leave empty = all)",
            options=buyers,
            default=[],
        )

        vendor_selected = st.multiselect(
            "Vendor (leave empty = all)",
            options=vendors,
            default=[],
        )

        refresh = st.button("Refresh")

        st.divider()
        st.subheader("Reports")

        generate_report = st.button("📄 Generate report", use_container_width=True)

        st.download_button(
            label="⬇️ Download report",
            data=st.session_state.get("html_report_bytes", b""),
            file_name=st.session_state.get("html_report_name", "accounts_receivable_report.html"),
            mime="text/html",
            disabled="html_report_bytes" not in st.session_state,
            use_container_width=True,
            key="dl_html_report",
        )

        # ✅ NEW: invoices zip controls (invoices module is called from the page)
        generate_invoices_zip = st.button("📦 Generate invoices ZIP", use_container_width=True)

        st.download_button(
            label="⬇️ Download invoices ZIP",
            data=st.session_state.get("invoices_zip_bytes", b""),
            file_name=st.session_state.get("invoices_zip_name", "invoices.zip"),
            mime="application/zip",
            disabled="invoices_zip_bytes" not in st.session_state,
            use_container_width=True,
            key="dl_invoices_zip",
        )

    # keep original behavior
    if issue_from > issue_to:
        issue_from, issue_to = issue_to, issue_from

    f = Filters(
        issue_from=issue_from,
        issue_to=issue_to,
        aging_min=int(aging_min),
        aging_max=int(aging_max),
        invoice_type=invoice_type,
        buyer_selected=buyer_selected,
        vendor_selected=vendor_selected,
    )

    return f, refresh, generate_report, generate_invoices_zip


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

    # REMOVE paid (keep everything else)
    df_f = df_f[df_f["payment_status_norm"] != "paid"].copy()

    return df_f
