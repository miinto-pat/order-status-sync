import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock

from clients.PATAclient import PATAClient


class FakeResponse:
    ok = True
    status_code = 200
    text = ""

    def json(self):
        return {"data": {"id": "order-1"}}


class FakeSession:
    def __init__(self):
        self.get_calls = []

    def get(self, url, headers=None, timeout=None):
        self.get_calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse()


class PATAClientTests(unittest.TestCase):
    def test_get_id_token_reuses_cached_token_until_ttl_expires(self):
        now = [1000]
        client = PATAClient(clock=lambda: now[0], token_ttl_seconds=60)
        client._fetch_id_token = Mock(return_value="token-1")

        self.assertEqual(client.get_id_token("audience"), "token-1")
        self.assertEqual(client.get_id_token("audience"), "token-1")
        self.assertEqual(client._fetch_id_token.call_count, 1)

        now[0] = 1061
        client._fetch_id_token.return_value = "token-2"

        self.assertEqual(client.get_id_token("audience"), "token-2")
        self.assertEqual(client._fetch_id_token.call_count, 2)

    def test_retrieve_order_uses_configured_session_and_bearer_token(self):
        session = FakeSession()
        client = PATAClient(session=session)
        client.get_id_token = Mock(return_value="cached-token")

        result = client.retrieve_order("FR", "order-1")

        self.assertEqual(result, {"data": {"id": "order-1"}})
        self.assertEqual(len(session.get_calls), 1)
        call = session.get_calls[0]
        self.assertIn("/fr/orders/order-1", call["url"])
        self.assertEqual(call["headers"], {"Authorization": "Bearer cached-token"})
        self.assertEqual(call["timeout"], 30)

    def test_retrieve_order_requests_only_expansions_used_by_rules(self):
        session = FakeSession()
        client = PATAClient(session=session)
        client.get_id_token = Mock(return_value="cached-token")

        client.retrieve_order("FR", "order-1")

        parsed = urlparse(session.get_calls[0]["url"])
        query = parse_qs(parsed.query)
        self.assertEqual(
            query.get("expansions[]"),
            ["events", "voucher", "positions", "rma"],
        )
        self.assertNotIn("all", query.get("expansions[]", []))


if __name__ == "__main__":
    unittest.main()
