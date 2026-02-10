import io
import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client
import numpy as np

from invoices_export import get_csv_bytes

COLUMN_MAP = {
    "Invoice ID": "invoice_id",
    "Creation Date": "creation_date",
    "Work Description": "work_description",
    "Payment Status": "payment_status",
    "Vendor Company Name": "vendor_company_name",
    "Vendor First Name": "vendor_first_name",
    "Vendor Last Name": "vendor_last_name",
    "Vendor Address": "vendor_address",
    "Vendor City": "vendor_city",
    "Vendor Postal Code": "vendor_postal_code",
    "Vendor Province": "vendor_province",
    "Vendor Country": "vendor_country",
    "Vendor Phone Number": "vendor_phone_number",
    "Vendor Cell Phone": "vendor_cell_phone",
    "Buyer Company Name": "buyer_company_name",
    "Buyer First Name": "buyer_first_name",
    "Buyer Last Name": "buyer_last_name",
    "Buyer Address": "buyer_address",
    "Buyer City": "buyer_city",
    "Buyer Postal Code": "buyer_postal_code",
    "Buyer Province": "buyer_province",
    "Buyer Country": "buyer_country",
    "Buyer Phone Number": "buyer_phone_number",
    "Buyer Cell Phone": "buyer_cell_phone",
    "Total Amount Without Taxes": "total_amount_without_taxes",
    "Total Amount With Taxes": "total_amount_with_taxes",
    "GST QC": "gst_qc",
    "QST QC": "qst_qc",
    "HST ON": "hst_on",
    "GST AB": "gst_ab",
    "GST BC": "gst_bc",
    "PST BC": "pst_bc",
    "HST NB": "hst_nb",
    "PST MB": "pst_mb",
    "GST MB": "gst_mb",
    "HST NL": "hst_nl",
    "GST NT": "gst_nt",
    "HST NS": "hst_ns",
    "GST NU": "gst_nu",
    "HST PE": "hst_pe",
    "PST SK": "pst_sk",
    "GST SK": "gst_sk",
    "GST YT": "gst_yt",
}

def run_pipeline():
    load_dotenv()

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    table = os.getenv("SUPABASE_TABLE")
    if not url or not key or not table:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_TABLE")

    csv_bytes = get_csv_bytes()
    df = pd.read_csv(io.BytesIO(csv_bytes), engine="python")

    df = df.rename(columns=COLUMN_MAP)

    # Parse the date, then convert to JSON-safe string
    dt = pd.to_datetime(df["creation_date"], format="%m/%d/%Y %H:%M", errors="coerce")
    df["creation_date"] = dt.dt.strftime("%Y-%m-%dT%H:%M:%S")  # ISO-ish, JSON safe

    df = df.replace([np.nan, np.inf, -np.inf], None)
    records = df.to_dict(orient="records")
    # JSON-safe None handling
    records = df.where(pd.notnull(df), None).to_dict(orient="records")

    supabase = create_client(url, key)

    # Truncate via RPC
    supabase.rpc("truncate_table", {"tbl": table}).execute()

    supabase.table(table).insert(records).execute()
    return df


def upload_invoice_creation_overrides(df: pd.DataFrame) -> int:
    """
    Expects a DataFrame where:
      - column 0 = invoice_id (int-like, e.g. 2345)
      - column 1 = new_creation_date (string or date) in YYYY-MM-DD

    Upserts into Supabase table invoice_creation_override:
      - update new_creation_date if invoice_id exists
      - insert row if invoice_id does not exist

    Returns number of rows upserted.
    """
    if df is None or df.empty:
        return 0
    if df.shape[1] < 2:
        raise ValueError("DataFrame must have at least 2 columns: [invoice_id, new_creation_date].")

    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

    # Use only the first 2 columns, order-based
    work = df.iloc[:, :2].copy()

    # Validate invoice_id: must be integer-like (no decimals, no nulls)
    ids = pd.to_numeric(work.iloc[:, 0], errors="coerce")
    if ids.isna().any():
        bad = work.loc[ids.isna(), work.columns[0]].head(10).tolist()
        raise ValueError(f"Invalid invoice_id(s) (non-numeric or null). Examples: {bad}")
    if not (ids % 1 == 0).all():
        bad = work.loc[(ids % 1 != 0), work.columns[0]].head(10).tolist()
        raise ValueError(f"invoice_id must be integers. Examples: {bad}")
    ids = ids.astype("int64")

    # Validate date strictly as YYYY-MM-DD
    raw_dates = work.iloc[:, 1].astype(str).str.strip()
    dt = pd.to_datetime(raw_dates, format="%Y-%m-%d", errors="coerce")
    if dt.isna().any():
        bad = work.loc[dt.isna(), work.columns[1]].head(10).tolist()
        raise ValueError(f"Invalid date(s). Must be YYYY-MM-DD. Examples: {bad}")

    # Build records for Supabase
    payload = pd.DataFrame({
        "invoice_id": ids,
        "new_creation_date": dt.dt.strftime("%Y-%m-%d"),
    })

    # If duplicates exist, keep the last one (latest row wins)
    payload = payload.drop_duplicates(subset=["invoice_id"], keep="last")

    records = payload.to_dict(orient="records")

    supabase = create_client(url, key)

    # Upsert: update date if exists, insert if not
    supabase.table("invoice_creation_override").upsert(
        records,
        on_conflict="invoice_id"
    ).execute()

    return len(records)