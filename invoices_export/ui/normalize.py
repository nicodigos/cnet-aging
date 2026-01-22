from datetime import date
import pandas as pd


def normalize_invoices(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["issue_date"] = pd.to_datetime(df.get("issue_date"), errors="coerce").dt.date
    df["days_since_issue"] = pd.to_numeric(df.get("days_since_issue"), errors="coerce")
    df["total_amount_with_taxes"] = (
        pd.to_numeric(df.get("total_amount_with_taxes"), errors="coerce").fillna(0)
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
