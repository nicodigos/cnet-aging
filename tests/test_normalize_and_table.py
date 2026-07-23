from datetime import date
import unittest
from unittest.mock import patch

import pandas as pd

from invoices_export.ui.normalize import (
    normalize_invoices,
    safe_aging_bounds,
    safe_issue_bounds,
)
from invoices_export.ui.table import render_past_due_table


MONETARY_COLUMNS = [
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


def raw_invoice_frame():
    row = {
        "issue_date": "2026-07-01",
        "days_since_issue": "22",
        "total_amount_with_taxes": "125.50",
        "partial_payments_amount": "25.50",
        "partial_payments_count": "2",
        "open_amount_with_taxes": "100.00",
        "past_due": " YES ",
        "payment_status": " Partially Paid ",
        "invoice_type": None,
        "buyer_company_name": None,
        "vendor_company_name": "Vendor A",
        "work_description": None,
        "po_number": None,
        "building_address": "123 Main St",
    }
    row.update({column: "10.25" for column in MONETARY_COLUMNS})
    return pd.DataFrame([row])


class NormalizeTests(unittest.TestCase):
    def test_normalize_invoices_converts_types_and_defaults(self):
        result = normalize_invoices(raw_invoice_frame())

        self.assertEqual(result.loc[0, "issue_date"], date(2026, 7, 1))
        self.assertEqual(result.loc[0, "total_amount_with_taxes"], 125.50)
        self.assertEqual(result.loc[0, "partial_payments_count"], 2)
        self.assertEqual(result.loc[0, "open_amount_with_taxes"], 100.00)
        self.assertTrue(bool(result.loc[0, "past_due"]))
        self.assertEqual(result.loc[0, "payment_status_norm"], "partially paid")
        self.assertEqual(result.loc[0, "buyer_company_name"], "(null)")
        self.assertEqual(result.loc[0, "po_number"], "")
        self.assertEqual(result.loc[0, "building_address"], "123 Main St")

    def test_open_amount_falls_back_to_invoice_total(self):
        frame = raw_invoice_frame()
        frame.loc[0, "open_amount_with_taxes"] = None

        result = normalize_invoices(frame)

        self.assertEqual(result.loc[0, "open_amount_with_taxes"], 125.50)

    def test_safe_bounds_handle_missing_values(self):
        frame = pd.DataFrame(
            {
                "issue_date": [pd.NaT],
                "days_since_issue": [float("nan")],
            }
        )

        min_issue, max_issue = safe_issue_bounds(frame)

        self.assertEqual(min_issue, date(2020, 1, 1))
        self.assertEqual(max_issue, date.today())
        self.assertEqual(safe_aging_bounds(frame), (0, 0))


class TableRenderingTests(unittest.TestCase):
    @patch("invoices_export.ui.table.st.dataframe")
    @patch("invoices_export.ui.table.st.subheader")
    @patch("invoices_export.ui.table.st.divider")
    def test_table_displays_open_balance_partial_payment_and_building(
        self,
        _divider,
        _subheader,
        dataframe,
    ):
        frame = pd.DataFrame(
            [
                {
                    "invoice_id": 1001,
                    "building_address": "123 Main St",
                    "past_due": True,
                    "total_amount_with_taxes": 125.0,
                    "open_amount_with_taxes": 100.0,
                    "partial_payments_amount": 25.0,
                }
            ]
        )

        render_past_due_table(frame)

        styler = dataframe.call_args.args[0]
        displayed = styler.data
        self.assertEqual(displayed.loc[0, "total_amount_with_taxes"], 100.0)
        self.assertEqual(displayed.loc[0, "partially_paid"], 25.0)
        self.assertEqual(displayed.loc[0, "building_address"], "123 Main St")
        self.assertEqual(displayed.loc[0, "past_due"], "Past Due")
        self.assertNotIn("open_amount_with_taxes", displayed.columns)
        self.assertNotIn("partial_payments_amount", displayed.columns)


if __name__ == "__main__":
    unittest.main()
