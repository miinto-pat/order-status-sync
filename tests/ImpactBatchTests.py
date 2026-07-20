import csv
import os
import unittest
import zipfile

from utils.ImpactBatch import (
    batch_rows_from_actions_by_state,
    create_batch_file_name,
    write_batch_csv,
    write_market_batch_zip,
)


class ImpactBatchTests(unittest.TestCase):
    def test_write_batch_csv_uses_action_id_identifier_and_impact_fields(self):
        rows = [
            {
                "action_id": "A1",
                "order_id": "DK-123",
                "amount": 12.34,
                "reason": "ORDER_UPDATE",
            },
            {
                "action_id": "A2",
                "order_id": "DK-124",
                "amount": 0,
                "reason": "ITEM_RETURNED",
            },
        ]

        tmp_dir = os.path.join(os.getcwd(), ".test-tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        try:
            path = os.path.join(tmp_dir, "batch.csv")
            write_batch_csv(path, rows)

            with open(path, newline="", encoding="utf-8") as fh:
                written = list(csv.DictReader(fh))
        finally:
            if os.path.exists(os.path.join(tmp_dir, "batch.csv")):
                os.remove(os.path.join(tmp_dir, "batch.csv"))
            if os.path.isdir(tmp_dir):
                os.rmdir(tmp_dir)

        self.assertEqual(
            written,
            [
                {"ActionID": "A1", "Oid": "DK-123", "Amount": "12.34", "Reason": "ORDER_UPDATE"},
                {"ActionID": "A2", "Oid": "DK-124", "Amount": "0", "Reason": "ITEM_RETURNED"},
            ],
        )

    def test_create_batch_file_name_is_csv_and_identifiable(self):
        name = create_batch_file_name("run-1", ["DK", "SE"])

        self.assertTrue(name.startswith("impact_batch_run-1_DK-SE_"))
        self.assertTrue(name.endswith(".csv"))

    def test_batch_rows_from_actions_by_state_keeps_only_impact_changes(self):
        rows = batch_rows_from_actions_by_state(
            "DK",
            {
                "ORDER_UPDATE": [{"actionId": "A1", "orderId": "DK-1", "amount": 10}],
                "OTHER": [{"actionId": "A2", "orderId": "DK-2", "amount": 0}],
                "Not_Modified": [{"actionId": "A3", "orderId": "DK-3", "amount": None}],
            },
        )

        self.assertEqual(
            rows,
            [
                {"market": "DK", "action_id": "A2", "order_id": "DK-2", "amount": 0, "reason": "OTHER"},
                {"market": "DK", "action_id": "A1", "order_id": "DK-1", "amount": 10, "reason": "ORDER_UPDATE"},
            ],
        )

    def test_write_market_batch_zip_creates_one_csv_per_market(self):
        rows = [
            {"market": "DK", "action_id": "A1", "order_id": "DK-1", "amount": 10, "reason": "ORDER_UPDATE"},
            {"market": "SE", "action_id": "A2", "order_id": "SE-1", "amount": 0, "reason": "OTHER"},
            {"market": "DK", "action_id": "A3", "order_id": "DK-2", "amount": 0, "reason": "ITEM_RETURNED"},
        ]
        tmp_dir = os.path.join(os.getcwd(), ".test-tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        zip_path = os.path.join(tmp_dir, "market_batches.zip")
        try:
            files = write_market_batch_zip(zip_path, rows, run_id="run-1")

            with zipfile.ZipFile(zip_path) as zipf:
                names = sorted(zipf.namelist())
                dk_content = zipf.read("impact_batch_run-1_DK.csv").decode("utf-8")
                se_content = zipf.read("impact_batch_run-1_SE.csv").decode("utf-8")
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            if os.path.isdir(tmp_dir):
                os.rmdir(tmp_dir)

        self.assertEqual(
            files,
            {
                "DK": "impact_batch_run-1_DK.csv",
                "SE": "impact_batch_run-1_SE.csv",
            },
        )
        self.assertEqual(names, ["impact_batch_run-1_DK.csv", "impact_batch_run-1_SE.csv"])
        self.assertIn("ActionID,Oid,Amount,Reason", dk_content)
        self.assertIn("A1,DK-1,10,ORDER_UPDATE", dk_content)
        self.assertIn("A3,DK-2,0,ITEM_RETURNED", dk_content)
        self.assertIn("A2,SE-1,0,OTHER", se_content)


if __name__ == "__main__":
    unittest.main()
