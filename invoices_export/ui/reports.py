# invoices_export/ui/reports.py
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import streamlit as st

from reporting.report import ClientReportGenerator


def init_reports_state():
    # Full report (single HTML)
    st.session_state.setdefault("html_report_bytes", None)
    st.session_state.setdefault("html_report_name", "accounts_receivable_report.html")

    # Partitioned report ZIP
    st.session_state.setdefault("reports_zip_bytes", None)
    st.session_state.setdefault("reports_zip_name", "reports_by_vendor_buyer.zip")


def _zip_folder_bytes(root_dir: Path) -> bytes:
    """
    Zip an on-disk folder into bytes. Paths inside zip are relative to root_dir.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in root_dir.rglob("*"):
            if p.is_file():
                arc = p.relative_to(root_dir).as_posix()
                z.write(p, arcname=arc)
    buf.seek(0)
    return buf.read()


def generate_full_html_report_to_session(df_f, report_generator: ClientReportGenerator):
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
            template_name="report.html",
        )

    st.session_state["html_report_bytes"] = html_path.read_bytes()
    st.session_state["html_report_name"] = html_path.name


def generate_partitioned_reports_zip_to_session(df_f, report_generator: ClientReportGenerator):
    """
    Generates vendor/buyer partitioned HTML files to a temp folder (inside report_generator.output_dir),
    then zips that folder and stores bytes in session for download.
    """
    hide_cols = [
        "creation_date",
        "payment_status",
        "payment_status_norm",
    ]

    df_report = df_f.copy()

    with st.spinner("Generating partitioned reports ZIP..."):
        root_dir = report_generator.generate_html_partitioned(
            df=df_report,
            client_col="buyer_company_name",
            amount_col="total_amount_with_taxes",
            output_root_name="reports_by_vendor_buyer",
            report_filename="report.html",
            hide_columns=hide_cols,
            include_index_html=True,
            template_name="report_partition.html",
        )

        zip_bytes = _zip_folder_bytes(root_dir)

    st.session_state["reports_zip_bytes"] = zip_bytes
    st.session_state["reports_zip_name"] = f"{root_dir.name}.zip"
