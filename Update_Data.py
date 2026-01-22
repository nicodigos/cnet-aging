import sys
import asyncio

# Fix Windows event loop issue
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
from pipeline import run_pipeline

st.title("Update Data")

if st.button("Export & Upload"):
    with st.spinner("Exporting and uploading..."):
        df = run_pipeline()

    st.success(f"Uploaded {len(df)} rows")
