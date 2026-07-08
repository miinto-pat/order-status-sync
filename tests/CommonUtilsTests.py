import json
import os
import tempfile
import unittest
from unittest.mock import patch

from utils.CommonUtils import common_utils


class CommonUtilsTests(unittest.TestCase):
    def test_load_config_accepts_utf8_bom_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmp_dir)
                config = {"campaign_ids": [30761], "account_SID_DK": "sid"}
                with open("config.json", "w", encoding="utf-8-sig") as fh:
                    json.dump(config, fh)

                self.assertEqual(
                    common_utils.load_config(fallback_to_env=False),
                    config,
                )
            finally:
                os.chdir(original_cwd)

    def test_read_json_accepts_utf8_bom_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.json")
            config = {"token_DK": "token"}
            with open(config_path, "w", encoding="utf-8-sig") as fh:
                json.dump(config, fh)

            self.assertEqual(common_utils.read_json(config_path), config)

    def test_create_market_csv_uses_system_temp_directory(self):
        actions_by_state = {
            "OTHER": [{"orderId": 123, "amount": 0, "reason": "OTHER"}],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("tempfile.gettempdir", return_value=tmp_dir):
                csv_path = common_utils.create_market_csv(
                    "DK",
                    actions_by_state,
                    {"OTHER"},
                    "processed",
                )

            self.assertEqual(csv_path, os.path.join(tmp_dir, "DK_processed_results.csv"))
            self.assertTrue(os.path.exists(csv_path))


if __name__ == "__main__":
    unittest.main()
