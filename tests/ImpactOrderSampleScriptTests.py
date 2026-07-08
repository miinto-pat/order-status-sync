import unittest

import sample_impact_orders


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"Actions": [{"Id": "A1"}, {"Id": "A2"}, {"Id": "A3"}]}


class FakeSession:
    def __init__(self):
        self.get_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append({"url": url, **kwargs})
        return FakeResponse()


class FakeImpactClient:
    username = "account-sid"
    password = "token"

    def __init__(self):
        self.session = FakeSession()

    def local_to_utc_from_campaign(self, campaign_id, start, end):
        return "2026-07-07T00:00:00+00:00", "2026-07-08T23:59:59+00:00"

    def to_impact_datetime_utc(self, value):
        return value.replace("+00:00", "Z")


class ImpactOrderSampleScriptTests(unittest.TestCase):
    def test_campaign_id_for_market_returns_se_campaign(self):
        self.assertEqual(sample_impact_orders.campaign_id_for_market("se"), 30859)

    def test_select_sample_limits_actions(self):
        actions = [{"Id": "A1"}, {"Id": "A2"}, {"Id": "A3"}]

        self.assertEqual(
            sample_impact_orders.select_sample(actions, limit=2),
            [{"Id": "A1"}, {"Id": "A2"}],
        )

    def test_extract_identity_fields_keeps_id_like_fields(self):
        action = {
            "Id": "action-1",
            "Oid": "new-order-id",
            "AdId": "ad-1",
            "CampaignId": 30859,
            "Amount": "12.34",
            "CustomOrderUuid": "uuid-ish",
        }

        self.assertEqual(
            sample_impact_orders.extract_identity_fields(action),
            {
                "AdId": "ad-1",
                "CampaignId": 30859,
                "CustomOrderUuid": "uuid-ish",
                "Id": "action-1",
                "Oid": "new-order-id",
            },
        )

    def test_fetch_single_page_actions_does_not_paginate(self):
        client = FakeImpactClient()

        actions = sample_impact_orders.fetch_single_page_actions(
            client,
            campaign_id=30859,
            start_date="2026-07-07",
            end_date="2026-07-08",
            page_size=5,
        )

        self.assertEqual(actions, [{"Id": "A1"}, {"Id": "A2"}, {"Id": "A3"}])
        self.assertEqual(len(client.session.get_calls), 1)
        call = client.session.get_calls[0]
        self.assertEqual(call["params"]["PageNumber"], 1)
        self.assertEqual(call["params"]["PageSize"], 5)
        self.assertEqual(call["params"]["CampaignId"], 30859)


if __name__ == "__main__":
    unittest.main()
