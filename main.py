import os

from clients.ImpactClient import ImpactClient
from clients.PATAclient import PATAClient
from constants.Constants import COUNTRY_CODES_AND_CAMPAIGNS
from helpers.logger import get_logger
from utils.CommonUtils import common_utils
from utils.OrderMiiUUID import OrderMiiUUID
from helpers.PATARules import PATARules
logger = get_logger(__name__)

class main:

    def main(self,start_date=None, end_date=None):
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        CONFIG_FILE_PATH = os.path.join(BASE_DIR, "config.json")
        data = common_utils.read_json(CONFIG_FILE_PATH)
        campaign_ids = data.get("campaign_ids", [])
        print("Campaign IDs:", campaign_ids)

        all_stats = {}

        for campaign_id in campaign_ids:
            market = COUNTRY_CODES_AND_CAMPAIGNS.get(campaign_id)
            impact_client = ImpactClient(CONFIG_FILE_PATH, market)
            pata_client = PATAClient()

            actions = impact_client.get_actions(campaign_id, start_date, end_date)
            # logger.info(f"Total actions retrieved for market {market}: {len(actions)}")

            # ✅ Initialize stats
            stats = {
                "total_actions": len(actions),
                "OTHER": 0,
                "ITEM_RETURNED": 0,
                "ORDER_UPDATE": 0,
                "Not_Modified": 0,
                "NONE":0
            }


            for action in actions:
                order_id_impact = int(action.get("Oid"))
                order_uuid_str = OrderMiiUUID(market, order_id_impact).to_uuid_string()
                order = pata_client.retrieve_order(market, order_uuid_str)

                reason, amount = PATARules.calculate_action_reason_and_amount(order)

                if reason in stats:
                    stats[reason] += 1
                else:
                    # reason is None or unexpected → count in Not_Modified later
                    continue

            # Calculate fully processed actions
            stats["Not_Modified"] = stats["total_actions"] - (
                        stats["OTHER"] + stats["ITEM_RETURNED"] + stats["ORDER_UPDATE"])

            all_stats[market] = stats

            # ✅ Print/Log summary for this market
            # logger.info(f"Summary for market {market}:")
            # logger.info(f"  Total actions: {stats['total_actions']}")
            # logger.info(f"  Processed: {stats['processed']}")
            # logger.info(f"  OTHER: {stats['OTHER']}")
            # logger.info(f"  ITEM_RETURNED: {stats['ITEM_RETURNED']}")
            # logger.info(f"  ORDER_UPDATE: {stats['ORDER_UPDATE']}")
            # logger.info(f"  NONE: {stats['NONE']}")
        return all_stats


if __name__ == "__main__":
    main().main()
