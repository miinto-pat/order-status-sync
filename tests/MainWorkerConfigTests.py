import os
import unittest

from main import _get_pata_max_workers


class MainWorkerConfigTests(unittest.TestCase):
    def test_worker_count_defaults_to_five(self):
        old_value = os.environ.pop("PATA_MAX_WORKERS", None)
        try:
            self.assertEqual(_get_pata_max_workers({}), 5)
        finally:
            if old_value is not None:
                os.environ["PATA_MAX_WORKERS"] = old_value

    def test_worker_count_uses_config_value(self):
        old_value = os.environ.pop("PATA_MAX_WORKERS", None)
        try:
            self.assertEqual(_get_pata_max_workers({"pata_max_workers": 3}), 3)
        finally:
            if old_value is not None:
                os.environ["PATA_MAX_WORKERS"] = old_value

    def test_worker_count_env_overrides_config_value(self):
        old_value = os.environ.get("PATA_MAX_WORKERS")
        try:
            os.environ["PATA_MAX_WORKERS"] = "2"
            self.assertEqual(_get_pata_max_workers({"pata_max_workers": 7}), 2)
        finally:
            if old_value is None:
                os.environ.pop("PATA_MAX_WORKERS", None)
            else:
                os.environ["PATA_MAX_WORKERS"] = old_value


if __name__ == "__main__":
    unittest.main()
