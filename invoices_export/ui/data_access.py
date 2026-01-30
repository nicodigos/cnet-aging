import os
from dotenv import load_dotenv
import pandas as pd
from supabase import create_client
import streamlit as st

load_dotenv()

VIEW_NAME = os.getenv("SUPABASE_INVOICES_VIEW", "invoices_v")
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not URL or not KEY:
    raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(URL, KEY)


@st.cache_data(ttl=300)
def fetch_all_rows(page_size: int = 1000, max_pages: int = 5000) -> pd.DataFrame:
    all_rows = []
    offset = 0

    for _ in range(max_pages):
        res = (
            supabase.table(VIEW_NAME)
            .select(
                "invoice_id,issue_date,creation_date,invoice_type,"
                "buyer_company_name,vendor_company_name,payment_status,"
                "days_since_issue,past_due,total_amount_with_taxes,work_description"
            )
            .order("invoice_id", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        rows = res.data or []
        if not rows:
            break

        all_rows.extend(rows)

        if len(rows) < page_size:
            break

        offset += page_size

    return pd.DataFrame(all_rows)
