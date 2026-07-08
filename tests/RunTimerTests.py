import json
import unittest

from utils.RunTimer import RunTimer


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append(message % args)


class RunTimerTests(unittest.TestCase):
    def test_measure_records_event_context_and_duration(self):
        timer = RunTimer(run_id="run-1")

        with timer.measure("step.name", market="DK", count=3):
            pass

        self.assertEqual(len(timer.events), 1)
        event = timer.events[0]
        self.assertEqual(event["name"], "step.name")
        self.assertEqual(event["status"], "ok")
        self.assertEqual(event["context"], {"market": "DK", "count": 3})
        self.assertGreaterEqual(event["duration_ms"], 0)

    def test_measure_records_error_and_reraises(self):
        timer = RunTimer(run_id="run-1")

        with self.assertRaises(ValueError):
            with timer.measure("broken.step"):
                raise ValueError("boom")

        self.assertEqual(timer.events[0]["status"], "error")
        self.assertEqual(timer.events[0]["error_type"], "ValueError")

    def test_log_summary_writes_json_payload(self):
        timer = RunTimer(run_id="run-1")
        logger = FakeLogger()

        with timer.measure("step.name"):
            pass

        timer.log_summary(logger)

        self.assertEqual(len(logger.messages), 1)
        prefix, payload = logger.messages[0].split(" ", 1)
        self.assertEqual(prefix, "RUN_TIMING")
        data = json.loads(payload)
        self.assertEqual(data["run_id"], "run-1")
        self.assertEqual(data["event_count"], 1)
        self.assertIn("step.name", data["totals_by_name"])


if __name__ == "__main__":
    unittest.main()
