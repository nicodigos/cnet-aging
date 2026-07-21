# Update_Data.py

import sys
import asyncio
import os
from datetime import datetime
from dateutil import tz

# Fix Windows event loop issue
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from pipeline.sync import run_pipeline, upload_invoice_creation_overrides
from pipeline.database import connect
from invoices_export.ui.data_access import fetch_invoice_creation_overrides
from invoices_export.ui.auth import require_authentication


load_dotenv()
require_authentication()


# -----------------------------
# Helpers
# -----------------------------
def format_utc_to_toronto(ts: str) -> str:
    """
    Convert UTC timestamptz (from DB) -> America/Toronto
    ONLY used for displaying 'Last synchronization'.
    """
    if not ts:
        return None

    toronto_zone = tz.gettz("America/Toronto")
    dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    dt_toronto = dt_utc.astimezone(toronto_zone)

    return dt_toronto.strftime("%B %d, %Y at %I:%M %p")


def get_last_sync_time():
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select max(created_at) from public.invoices_raw")
            value = cursor.fetchone()[0]
    if value:
        return format_utc_to_toronto(value.isoformat())
    return None


# -----------------------------
# UI
# -----------------------------
st.title("Update Data")

# =========================================================
# SECTION A — INVOICES UPDATE (original UX)
# =========================================================
st.header("Invoices Update")

last_sync = get_last_sync_time()
if last_sync:
    st.info(f"Last synchronization: {last_sync}")
else:
    st.info("Last synchronization: No data yet")

if st.button("Export & Upload", type="primary"):
    try:
        with st.spinner("Exporting and uploading..."):
            df = run_pipeline()

        st.success(f"Uploaded {len(df):,} rows")

        last_sync = get_last_sync_time()
        if last_sync:
            st.info(f"Last synchronization: {last_sync}")
    except Exception as e:
        st.error(f"Upload failed: {e}")

st.divider()

# =========================================================
# SECTION B — INVOICE CREATION OVERRIDES
# =========================================================
st.header("Invoice Creation Overrides")

st.caption(
    "Order-based input:\n"
    "- Column 1: invoice_id (int)\n"
    "- Column 2: new_creation_date (YYYY-MM-DD)\n"
    "Column names don’t matter.\n"
    "Accepted files: CSV, XLSX (first sheet is used by default)."
)

uploaded = st.file_uploader(
    "Upload CSV or Excel (XLSX)",
    type=["csv", "xlsx"],
    key="overrides_uploader",
)

if uploaded is not None:
    try:
        if uploaded.name.lower().endswith(".csv"):
            df_in = pd.read_csv(uploaded)
        else:
            df_in = pd.read_excel(uploaded, sheet_name=0)

        st.subheader("Upload preview")
        st.dataframe(df_in.head(50), use_container_width=True, height=320)

        if st.button("Upsert overrides", type="primary"):
            with st.spinner("Upserting overrides..."):
                n = upload_invoice_creation_overrides(df_in)
            st.success(f"Upserted {n:,} row(s) into invoice_creation_override.")
            st.cache_data.clear()
    except Exception as e:
        st.error(f"Override upload failed: {e}")

st.subheader("Current table: invoice_creation_override")
if st.button("Refresh overrides table"):
    st.cache_data.clear()

try:
    df_tbl = fetch_invoice_creation_overrides()
    st.write(f"Rows: {len(df_tbl):,}")
    st.dataframe(df_tbl, use_container_width=True, height=620)
except Exception as e:
    st.error(f"Fetch failed: {e}")
