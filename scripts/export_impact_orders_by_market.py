import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from constants.Constants import COUNTRY_CODES_AND_CAMPAIGNS


def market_campaign_ids(markets=None):
    requested = {market.strip().upper() for market in markets or [] if market.strip()}
    mapping = {
        market: campaign_id
        for campaign_id, market in COUNTRY_CODES_AND_CAMPAIGNS.items()
        if not requested or market in requested
    }
    return dict(sorted(mapping.items()))


def oid_format(order_id):
    value = str(order_id or "").strip()
    if value.isdigit():
        return "numeric"
    if len(value) == 36 and value.count("-") == 4:
        return "uuid"
    return "string"


def extract_market_orders(actions):
    orders_by_id = {}
    for action in actions:
        order_id = action.get("Oid")
        if order_id in (None, ""):
            continue

        order_key = str(order_id)
        order = orders_by_id.setdefault(
            order_key,
            {
                "orderId": order_key,
                "oidFormat": oid_format(order_key),
                "actionIds": [],
                "actionCount": 0,
            },
        )
        action_id = action.get("Id")
        if action_id not in (None, ""):
            order["actionIds"].append(str(action_id))
        order["actionCount"] += 1

    return [orders_by_id[key] for key in sorted(orders_by_id)]


def build_export_payload(start_date, end_date, actions_by_market):
    markets = {}
    total_action_count = 0
    total_unique_order_count = 0

    for market in sorted(actions_by_market):
        actions = actions_by_market[market]
        orders = extract_market_orders(actions)
        campaign_id = market_campaign_ids([market]).get(market)
        markets[market] = {
            "campaign_id": campaign_id,
            "action_count": len(actions),
            "unique_order_count": len(orders),
            "orders": orders,
        }
        total_action_count += len(actions)
        total_unique_order_count += len(orders)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "total_action_count": total_action_count,
        "total_unique_order_count": total_unique_order_count,
        "markets": markets,
    }


def default_output_path():
    return os.path.join(tempfile.gettempdir(), "impact_orders_by_market_june.json")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Export Impact order IDs grouped per market as JSON."
    )
    parser.add_argument("--start", default=f"{date.today().year}-06-01", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end", default=f"{date.today().year}-06-30", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--market", action="append", help="Market code. Can be passed multiple times.")
    parser.add_argument("--output", default=default_output_path(), help="Output JSON path.")
    return parser


def main():
    args = build_parser().parse_args()

    from clients.ImpactClient import ImpactClient
    from utils.CommonUtils import common_utils

    config = common_utils.load_config()
    actions_by_market = {}
    for market, campaign_id in market_campaign_ids(args.market).items():
        client = ImpactClient(config, market=market)
        actions_by_market[market] = client.get_actions(campaign_id, args.start, args.end)

    payload = build_export_payload(args.start, args.end, actions_by_market)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True)

    print(
        json.dumps(
            {
                "output": os.path.abspath(args.output),
                "markets": sorted(payload["markets"]),
                "total_action_count": payload["total_action_count"],
                "total_unique_order_count": payload["total_unique_order_count"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
