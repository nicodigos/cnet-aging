from datetime import date
import pandas as pd


def normalize_invoices(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["issue_date"] = pd.to_datetime(df.get("issue_date"), errors="coerce").dt.date
    df["days_since_issue"] = pd.to_numeric(df.get("days_since_issue"), errors="coerce")
    df["total_amount_with_taxes"] = (
        pd.to_numeric(df.get("total_amount_with_taxes"), errors="coerce").fillna(0)
    )
    monetary_columns = [
        "total_amount_without_taxes",
        "gst_qc",
        "qst_qc",
        "hst_on",
        "gst_ab",
        "gst_bc",
        "pst_bc",
        "hst_nb",
        "pst_mb",
        "gst_mb",
        "hst_nl",
        "gst_nt",
        "hst_ns",
        "gst_nu",
        "hst_pe",
        "pst_sk",
        "gst_sk",
        "gst_yt",
        "invoice_subtotal",
        "fee_gst",
        "fee_qst",
        "fee_hst",
        "fee_pst",
        "invoice_total",
        "franchise_fee_one_shot",
        "franchise_fee_custodial",
        "admin_fee",
        "advertising_fee",
        "brokerage_fee",
        "total_owed",
    ]
    for column in monetary_columns:
        df[column] = pd.to_numeric(df.get(column), errors="coerce").fillna(0)
    df["partial_payments_amount"] = (
        pd.to_numeric(df.get("partial_payments_amount", 0), errors="coerce").fillna(0)
    )
    df["partial_payments_count"] = (
        pd.to_numeric(df.get("partial_payments_count", 0), errors="coerce").fillna(0).astype(int)
    )
    df["open_amount_with_taxes"] = (
        pd.to_numeric(df.get("open_amount_with_taxes"), errors="coerce")
        .fillna(df["total_amount_with_taxes"])
    )

    past_due_raw = df.get("past_due")
    if past_due_raw is None:
        df["past_due"] = False
    else:
        s = past_due_raw.astype(str).str.strip().str.lower()
        df["past_due"] = s.isin(["true", "t", "1", "yes"])

    df["payment_status"] = df.get("payment_status", "").fillna("").astype(str)
    df["payment_status_norm"] = df["payment_status"].str.strip().str.lower()

    df["invoice_type"] = df.get("invoice_type", "").fillna("").astype(str)
    df["buyer_company_name"] = df.get("buyer_company_name", "").fillna("(null)").astype(str)
    df["vendor_company_name"] = df.get("vendor_company_name", "").fillna("(null)").astype(str)
    df["work_description"] = df.get("work_description", "").fillna("").astype(str)
    df["po_number"] = df.get("po_number", "").fillna("").astype(str)
    df["building_address"] = df.get("building_address", "").fillna("").astype(str)

    return df


def safe_issue_bounds(df: pd.DataFrame) -> tuple[date, date]:
    min_issue = df["issue_date"].min()
    max_issue = df["issue_date"].max()

    if pd.isna(min_issue) or min_issue is None:
        min_issue = date(2020, 1, 1)
    if pd.isna(max_issue) or max_issue is None:
        max_issue = date.today()

    return min_issue, max_issue


def safe_aging_bounds(df: pd.DataFrame) -> tuple[int, int]:
    min_aging = df["days_since_issue"].min()
    max_aging = df["days_since_issue"].max()

    min_aging = int(min_aging) if pd.notna(min_aging) else 0
    max_aging = int(max_aging) if pd.notna(max_aging) else 0

    if min_aging > max_aging:
        min_aging, max_aging = max_aging, min_aging

    return min_aging, max_aging
