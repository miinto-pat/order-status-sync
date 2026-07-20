import unittest

from utils.ProgressTracker import ProgressTracker


class ProgressTrackerTests(unittest.TestCase):
    def test_snapshot_starts_with_pending_markets(self):
        tracker = ProgressTracker(["DK", "FR"])
        tracker.start_run()

        snapshot = tracker.snapshot()

        self.assertEqual(snapshot["total_markets"], 2)
        self.assertEqual(snapshot["completed_markets"], 0)
        self.assertEqual(snapshot["percent"], 0)
        self.assertEqual(snapshot["markets"]["DK"]["status"], "pending")

    def test_action_progress_contributes_to_overall_percent(self):
        tracker = ProgressTracker(["DK", "FR"])

        tracker.start_market("DK")
        tracker.actions_loaded("DK", 10)
        tracker.action_completed("DK", 4, {"total_actions": 10, "ORDER_UPDATE": 2, "Not_Modified": 1, "Not_Processed": 1})

        snapshot = tracker.snapshot()

        self.assertEqual(snapshot["percent"], 20.0)
        self.assertEqual(snapshot["processed_actions"], 4)
        self.assertEqual(snapshot["remaining_actions"], 6)
        self.assertEqual(snapshot["successful_actions"], 2)
        self.assertEqual(snapshot["skipped_actions"], 1)
        self.assertEqual(snapshot["error_actions"], 1)

    def test_finished_market_counts_as_complete(self):
        tracker = ProgressTracker(["DK", "FR"])

        tracker.start_market("DK")
        tracker.actions_loaded("DK", 3)
        tracker.finish_market("DK", {"total_actions": 3, "OTHER": 1, "ITEM_RETURNED": 1, "ORDER_UPDATE": 1})

        snapshot = tracker.snapshot()

        self.assertEqual(snapshot["percent"], 50.0)
        self.assertEqual(snapshot["completed_markets"], 1)
        self.assertEqual(snapshot["markets"]["DK"]["remaining_actions"], 0)


if __name__ == "__main__":
    unittest.main()
