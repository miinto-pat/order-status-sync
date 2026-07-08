import argparse
import json
from datetime import date, timedelta

from requests.auth import HTTPBasicAuth

from constants.Constants import BASE_URL, COUNTRY_CODES_AND_CAMPAIGNS


IDENTITY_FIELD_NAMES = {
    "AdId",
    "CampaignId",
    "Id",
    "Oid",
}


def campaign_id_for_market(market):
    normalized_market = market.strip().upper()
    for campaign_id, market_code in COUNTRY_CODES_AND_CAMPAIGNS.items():
        if market_code == normalized_market:
            return campaign_id
    raise ValueError(f"Unknown market: {market}")


def select_sample(actions, limit):
    return list(actions[: max(0, limit)])


def extract_identity_fields(action):
    return {
        key: action[key]
        for key in sorted(action)
        if key in IDENTITY_FIELD_NAMES or "id" in key.lower()
    }


def fetch_single_page_actions(client, campaign_id, start_date, end_date, page_size):
    start_utc, end_utc = client.local_to_utc_from_campaign(campaign_id, start_date, end_date)
    url = BASE_URL + client.username + "/Actions?"
    params = {
        "ActionDateStart": client.to_impact_datetime_utc(start_utc),
        "ActionDateEnd": client.to_impact_datetime_utc(end_utc),
        "PageSize": max(1, page_size),
        "PageNumber": 1,
        "CampaignId": campaign_id,
    }
    response = client.session.get(
        url,
        auth=HTTPBasicAuth(client.username, client.password),
        headers={"Accept": "application/json"},
        params=params,
    )
    if response.status_code != 200:
        raise ValueError(f"Impact API error {response.status_code}: {response.text}")
    return response.json().get("Actions", [])


def default_start_date():
    return (date.today() - timedelta(days=1)).isoformat()


def default_end_date():
    return date.today().isoformat()


def build_parser():
    parser = argparse.ArgumentParser(
        description="Fetch a small sample of Impact actions for inspecting order ID fields."
    )
    parser.add_argument("--market", default="SE", help="Market code, e.g. SE, DK, FR.")
    parser.add_argument("--start", default=default_start_date(), help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end", default=default_end_date(), help="End date in YYYY-MM-DD format.")
    parser.add_argument("--limit", type=int, default=5, help="How many actions to print.")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print only ID-like fields instead of full action JSON.",
    )
    return parser


def main():
    args = build_parser().parse_args()
    market = args.market.strip().upper()
    campaign_id = campaign_id_for_market(market)

    from clients.ImpactClient import ImpactClient
    from utils.CommonUtils import common_utils

    config = common_utils.load_config()
    client = ImpactClient(config, market=market)
    actions = fetch_single_page_actions(
        client,
        campaign_id,
        args.start,
        args.end,
        page_size=max(1, args.limit),
    )
    sample = select_sample(actions, args.limit)

    print(
        json.dumps(
            {
                "market": market,
                "campaign_id": campaign_id,
                "start": args.start,
                "end": args.end,
                "retrieved_actions": len(actions),
                "printed_actions": len(sample),
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    for index, action in enumerate(sample, start=1):
        print(f"\n--- ACTION {index} ID FIELDS ---")
        print(json.dumps(extract_identity_fields(action), indent=2, ensure_ascii=False, sort_keys=True))

        if not args.summary_only:
            print(f"\n--- ACTION {index} FULL JSON ---")
            print(json.dumps(action, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
