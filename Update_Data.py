import sys
import asyncio
import os
from datetime import datetime
from dateutil import tz

# Fix Windows event loop issue
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

from pipeline import run_pipeline


# -----------------------------
# Supabase connection
# -----------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # must be service role
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "invoices_raw")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# -----------------------------
# Helpers
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

last_sync = get_last_sync_time()
if last_sync:
    st.info(f"Last synchronization: {last_sync}")
else:
    st.info("Last synchronization: No data yet")

if st.button("Export & Upload"):
    with st.spinner("Exporting and uploading..."):
        df = run_pipeline()

    st.success(f"Uploaded {len(df)} rows")

    last_sync = get_last_sync_time()
    if last_sync:
        st.info(f"Last synchronization: {last_sync}")
