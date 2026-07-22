import io
import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client
import numpy as np

from invoices_export.exporter import (
    get_csv_exports_bytes,
    get_payment_summaries,
    get_purchase_order_numbers,
)

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

REQUIRED_ENRICHMENT_COLUMNS = {
    "partial_payments_amount",
    "partial_payments_count",
    "open_amount_with_taxes",
}

FEE_COLUMN_MAP = {
    "Invoice ID": "invoice_id",
    "Reference": "reference",
    "Vendor (Franchisee)": "vendor_franchisee",
    "Vendor Address": "vendor_address",
    "Vendor City": "vendor_city",
    "Vendor Postal Code": "vendor_postal_code",
    "Purchasor (Recipient of Services)": "purchaser_recipient_of_services",
    "Purchasor Address": "purchaser_address",
    "Purchasor City": "purchaser_city",
    "Purchasor Postal Code": "purchaser_postal_code",
    "Work Description": "work_description",
    "Building Address": "building_address",
    "Invoice Subtotal": "invoice_subtotal",
    "GST": "gst",
    "QST": "qst",
    "HST": "hst",
    "PST": "pst",
    "Invoice Total": "invoice_total",
    "Franchise Fee One-Shot": "franchise_fee_one_shot",
    "Franchise Fee Custodial": "franchise_fee_custodial",
    "Admin Fee": "admin_fee",
    "Advertising Fee": "advertising_fee",
    "Brokerage Fee": "brokerage_fee",
    "Total Owed": "total_owed",
}

FEE_NUMERIC_COLUMNS = {
    "invoice_subtotal",
    "gst",
    "qst",
    "hst",
    "pst",
    "invoice_total",
    "franchise_fee_one_shot",
    "franchise_fee_custodial",
    "admin_fee",
    "advertising_fee",
    "brokerage_fee",
    "total_owed",
}

INSERT_BATCH_SIZE = 500

JANITORIAL_DESCRIPTION = "Janitorial Services"
REGULAR_INVOICE_EXCEPTIONS = {
    "4057",
    "3208",
    "3200",
    "3199",
    "3198",
    "3197",
    "3350",
}

SCHEMA_SQL = """
alter table public.invoices_raw
  add column if not exists partial_payments_amount numeric,
  add column if not exists partial_payments_count integer,
  add column if not exists open_amount_with_taxes numeric;
""".strip()


def _ensure_enrichment_columns(supabase, table: str) -> None:
    try:
        (
            supabase.table(table)
            .select(",".join(sorted(REQUIRED_ENRICHMENT_COLUMNS)))
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(
            "Supabase is missing the partial-payment enrichment columns. "
            "Apply this SQL before running the sync:\n\n"
            f"{SCHEMA_SQL}"
        ) from exc


def _clean_work_descriptions(df: pd.DataFrame) -> None:
    """Remove the service label only from known Regular invoice exceptions."""
    if "invoice_id" not in df.columns or "work_description" not in df.columns:
        return

    invoice_ids = (
        df["invoice_id"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0+$", "", regex=True)
    )
    exception_mask = invoice_ids.isin(REGULAR_INVOICE_EXCEPTIONS)

    descriptions = df["work_description"].astype("string")
    cleaned_exceptions = descriptions.loc[exception_mask].str.replace(
        JANITORIAL_DESCRIPTION,
        "",
        case=False,
        regex=False,
    ).str.strip()

    # Keep empty descriptions as NULL so the invoices view categorizes them as Regular.
    df.loc[exception_mask, "work_description"] = cleaned_exceptions.mask(
        cleaned_exceptions.eq(""),
        pd.NA,
    )


def _validated_invoice_ids(df: pd.DataFrame, label: str) -> pd.Series:
    if "Invoice ID" not in df.columns:
        raise ValueError(f"{label} export is missing required column: Invoice ID")
    if df.empty:
        raise ValueError(f"{label} export contains no invoices")

    ids = pd.to_numeric(df["Invoice ID"], errors="coerce")
    if ids.isna().any():
        examples = df.loc[ids.isna(), "Invoice ID"].head(10).tolist()
        raise ValueError(f"{label} export has invalid Invoice ID values: {examples}")
    if not (ids % 1 == 0).all():
        examples = df.loc[ids % 1 != 0, "Invoice ID"].head(10).tolist()
        raise ValueError(f"{label} export has non-integer Invoice ID values: {examples}")

    ids = ids.astype("int64")
    if ids.duplicated().any():
        examples = ids.loc[ids.duplicated(keep=False)].head(10).tolist()
        raise ValueError(f"{label} export has duplicate Invoice IDs: {examples}")
    return ids


def _prepare_exports(
    invoices_csv_bytes: bytes,
    fees_csv_bytes: bytes,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invoices = pd.read_csv(io.BytesIO(invoices_csv_bytes), engine="python")
    fees = pd.read_csv(io.BytesIO(fees_csv_bytes), engine="python")

    missing_invoice_columns = set(COLUMN_MAP) - set(invoices.columns)
    if missing_invoice_columns:
        raise ValueError(
            "Invoices export is missing required columns: "
            f"{sorted(missing_invoice_columns)}"
        )
    missing_fee_columns = set(FEE_COLUMN_MAP) - set(fees.columns)
    if missing_fee_columns:
        raise ValueError(
            f"Fees export is missing required columns: {sorted(missing_fee_columns)}"
        )

    invoice_ids = _validated_invoice_ids(invoices, "Invoices")
    fee_ids = _validated_invoice_ids(fees, "Fees")
    invoice_id_set = set(invoice_ids.tolist())
    fee_id_set = set(fee_ids.tolist())
    if invoice_id_set != fee_id_set:
        only_invoices = sorted(invoice_id_set - fee_id_set)[:10]
        only_fees = sorted(fee_id_set - invoice_id_set)[:10]
        raise ValueError(
            "Invoice exports do not contain the same Invoice IDs. "
            f"Only in invoices (up to 10): {only_invoices}; "
            f"only in fees (up to 10): {only_fees}"
        )

    invoices = invoices.loc[:, list(COLUMN_MAP)].rename(columns=COLUMN_MAP)
    invoices["invoice_id"] = invoice_ids

    fees = fees.loc[:, list(FEE_COLUMN_MAP)].rename(columns=FEE_COLUMN_MAP)
    fees["invoice_id"] = fee_ids
    for column in FEE_NUMERIC_COLUMNS:
        raw_values = fees[column]
        numeric_values = pd.to_numeric(raw_values, errors="coerce")
        invalid = raw_values.notna() & numeric_values.isna()
        if invalid.any():
            examples = raw_values.loc[invalid].head(10).tolist()
            raise ValueError(
                f"Fees export has invalid numeric values in {column}: {examples}"
            )
        fees[column] = numeric_values

    return invoices, fees


def _json_records(df: pd.DataFrame) -> list[dict]:
    safe = df.replace([np.inf, -np.inf], np.nan)
    return safe.astype(object).where(pd.notnull(safe), None).to_dict(orient="records")


def _insert_in_batches(supabase, table: str, records: list[dict]) -> None:
    for start in range(0, len(records), INSERT_BATCH_SIZE):
        supabase.table(table).insert(records[start:start + INSERT_BATCH_SIZE]).execute()


def _fetch_invoice_ids(supabase, table: str, page_size: int = 1000) -> list[str]:
    invoice_ids: list[str] = []
    offset = 0
    while True:
        response = (
            supabase.table(table)
            .select("invoice_id")
            .order("invoice_id", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = response.data or []
        invoice_ids.extend(str(row["invoice_id"]).strip() for row in rows)
        if len(rows) < page_size:
            break
        offset += page_size

    if not invoice_ids:
        raise RuntimeError(f"No invoice IDs found in {table}")
    if len(invoice_ids) != len(set(invoice_ids)):
        raise RuntimeError(f"Duplicate invoice IDs found in {table}")
    return invoice_ids


def update_purchase_orders(progress_callback=None) -> tuple[int, int]:
    """Rebuild the PO table after every invoice page has been fetched successfully."""
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    invoices_table = os.getenv("SUPABASE_TABLE")
    po_table = os.getenv("SUPABASE_PO_TABLE", "invoice_purchase_orders")
    if not url or not key or not invoices_table:
        raise RuntimeError(
            "Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_TABLE"
        )

    supabase = create_client(url, key)
    invoice_ids = _fetch_invoice_ids(supabase, invoices_table)
    records = get_purchase_order_numbers(invoice_ids, progress_callback)
    po_count = sum(bool(record["po_number"]) for record in records)

    # Do not remove the previous snapshot until every CNET page succeeded.
    supabase.rpc("truncate_table", {"tbl": po_table}).execute()
    _insert_in_batches(supabase, po_table, records)
    return len(records), po_count


def run_pipeline():
    load_dotenv()

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    table = os.getenv("SUPABASE_TABLE")
    fees_table = os.getenv("SUPABASE_FEES_TABLE", "invoice_fees")
    if not url or not key or not table:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_TABLE")

    supabase = create_client(url, key)
    _ensure_enrichment_columns(supabase, table)

    invoices_csv_bytes, fees_csv_bytes = get_csv_exports_bytes()
    df, fees_df = _prepare_exports(invoices_csv_bytes, fees_csv_bytes)
    _clean_work_descriptions(df)

    status = df.get("payment_status", pd.Series(dtype=str)).fillna("").astype(str).str.strip().str.lower()
    partial_mask = status.eq("partially paid")
    partial_invoice_ids = df.loc[partial_mask, "invoice_id"].astype(str).str.strip().tolist()

    df["partial_payments_amount"] = 0.0
    df["partial_payments_count"] = 0

    if partial_invoice_ids:
        payment_summaries = get_payment_summaries(partial_invoice_ids)
        for idx, invoice_id in df.loc[partial_mask, "invoice_id"].astype(str).str.strip().items():
            summary = payment_summaries.get(invoice_id, {})
            df.at[idx, "partial_payments_amount"] = summary.get("partial_payments_amount", 0.0)
            df.at[idx, "partial_payments_count"] = summary.get("partial_payments_count", 0)

    total_with_taxes = pd.to_numeric(df.get("total_amount_with_taxes"), errors="coerce").fillna(0)
    partial_amount = pd.to_numeric(df["partial_payments_amount"], errors="coerce").fillna(0)
    df["open_amount_with_taxes"] = total_with_taxes
    df.loc[partial_mask, "open_amount_with_taxes"] = total_with_taxes.loc[partial_mask] - partial_amount.loc[partial_mask]

    # Parse the date, then convert to JSON-safe string
    dt = pd.to_datetime(df["creation_date"], format="%m/%d/%Y %H:%M", errors="coerce")
    df["creation_date"] = dt.dt.strftime("%Y-%m-%dT%H:%M:%S")  # ISO-ish, JSON safe

    records = _json_records(df)
    fee_records = _json_records(fees_df)

    # Rebuild fees first. Extra fee rows are harmless until invoices_raw is refreshed.
    supabase.rpc("truncate_table", {"tbl": fees_table}).execute()
    _insert_in_batches(supabase, fees_table, fee_records)

    # Truncate via RPC
    supabase.rpc("truncate_table", {"tbl": table}).execute()

    _insert_in_batches(supabase, table, records)
    return df, len(fees_df)


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
