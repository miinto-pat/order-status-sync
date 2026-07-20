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
        self.get_payloads = []

    def get(self, url, **kwargs):
        self.get_calls.append({"url": url, **kwargs})
        payload = self.get_payloads.pop(0) if self.get_payloads else {"Actions": []}
        return FakeResponse(payload=payload)

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

    def test_ftp_submission_helpers_use_configured_session(self):
        session = FakeSession()
        session.get_payloads = [
            {"FTPFileSubmissions": [{"FileName": "batch.csv", "Status": "Complete"}]},
            {"BatchId": "F-1", "Status": "Complete"},
            {"FTPFileSubmissionErrors": [{"Error": "BAD_DISPOSITION"}]},
        ]
        client = ImpactClient(
            {"account_SID_DK": "sid", "token_DK": "token"},
            "DK",
            session=session,
        )

        submissions = client.list_ftp_submissions()
        submission = client.retrieve_ftp_submission("/Advertisers/sid/FTPFileSubmissions/F-1")
        errors = client.list_ftp_submission_errors("/Advertisers/sid/FTPFileSubmissions/F-1/ErrorDetails")

        self.assertEqual(submissions, [{"FileName": "batch.csv", "Status": "Complete"}])
        self.assertEqual(submission["BatchId"], "F-1")
        self.assertEqual(errors, [{"Error": "BAD_DISPOSITION"}])
        self.assertEqual(len(session.get_calls), 3)


if __name__ == "__main__":
    unittest.main()
