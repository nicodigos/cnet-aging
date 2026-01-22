import sys
import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Fix Windows Playwright subprocess issue
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

BASE_URL = "https://app.master.cnetfranchise.com"
LOGIN_URL = f"{BASE_URL}/login"
INVOICES_URL = f"{BASE_URL}/manager/invoices"


async def _export_csv_bytes():
    load_dotenv()

    user = os.getenv("CNET_USER")
    pw = os.getenv("CNET_PASS")
    if not user or not pw:
        raise RuntimeError("Missing CNET_USER or CNET_PASS")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # Login
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.fill('input[name="_username"]', user)
        await page.fill('input[name="_password"]', pw)
        await page.click("#_submit")
        await page.wait_for_load_state("networkidle")

        # Invoices page
        await page.goto(INVOICES_URL, wait_until="networkidle")

        async with page.expect_download() as dl:
            await page.locator("text=/Export search results/i").first.click()

        download = await dl.value
        path = await download.path()

        with open(path, "rb") as f:
            csv_bytes = f.read()

        await context.close()
        await browser.close()

        return csv_bytes


def get_csv_bytes():
    return asyncio.run(_export_csv_bytes())
