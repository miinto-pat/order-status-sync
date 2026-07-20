import os
import unittest

from main import _emit_progress, _get_impact_delivery_mode, _get_pata_max_workers


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

    def test_impact_delivery_mode_defaults_to_rest(self):
        old_value = os.environ.pop("IMPACT_DELIVERY_MODE", None)
        try:
            self.assertEqual(_get_impact_delivery_mode({}), "rest")
        finally:
            if old_value is not None:
                os.environ["IMPACT_DELIVERY_MODE"] = old_value

    def test_impact_delivery_mode_accepts_batch_sftp_from_config(self):
        old_value = os.environ.pop("IMPACT_DELIVERY_MODE", None)
        try:
            self.assertEqual(
                _get_impact_delivery_mode({"impact_delivery_mode": "batch_sftp"}),
                "batch_sftp",
            )
        finally:
            if old_value is not None:
                os.environ["IMPACT_DELIVERY_MODE"] = old_value

    def test_emit_progress_sends_event_payload_to_callback(self):
        events = []

        _emit_progress(events.append, "action_completed", market="DK", processed_actions=3)

        self.assertEqual(
            events,
            [{"event": "action_completed", "market": "DK", "processed_actions": 3}],
        )

    def test_emit_progress_ignores_missing_callback(self):
        _emit_progress(None, "action_completed", market="DK")


if __name__ == "__main__":
    unittest.main()
