from __future__ import annotations

from pathlib import Path
import streamlit as st
from reporting.report import ClientReportGenerator


def init_reports_state():
    if "report_pdf_bytes" not in st.session_state:
        st.session_state.report_pdf_bytes = None
    if "report_pdf_name" not in st.session_state:
        st.session_state.report_pdf_name = "accounts_receivable_report.pdf"


def render_reports_download_buttons_sidebar():
    # Always visible; enabled only when PDF exists
    st.download_button(
        label="⬇️ Download Report",
        data=st.session_state.report_pdf_bytes or b"",
        file_name=st.session_state.report_pdf_name,
        mime="application/pdf",
        disabled=st.session_state.report_pdf_bytes is None,
        use_container_width=True,
    )

    # Always visible; DISABLED + disconnected for now
    st.download_button(
        label="⬇️ Download Invoices (coming soon)",
        data=b"",
        file_name="invoices.zip",
        mime="application/zip",
        disabled=True,
        use_container_width=True,
    )



def generate_html_report_to_session(df_f, report_generator: ClientReportGenerator):
    hide_cols = [
        "creation_date",
        "payment_status",
        "payment_status_norm",
    ]

    df_report = df_f.copy()

    with st.spinner("Generating HTML report..."):
        html_path = report_generator.generate_html(
            df=df_report,
            client_col="buyer_company_name",
            amount_col="total_amount_with_taxes",
            output_name="accounts_receivable_report.html",
            hide_columns=hide_cols,
        )

    st.session_state["html_report_bytes"] = html_path.read_bytes()
    st.session_state["html_report_name"] = html_path.name