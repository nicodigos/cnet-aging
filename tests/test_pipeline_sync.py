import io
import sys
import types
import unittest

import numpy as np
import pandas as pd

# The sync helpers tested here are pure transformations. Stub the optional
# service client so the suite can run without Supabase installed or configured.
if "supabase" not in sys.modules:
    supabase_stub = types.ModuleType("supabase")
    supabase_stub.create_client = lambda *_args, **_kwargs: None
    sys.modules["supabase"] = supabase_stub

from pipeline.sync import (
    COLUMN_MAP,
    FEE_COLUMN_MAP,
    _clean_work_descriptions,
    _json_records,
    _prepare_exports,
    _validated_invoice_ids,
)


def csv_bytes(rows, columns):
    return pd.DataFrame(rows, columns=columns).to_csv(index=False).encode("utf-8")


def valid_invoice_row(invoice_id=1001):
    row = {column: "" for column in COLUMN_MAP}
    row.update(
        {
            "Invoice ID": invoice_id,
            "Creation Date": "07/01/2026 10:30",
            "Payment Status": "Unpaid",
            "Total Amount Without Taxes": "100",
            "Total Amount With Taxes": "113",
        }
    )
    return row


def valid_fee_row(invoice_id=1001):
    row = {column: "" for column in FEE_COLUMN_MAP}
    row.update(
        {
            "Invoice ID": invoice_id,
            "Building Address": "123 Main St",
            "Invoice Subtotal": "100",
            "GST": "5",
            "QST": "0",
            "HST": "8",
            "PST": "0",
            "Invoice Total": "113",
            "Franchise Fee One-Shot": "1",
            "Franchise Fee Custodial": "2",
            "Admin Fee": "3",
            "Advertising Fee": "4",
            "Brokerage Fee": "5",
            "Total Owed": "15",
        }
    )
    return row


class PipelineValidationTests(unittest.TestCase):
    def test_prepare_exports_maps_columns_and_numeric_fees(self):
        invoices, fees = _prepare_exports(
            csv_bytes([valid_invoice_row()], COLUMN_MAP),
            csv_bytes([valid_fee_row()], FEE_COLUMN_MAP),
        )

        self.assertEqual(invoices.loc[0, "invoice_id"], 1001)
        self.assertEqual(invoices.loc[0, "total_amount_with_taxes"], 113)
        self.assertEqual(fees.loc[0, "building_address"], "123 Main St")
        self.assertEqual(fees.loc[0, "total_owed"], 15)

    def test_prepare_exports_rejects_mismatched_invoice_sets(self):
        with self.assertRaisesRegex(ValueError, "same Invoice IDs"):
            _prepare_exports(
                csv_bytes([valid_invoice_row(1001)], COLUMN_MAP),
                csv_bytes([valid_fee_row(2002)], FEE_COLUMN_MAP),
            )

    def test_prepare_exports_rejects_invalid_fee_amount(self):
        fee = valid_fee_row()
        fee["Total Owed"] = "invalid"

        with self.assertRaisesRegex(ValueError, "invalid numeric values in total_owed"):
            _prepare_exports(
                csv_bytes([valid_invoice_row()], COLUMN_MAP),
                csv_bytes([fee], FEE_COLUMN_MAP),
            )

    def test_invoice_id_validation_rejects_duplicates_and_decimals(self):
        with self.assertRaisesRegex(ValueError, "duplicate Invoice IDs"):
            _validated_invoice_ids(
                pd.DataFrame({"Invoice ID": [1001, 1001]}),
                "Invoices",
            )
        with self.assertRaisesRegex(ValueError, "non-integer Invoice ID"):
            _validated_invoice_ids(
                pd.DataFrame({"Invoice ID": [1001.5]}),
                "Invoices",
            )

    def test_clean_work_descriptions_only_changes_known_exceptions(self):
        frame = pd.DataFrame(
            {
                "invoice_id": [4057, 9999],
                "work_description": [
                    "Janitorial Services",
                    "Janitorial Services",
                ],
            }
        )

        _clean_work_descriptions(frame)

        self.assertTrue(pd.isna(frame.loc[0, "work_description"]))
        self.assertEqual(frame.loc[1, "work_description"], "Janitorial Services")

    def test_json_records_replace_non_json_numeric_values_with_none(self):
        records = _json_records(
            pd.DataFrame([{"finite": 1.5, "nan": np.nan, "infinite": np.inf}])
        )

        self.assertEqual(records, [{"finite": 1.5, "nan": None, "infinite": None}])


if __name__ == "__main__":
    unittest.main()
