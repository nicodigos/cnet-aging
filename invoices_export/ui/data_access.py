import os
from dotenv import load_dotenv
import pandas as pd
from supabase import create_client
import streamlit as st

load_dotenv()

VIEW_NAME = os.getenv("SUPABASE_INVOICES_VIEW", "invoices_v")
RAW_TABLE = os.getenv("SUPABASE_TABLE", "invoices_raw")
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

    df = pd.DataFrame(all_rows)
    if df.empty:
        return df

    try:
        enrichment_rows = []
        offset = 0
        for _ in range(max_pages):
            res = (
                supabase.table(RAW_TABLE)
                .select(
                    "invoice_id,partial_payments_amount,"
                    "partial_payments_count,open_amount_with_taxes"
                )
                .order("invoice_id", desc=False)
                .range(offset, offset + page_size - 1)
                .execute()
            )

            rows = res.data or []
            if not rows:
                break

            enrichment_rows.extend(rows)
            if len(rows) < page_size:
                break

            offset += page_size

        enrich = pd.DataFrame(enrichment_rows)
        if not enrich.empty:
            df = df.merge(enrich, on="invoice_id", how="left")
    except Exception:
        df["partial_payments_amount"] = 0
        df["partial_payments_count"] = 0
        df["open_amount_with_taxes"] = df["total_amount_with_taxes"]

    return df


@st.cache_data(ttl=300)
def fetch_invoice_creation_overrides(
    page_size: int = 1000,
    max_pages: int = 5000,
) -> pd.DataFrame:
    all_rows = []
    offset = 0

    for _ in range(max_pages):
        res = (
            supabase.table("invoice_creation_override")
            .select("invoice_id,new_creation_date")
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
