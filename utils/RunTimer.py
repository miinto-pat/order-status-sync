import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone


class RunTimer:
    def __init__(self, run_id=None, context=None):
        self.run_id = run_id
        self.context = context or {}
        self.started_at = datetime.now(timezone.utc)
        self.events = []
        self._lock = threading.Lock()

    @contextmanager
    def measure(self, name, **context):
        start = time.perf_counter()
        event = {
            "name": name,
            "status": "ok",
            "context": context,
        }
        try:
            yield
        except Exception as exc:
            event["status"] = "error"
            event["error_type"] = type(exc).__name__
            raise
        finally:
            event["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
            with self._lock:
                self.events.append(event)

    def totals_by_name(self):
        totals = {}
        with self._lock:
            events = list(self.events)

        for event in events:
            name = event["name"]
            if name not in totals:
                totals[name] = {
                    "count": 0,
                    "total_ms": 0.0,
                    "max_ms": 0.0,
                    "errors": 0,
                }

            totals[name]["count"] += 1
            totals[name]["total_ms"] += event["duration_ms"]
            totals[name]["max_ms"] = max(totals[name]["max_ms"], event["duration_ms"])
            if event["status"] == "error":
                totals[name]["errors"] += 1

        for total in totals.values():
            total["total_ms"] = round(total["total_ms"], 2)
            total["max_ms"] = round(total["max_ms"], 2)

        return totals

    def to_payload(self):
        finished_at = datetime.now(timezone.utc)
        with self._lock:
            events = list(self.events)

        return {
            "run_id": self.run_id,
            "context": self.context,
            "started_at": self.started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "total_duration_ms": round((finished_at - self.started_at).total_seconds() * 1000, 2),
            "event_count": len(events),
            "totals_by_name": self.totals_by_name(),
            "events": events,
        }

    def log_summary(self, logger):
        payload = json.dumps(self.to_payload(), sort_keys=True, ensure_ascii=True)
        logger.info("RUN_TIMING %s", payload)
