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
from supabase import create_client

from pipeline.sync import run_pipeline, upload_invoice_creation_overrides
from invoices_export.ui.data_access import fetch_invoice_creation_overrides


# -----------------------------
# Supabase connection (for last-sync info)
# -----------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # must be service role
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "invoices_raw")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# -----------------------------
# Helpers (keep original last-sync behavior)
# -----------------------------
def format_to_local_human(ts: str) -> str:
    """
    Convert UTC timestamptz -> local time
    Return: January 30, 2026 at 9:52 AM
    """
    if not ts:
        return None

    local_zone = tz.tzlocal()
    dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    dt_local = dt_utc.astimezone(local_zone)
    return dt_local.strftime("%B %d, %Y at %I:%M %p")


def get_last_sync_time():
    res = (
        supabase
        .table(SUPABASE_TABLE)
        .select("created_at")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if res.data:
        return format_to_local_human(res.data[0]["created_at"])
    return None


# -----------------------------
# UI
# -----------------------------
st.title("Update Data")

# =========================================================
# SECTION A — INVOICES UPDATE (original UX: last sync + button)
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
# SECTION B — INVOICE CREATION OVERRIDES (upload + table below)
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
            # first sheet by default
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
