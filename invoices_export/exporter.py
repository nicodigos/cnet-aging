from __future__ import annotations

import os
import re
import asyncio
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

BASE_URL = "https://app.master.cnetfranchise.com"
LOGIN_URL = f"{BASE_URL}/login"
INVOICES_URL = f"{BASE_URL}/manager/invoices"


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


def _login_and_download_csv_bytes() -> bytes:
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

    # 3) Load invoices page
    r3 = s.get(INVOICES_URL, timeout=60)
    r3.raise_for_status()

    # 4) Find export endpoint in invoices HTML
    export_url = _pick_export_url(r3.text, BASE_URL)

    # 5) Download CSV bytes
    dl = s.get(export_url, timeout=120)
    dl.raise_for_status()

    return dl.content


# Keep the same external function signature
async def _export_csv_bytes():
    # Keep async wrapper so you don't change any internal calling expectations
    return _login_and_download_csv_bytes()


def get_csv_bytes():
    # Same external API: returns bytes
    return asyncio.run(_export_csv_bytes())
