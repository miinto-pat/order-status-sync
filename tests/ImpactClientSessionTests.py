import unittest

from clients.ImpactClient import ImpactClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = "error"

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.get_calls = []
        self.put_calls = []
        self.delete_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append({"url": url, **kwargs})
        return FakeResponse(payload={"Actions": []})

    def put(self, url, **kwargs):
        self.put_calls.append({"url": url, **kwargs})
        return FakeResponse(payload={"Status": "OK"})

    def delete(self, url, **kwargs):
        self.delete_calls.append({"url": url, **kwargs})
        return FakeResponse(payload={"Status": "OK"})


class ImpactClientSessionTests(unittest.TestCase):
    def test_impact_client_uses_configured_session_for_requests(self):
        session = FakeSession()
        client = ImpactClient(
            {"account_SID_DK": "sid", "token_DK": "token"},
            "DK",
            session=session,
        )
        client.local_to_utc_from_campaign = lambda campaign_id, start, end: (
            "2026-07-07T00:00:00+00:00",
            "2026-07-07T23:59:59+00:00",
        )

        client.get_actions(30761, "2026-07-07", "2026-07-07")
        client.update_action("A1", 10, "OTHER")
        client.reverse_action("A2", 0, "ITEM_RETURNED")

        self.assertEqual(len(session.get_calls), 1)
        self.assertEqual(len(session.put_calls), 1)
        self.assertEqual(len(session.delete_calls), 1)


if __name__ == "__main__":
    unittest.main()
