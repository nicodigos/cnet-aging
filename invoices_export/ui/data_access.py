import pandas as pd
import streamlit as st

from pipeline.database import connect


def _read_dataframe(query: str) -> pd.DataFrame:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [column.name for column in cursor.description]
            return pd.DataFrame(cursor.fetchall(), columns=columns)


@st.cache_data(ttl=300)
def fetch_all_rows(page_size: int = 1000, max_pages: int = 5000) -> pd.DataFrame:
    del page_size, max_pages
    query = """
        select invoice_id, issue_date, creation_date, invoice_type,
               buyer_company_name, vendor_company_name, payment_status,
               days_since_issue, past_due, total_amount_with_taxes,
               work_description, partial_payments_amount,
               partial_payments_count, open_amount_with_taxes
        from public.invoices_v
        order by invoice_id
    """
    return _read_dataframe(query)


@st.cache_data(ttl=300)
def fetch_invoice_creation_overrides(
    page_size: int = 1000,
    max_pages: int = 5000,
) -> pd.DataFrame:
    del page_size, max_pages
    return _read_dataframe(
        """
        select invoice_id, new_creation_date
        from public.invoice_creation_override
        order by invoice_id
        """
    )
