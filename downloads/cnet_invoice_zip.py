from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


# --------------------- Site constants ---------------------
BASE = "https://app.master.cnetfranchise.com"
LOGIN_URL = f"{BASE}/login"
LOGIN_CHECK_URL = f"{BASE}/login_check"
MANAGER_HOME = f"{BASE}/manager/"
DASHBOARD_MARKER = "Homepage"  # adjust if needed

PDF_TEXT_CANDIDATES = {
    "download pdf", "pdf", "print pdf", "download", "imprimer pdf", "télécharger pdf"
}


# --------------------- Public config ---------------------
@dataclass(frozen=True)
class CNetCredentials:
    user: str
    password: str


def load_cnet_credentials_from_env() -> CNetCredentials:
    user = os.getenv("CNET_USER")
    pw = os.getenv("CNET_PASS")
    if not user or not pw:
        raise RuntimeError("Missing env vars: CNET_USER / CNET_PASS")
    return CNetCredentials(user=user, password=pw)


# --------------------- Helpers ---------------------
def sanitize(s: str, maxlen: int = 80) -> str:
    s = re.sub(r"[^\w\-. ]+", "_", s or "", flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s)
    return s[:maxlen].strip("_")


def extract_csrf_from_login(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    token = soup.find("input", {"name": "_csrf_token"})
    if token and token.has_attr("value"):
        return token["value"]
    for name in ("csrf_token", "_token"):
        el = soup.find("input", {"name": name})
        if el and el.has_attr("value"):
            return el["value"]
    return None


def login(creds: CNetCredentials, remember_me: bool = True) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; cnet-downloader/1.0)"})

    r = s.get(LOGIN_URL, timeout=15)
    r.raise_for_status()
    csrf = extract_csrf_from_login(r.text)

    payload = {"_username": creds.user, "_password": creds.password}
    if csrf:
        payload["_csrf_token"] = csrf
    if remember_me:
        payload["_remember_me"] = "on"

    resp = s.post(LOGIN_CHECK_URL, data=payload, timeout=20, allow_redirects=True)
    resp.raise_for_status()

    guard = s.get(MANAGER_HOME, timeout=20)
    if not (guard.ok and (DASHBOARD_MARKER.lower() in guard.text.lower())):
        snippet = resp.text[:300].strip().replace("\n", " ")
        raise RuntimeError(f"Login likely failed; URL={resp.url}. Snippet: {snippet!r}")

    return s


def find_pdf_link(show_html: str) -> Optional[str]:
    soup = BeautifulSoup(show_html, "lxml")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True).lower()

        if href.lower().endswith(".pdf"):
            return href
        if "pdf" in href.lower():
            return href
        if text in PDF_TEXT_CANDIDATES or "pdf" in text:
            return href

    for form in soup.find_all("form"):
        action = (form.get("action") or "")
        if "pdf" in action.lower():
            return action

    return None


def fetch_pdf_bytes(session: requests.Session, pdf_url: str) -> bytes:
    url = urljoin(BASE, pdf_url)
    with session.get(url, timeout=60, stream=True) as r:
        r.raise_for_status()
        return r.content


# --------------------- Public API ---------------------
def build_past_due_invoices_zip_by_vendor_buyer(
    df: pd.DataFrame,
    creds: Optional[CNetCredentials] = None,
    *,
    include_fail_markers: bool = True,
) -> tuple[bytes, str]:
    """
    Build a ZIP with PDFs organized as Vendor/Buyer/*.pdf

    Expected df to already be filtered to:
      - past_due == True
      - payment_status_norm != "paid"

    Required columns:
      - invoice_id
      - vendor_company_name
      - buyer_company_name
    Optional:
      - work_description

    Returns: (zip_bytes, zip_filename)
    """
    if df is None or df.empty:
        raise ValueError("df is empty (no invoices to download).")

    required = {"invoice_id", "vendor_company_name", "buyer_company_name"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    if creds is None:
        creds = load_cnet_credentials_from_env()

    session = login(creds, remember_me=True)

    df2 = df.copy()
    df2["invoice_id"] = df2["invoice_id"].astype(str).str.strip()
    if "work_description" not in df2.columns:
        df2["work_description"] = ""

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_name = f"past_due_invoices_by_vendor_buyer_{ts}.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for _, row in df2.iterrows():
            inv_id = str(row.get("invoice_id", "")).strip()
            if not inv_id:
                continue

            vendor = sanitize(str(row.get("vendor_company_name") or "(null)"), maxlen=60) or "(null)"
            buyer = sanitize(str(row.get("buyer_company_name") or "(null)"), maxlen=60) or "(null)"
            work = sanitize(str(row.get("work_description") or ""), maxlen=60)

            show_url = f"{BASE}/manager/invoices/{inv_id}/show"
            try:
                show_resp = session.get(show_url, timeout=30)
                show_resp.raise_for_status()
            except Exception as e:
                if include_fail_markers:
                    z.writestr(
                        f"{vendor}/{buyer}/FAILED_SHOW_{inv_id}.txt",
                        f"Failed to open show page for invoice {inv_id}\nURL: {show_url}\nError: {e}\n",
                    )
                continue

            pdf_href = find_pdf_link(show_resp.text)
            if not pdf_href:
                if include_fail_markers:
                    z.writestr(
                        f"{vendor}/{buyer}/FAILED_NO_PDF_LINK_{inv_id}.txt",
                        f"No PDF link found for invoice {inv_id}\nURL: {show_url}\n",
                    )
                continue

            try:
                pdf_bytes = fetch_pdf_bytes(session, pdf_href)
            except Exception as e:
                if include_fail_markers:
                    z.writestr(
                        f"{vendor}/{buyer}/FAILED_PDF_{inv_id}.txt",
                        f"Failed to download PDF for invoice {inv_id}\nPDF href: {pdf_href}\nError: {e}\n",
                    )
                continue

            filename = f"invoice_{inv_id}_{work or 'document'}.pdf"
            zip_path = f"{vendor}/{buyer}/{filename}"
            z.writestr(zip_path, pdf_bytes)

    buf.seek(0)
    return buf.read(), zip_name
