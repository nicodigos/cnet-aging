from __future__ import annotations

import os
import re
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from typing import Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://app.master.cnetfranchise.com"
LOGIN_URL = f"{BASE_URL}/login"
INVOICES_URL = f"{BASE_URL}/manager/invoices"
FEES_EXPORT_URL = f"{BASE_URL}/manager/invoices/export/fees"
PO_REQUEST_WORKERS = 8


def _pick_export_url(html: str, base_url: str) -> str:
    """
    Try to locate the export URL in the invoices page HTML.
    This looks for:
      - <a> with text like "Export search results"
      - elements with href/data-href/data-url/onclick containing "export"
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1) Direct <a> by text
    for a in soup.find_all("a"):
        txt = (a.get_text(" ", strip=True) or "")
        if re.search(r"export\s+search\s+results", txt, flags=re.I):
            href = a.get("href")
            if href:
                return urljoin(base_url, href)

    # 2) Any tag with href/data-* that looks export-ish
    candidates = []
    for tag in soup.find_all(True):
        for attr in ("href", "data-href", "data-url", "data-export-url"):
            val = tag.get(attr)
            if val and re.search(r"export", val, flags=re.I):
                candidates.append(val)

        onclick = tag.get("onclick")
        if onclick and re.search(r"export", onclick, flags=re.I):
            # Try to extract a quoted URL from onclick="location.href='...'"
            m = re.search(r"""['"](/[^'"]+)['"]""", onclick)
            if m:
                candidates.append(m.group(1))

    if candidates:
        return urljoin(base_url, candidates[0])

    raise RuntimeError(
        "Could not find the Export URL in the invoices page HTML. "
        "Open the invoices page source and locate the export link/endpoint, "
        "then adapt _pick_export_url()."
    )


def _authenticated_session() -> requests.Session:
    load_dotenv()

    user = os.getenv("CNET_USER")
    pw = os.getenv("CNET_PASS")
    if not user or not pw:
        raise RuntimeError("Missing CNET_USER or CNET_PASS")

    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )

    # 1) GET login page (to fetch cookies + CSRF/hidden inputs)
    r = s.get(LOGIN_URL, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    form = soup.find("form")
    if not form:
        raise RuntimeError("Login page has no <form>. Login flow likely changed.")

    action = form.get("action") or "/login"
    post_url = urljoin(BASE_URL, action)

    # Collect hidden inputs (CSRF tokens, etc.)
    payload = {}
    for inp in form.select("input"):
        name = inp.get("name")
        if not name:
            continue
        itype = (inp.get("type") or "").lower()
        if itype in ("hidden", "submit"):
            payload[name] = inp.get("value") or ""

    # Add credentials in the same fields your Playwright code used
    payload["_username"] = user
    payload["_password"] = pw

    # 2) POST login (follow redirects)
    r2 = s.post(post_url, data=payload, allow_redirects=True, timeout=60)
    r2.raise_for_status()

    # Basic sanity: if we got bounced back to /login, auth failed
    if "/login" in r2.url:
        raise RuntimeError("Login appears to have failed (redirected back to /login).")

    return s


def _login_and_download_csv_bytes() -> bytes:
    s = _authenticated_session()

    # 3) Load invoices page
    r3 = s.get(INVOICES_URL, timeout=60)
    r3.raise_for_status()

    # 4) Find export endpoint in invoices HTML
    export_url = _pick_export_url(r3.text, BASE_URL)

    # 5) Download CSV bytes
    dl = s.get(export_url, timeout=120)
    dl.raise_for_status()

    return dl.content


def _login_and_download_csv_exports_bytes() -> tuple[bytes, bytes]:
    """Download the standard and fee exports using the same authenticated session."""
    s = _authenticated_session()

    invoices_page = s.get(INVOICES_URL, timeout=60)
    invoices_page.raise_for_status()
    export_url = _pick_export_url(invoices_page.text, BASE_URL)

    invoices_response = s.get(export_url, timeout=120)
    invoices_response.raise_for_status()

    fees_response = s.get(FEES_EXPORT_URL, timeout=120)
    fees_response.raise_for_status()

    return invoices_response.content, fees_response.content


def _parse_money(value: str) -> Decimal:
    cleaned = (value or "").strip().replace(",", "").replace("$", "")
    cleaned = re.sub(r"^\((.*)\)$", r"-\1", cleaned)
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def _extract_payment_summary(html: str) -> dict[str, float | int]:
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.select("table"):
        headers = [th.get_text(" ", strip=True).lower() for th in table.select("thead th")]
        if "payment date" not in headers or "amount" not in headers:
            continue

        amount_idx = headers.index("amount")
        total = Decimal("0")
        count = 0

        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if amount_idx >= len(cells):
                continue

            amount_text = cells[amount_idx].get_text(" ", strip=True)
            if not amount_text:
                continue

            total += _parse_money(amount_text)
            count += 1

        return {
            "partial_payments_amount": float(total),
            "partial_payments_count": count,
        }

    return {
        "partial_payments_amount": 0.0,
        "partial_payments_count": 0,
    }


def get_payment_summaries(invoice_ids: list[str]) -> dict[str, dict[str, float | int]]:
    if not invoice_ids:
        return {}

    s = _authenticated_session()
    out = {}

    for invoice_id in invoice_ids:
        inv = str(invoice_id).strip()
        if not inv:
            continue

        show_url = f"{BASE_URL}/manager/invoices/{inv}/show"
        r = s.get(show_url, timeout=60)
        r.raise_for_status()
        out[inv] = _extract_payment_summary(r.text)

    return out


def _extract_po_number(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for paragraph in soup.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        if not re.match(r"^PO\s+Number\s*:", text, flags=re.I):
            continue

        strong = paragraph.find("strong")
        value = strong.get_text(" ", strip=True) if strong else text.split(":", 1)[1].strip()
        return value or None
    return None


def get_purchase_order_numbers(
    invoice_ids: list[str],
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[dict[str, str | None]]:
    """Fetch PO numbers for invoice IDs while reusing one authenticated login."""
    normalized_ids = [str(invoice_id).strip() for invoice_id in invoice_ids]
    normalized_ids = [invoice_id for invoice_id in normalized_ids if invoice_id]
    if not normalized_ids:
        return []

    authenticated = _authenticated_session()
    cookies = authenticated.cookies.get_dict()
    headers = dict(authenticated.headers)
    thread_state = threading.local()

    def worker_session() -> requests.Session:
        if not hasattr(thread_state, "session"):
            session = requests.Session()
            session.headers.update(headers)
            session.cookies.update(cookies)
            retries = Retry(
                total=3,
                connect=3,
                read=3,
                backoff_factor=0.5,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
            )
            session.mount("https://", HTTPAdapter(max_retries=retries))
            thread_state.session = session
        return thread_state.session

    def fetch_one(invoice_id: str) -> dict[str, str | None]:
        url = f"{BASE_URL}/manager/invoices/{invoice_id}/show"
        response = worker_session().get(url, timeout=60)
        response.raise_for_status()
        if "/login" in response.url:
            raise RuntimeError("CNET session expired while fetching invoice pages")
        return {
            "invoice_id": invoice_id,
            "po_number": _extract_po_number(response.text),
        }

    records: list[dict[str, str | None]] = []
    failures: list[str] = []
    total = len(normalized_ids)
    with ThreadPoolExecutor(max_workers=PO_REQUEST_WORKERS) as executor:
        futures = {
            executor.submit(fetch_one, invoice_id): invoice_id
            for invoice_id in normalized_ids
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            invoice_id = futures[future]
            try:
                records.append(future.result())
            except Exception as exc:
                failures.append(f"{invoice_id}: {exc}")
            if progress_callback:
                progress_callback(completed, total)

    if failures:
        preview = "; ".join(failures[:10])
        raise RuntimeError(
            f"Failed to fetch {len(failures)} of {total} invoice pages. "
            f"No PO data was replaced. Examples: {preview}"
        )

    return sorted(records, key=lambda record: int(record["invoice_id"]))


# Keep the same external function signature
async def _export_csv_bytes():
    # Keep async wrapper so you don't change any internal calling expectations
    return _login_and_download_csv_bytes()


async def _export_csv_exports_bytes():
    return _login_and_download_csv_exports_bytes()


def get_csv_bytes():
    # Same external API: returns bytes
    return asyncio.run(_export_csv_bytes())


def get_csv_exports_bytes() -> tuple[bytes, bytes]:
    """Return (standard invoices CSV, invoice fees CSV)."""
    return asyncio.run(_export_csv_exports_bytes())
