from decimal import Decimal
import unittest

from invoices_export.exporter import (
    _extract_payment_summary,
    _extract_po_number,
    _parse_money,
    _pick_export_url,
)


class ExporterParsingTests(unittest.TestCase):
    def test_pick_export_url_prefers_named_export_link(self):
        html = """
        <a href="/manager/invoices/export?status=unpaid">
            Export search results
        </a>
        """

        result = _pick_export_url(html, "https://example.test")

        self.assertEqual(
            result,
            "https://example.test/manager/invoices/export?status=unpaid",
        )

    def test_pick_export_url_raises_when_page_structure_changes(self):
        with self.assertRaisesRegex(RuntimeError, "Could not find the Export URL"):
            _pick_export_url("<html><body>No export action</body></html>", "https://example.test")

    def test_parse_money_supports_currency_commas_and_parentheses(self):
        self.assertEqual(_parse_money("$1,234.56"), Decimal("1234.56"))
        self.assertEqual(_parse_money("($45.10)"), Decimal("-45.10"))
        self.assertEqual(_parse_money("not a number"), Decimal("0"))

    def test_extract_payment_summary_uses_payment_table_only(self):
        html = """
        <table><thead><tr><th>Item</th><th>Amount</th></tr></thead></table>
        <table>
          <thead><tr><th>Payment Date</th><th>Amount</th></tr></thead>
          <tbody>
            <tr><td>2026-06-01</td><td>$100.25</td></tr>
            <tr><td>2026-06-15</td><td>($20.00)</td></tr>
          </tbody>
        </table>
        """

        result = _extract_payment_summary(html)

        self.assertEqual(result["partial_payments_amount"], 80.25)
        self.assertEqual(result["partial_payments_count"], 2)

    def test_extract_po_number_supports_strong_and_plain_text(self):
        self.assertEqual(
            _extract_po_number("<p>PO Number: <strong>PO-123</strong></p>"),
            "PO-123",
        )
        self.assertEqual(
            _extract_po_number("<p>PO Number: PO-456</p>"),
            "PO-456",
        )
        self.assertIsNone(_extract_po_number("<p>Invoice Number: 123</p>"))


if __name__ == "__main__":
    unittest.main()
