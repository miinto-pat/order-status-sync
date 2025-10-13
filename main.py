import json
import os

from flask import jsonify

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
        if os.path.exists(CONFIG_FILE_PATH):
            data = common_utils.read_json(CONFIG_FILE_PATH)
            campaign_ids = data.get("campaign_ids", [])
        else:
            env_json = os.getenv("impact_secret_json", "")
            if env_json:
                try:
                    data = json.loads(env_json)
                    campaign_ids = data.get("campaign_ids", [])
                    print("Loaded campaign IDs from environment variable (impact_secret_json)")
                except json.JSONDecodeError as e:
                    print("Failed to decode JSON from impact_secret_json environment variable:", e)
            else:
                print("No config.json found and impact_secret_json environment variable is not set.")

        print("Campaign IDs:", campaign_ids)

        all_stats = {}

        for campaign_id in campaign_ids:
            market = COUNTRY_CODES_AND_CAMPAIGNS.get(campaign_id)
            impact_client = ImpactClient(CONFIG_FILE_PATH, market)
            pata_client = PATAClient()

            try:
                actions = impact_client.get_actions(campaign_id, start_date, end_date)
            except Exception as e:
                logger.error(f"Failed to get actions for campaign {campaign_id}: {e}")
                # Return None or skip this market
                raise
            # logger.info(f"Total actions retrieved for market {market}: {len(actions)}")

            # ✅ Initialize stats
            stats = {
                "total_actions": len(actions),
                "OTHER": 0,
                "ITEM_RETURNED": 0,
                "ORDER_UPDATE": 0,
                "Not_Modified": 0,
                "Not_Processed":0,
                "NONE":0
            }


            for action in actions:
                order_id_impact = int(action.get("Oid"))
                action_id = action.get("Id")
                order_uuid_str = OrderMiiUUID(market, order_id_impact).to_uuid_string()
                order = pata_client.retrieve_order(market, order_uuid_str)
                if not order:
                    logger.warning(
                        f"Order not processed: market={market}, "
                        f"impact_order_id={order_id_impact}, "
                        f"uuid={order_uuid_str}, action_id={action_id}"
                    )
                    stats['Not_Processed'] += 1
                    continue

                reason, amount = PATARules.calculate_action_reason_and_amount(order)
                if reason in stats and reason=="OTHER" or reason == "ITEM_RETURNED":
                    impact_client.reverse_action(action_id, amount, reason)
                elif  reason in stats and reason == "ORDER_UPDATE":
                    impact_client.update_action(action_id,amount, reason)



                if reason in stats:
                    stats[reason] += 1
                else:
                    # reason is None or unexpected → count in Not_Modified later
                    continue

            # Calculate fully processed actions
            stats["Not_Modified"] = stats["total_actions"] - (
                        stats["Not_Processed"] + stats["OTHER"] + stats["ITEM_RETURNED"] + stats["ORDER_UPDATE"])

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

    def run_main(self):
        try:
            result = self.main()
            if not result:
                # Friendly message for UI
                return jsonify({"message": "Error while retrieving actions"}), 500
            return jsonify({"message": "Bot finished successfully", "stats": result})
        except Exception as e:
            # Log internal details
            logger.exception("Error running bot")
            # Friendly message for UI
            return jsonify({"message": "Error while retrieving actions"}), 500

if __name__ == "__main__":
    main().run_main()
