from pathlib import Path
import tempfile
import unittest

import pandas as pd

from invoices_export.ui.reports import (
    REPORT_DETAIL_COLUMNS_TO_HIDE,
    _prepare_report_amount_columns,
    _report_hidden_columns,
)
from reporting.report import ClientReportGenerator, sanitize_path_part


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PROJECT_ROOT / "reporting" / "templates"


def report_frame():
    return pd.DataFrame(
        [
            {
                "vendor_company_name": "Vendor / A",
                "buyer_company_name": "Buyer: A",
                "invoice_id": "INV-1",
                "building_address": "123 Main St",
                "po_number": "PO-HIDDEN",
                "total_amount_without_taxes": 100,
                "gst_qc": 5,
                "fee_gst": 5,
                "total_owed": 110,
                "partial_payments_amount": 10,
                "partial_payments_count": 1,
                "open_amount_with_taxes": 100,
                "total_amount_with_taxes": 110,
            }
        ]
    )


class ReportTests(unittest.TestCase):
    def test_report_amounts_expose_partial_payment_and_open_balance(self):
        prepared = _prepare_report_amount_columns(report_frame())

        self.assertEqual(prepared.loc[0, "partially_paid"], 10)
        self.assertEqual(prepared.loc[0, "total_amount_with_taxes"], 100)

    def test_hidden_columns_keep_building_and_remove_internal_details(self):
        hidden = _report_hidden_columns()

        self.assertNotIn("building_address", hidden)
        self.assertIn("po_number", hidden)
        self.assertIn("total_amount_without_taxes", hidden)
        self.assertIn("gst_qc", hidden)
        self.assertIn("fee_gst", hidden)
        self.assertIn("total_owed", hidden)
        self.assertTrue(set(REPORT_DETAIL_COLUMNS_TO_HIDE).issubset(hidden))

    def test_full_and_partitioned_reports_hide_details_but_keep_building(self):
        frame = _prepare_report_amount_columns(report_frame())
        with tempfile.TemporaryDirectory() as tmp:
            generator = ClientReportGenerator(TEMPLATE_DIR, tmp)
            full_path = generator.generate_html(
                frame,
                "buyer_company_name",
                "total_amount_with_taxes",
                "full.html",
                hide_columns=_report_hidden_columns(),
            )
            root = generator.generate_html_partitioned(
                frame,
                "buyer_company_name",
                "total_amount_with_taxes",
                output_root_name="partitioned",
                hide_columns=_report_hidden_columns(),
            )

            report_paths = [full_path, *root.rglob("report.html")]
            self.assertEqual(len(report_paths), 2)
            for path in report_paths:
                html = path.read_text(encoding="utf-8")
                self.assertIn("123 Main St", html)
                self.assertIn("building_address", html)
                self.assertNotIn("PO-HIDDEN", html)
                self.assertNotIn("po_number", html)
                self.assertNotIn("total_amount_without_taxes", html)
                self.assertNotIn("gst_qc", html)
                self.assertNotIn("fee_gst", html)
                self.assertNotIn("total_owed", html)

    def test_partition_paths_are_sanitized(self):
        sanitized = sanitize_path_part("Vendor / A:*?")

        self.assertEqual(sanitized, "Vendor___A")
        self.assertNotIn("/", sanitized)
        self.assertNotIn(":", sanitized)
        self.assertNotIn("*", sanitized)
        self.assertNotIn("?", sanitized)


if __name__ == "__main__":
    unittest.main()
