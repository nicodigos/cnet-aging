from pathlib import Path
import streamlit as st
from downloads.cnet_invoice_zip import build_past_due_invoices_zip_by_vendor_buyer
from reporting.report import ClientReportGenerator

from invoices_export.ui.data_access import fetch_all_rows
from invoices_export.ui.normalize import normalize_invoices, safe_issue_bounds, safe_aging_bounds
from invoices_export.ui.filters import render_filters_sidebar, apply_filters
from invoices_export.ui.reports import (
    init_reports_state,
    generate_html_report_to_session,
)
from invoices_export.ui.metrics import render_metrics
from invoices_export.ui.charts import render_past_due_bins
from invoices_export.ui.table import render_past_due_table

st.set_page_config(page_title="Aging", layout="wide")
st.title("Aging")

# Report generator (HTML/PDF)
REPORT_OUTPUT_DIR = Path("reports")
REPORT_OUTPUT_DIR.mkdir(exist_ok=True)

report_generator = ClientReportGenerator(
    template_dir="reporting/templates",
    output_dir=str(REPORT_OUTPUT_DIR),
)

init_reports_state()

# Load
df = fetch_all_rows()
if df.empty:
    st.info("No rows found.")
    st.stop()

# Normalize
df = normalize_invoices(df)

# Bounds
min_issue, max_issue = safe_issue_bounds(df)
min_aging, max_aging = safe_aging_bounds(df)

# Sidebar
f, refresh, generate_report, generate_invoices_zip = render_filters_sidebar(
    df, min_issue, max_issue, min_aging, max_aging
)


if refresh:
    st.cache_data.clear()

# Apply filters
df_f = apply_filters(df, f)
if df_f.empty:
    st.info("No rows found with current filters (after removing Paid).")
    st.stop()


# Optional: keep HTML generation if you still want it
if generate_report:
    generate_html_report_to_session(df_f, report_generator)
    st.rerun()
    
if generate_invoices_zip:
    # df_f ya es not paid; solo past due:
    df_zip = df_f[df_f["past_due"]].copy()

    zip_bytes, zip_name = build_past_due_invoices_zip_by_vendor_buyer(df_zip)

    st.session_state["invoices_zip_bytes"] = zip_bytes
    st.session_state["invoices_zip_name"] = zip_name
    st.rerun()

# Dashboard stays same
render_metrics(df_f)

past_due_df = df_f[df_f["past_due"]]
render_past_due_bins(past_due_df)

render_past_due_table(df_f)
