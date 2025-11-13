from clients.ImpactClient import ImpactClient
from clients.PATAclient import PATAClient
from helpers.logger import get_logger
from utils.CommonUtils import common_utils
from utils.OrderMiiUUID import OrderMiiUUID
from helpers.PATARules import PATARules
logger = get_logger(__name__)

class main:

    def process_single_market(self, campaign_id, market, start_date=None, end_date=None):
        import os
        import json

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        CONFIG_FILE_PATH = os.path.join(BASE_DIR, "config.json")

        # ✅ Load configuration safely (from file or environment)
        data = None
        if os.path.exists(CONFIG_FILE_PATH):
            data = common_utils.read_json(CONFIG_FILE_PATH)
            print("Loaded configuration from config.json")
        else:
            env_json = os.getenv("impact_secret_json", "")
            if env_json:
                try:
                    data = json.loads(env_json)
                    print("Loaded configuration from environment variable (impact_secret_json)")
                except json.JSONDecodeError as e:
                    raise ValueError(f"Failed to decode JSON from impact_secret_json: {e}")
            else:
                raise FileNotFoundError(
                    "No config.json found and impact_secret_json environment variable is not set."
                )

        # Initialize clients
        impact_client = ImpactClient(data, market=market)
        pata_client = PATAClient()

        # ✅ Fetch actions with robust error handling
        try:
            actions = impact_client.get_actions(campaign_id, start_date, end_date)
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                raise PermissionError(f"⚠️ Authorization failed for market {market}. Please check credentials.")
            elif "timeout" in error_msg.lower():
                raise TimeoutError(f"⚠️ Request timed out for market {market}.")
            elif "404" in error_msg:
                raise FileNotFoundError(f"⚠️ Resource not found for market {market}.")
            else:
                raise RuntimeError(f"⚠️ API error for market {market}")

        # Initialize statistics
        stats = {
            "total_actions": len(actions),
            "OTHER": 0,
            "ITEM_RETURNED": 0,
            "ORDER_UPDATE": 0,
            "Not_Modified": 0,
            "Not_Processed": 0,
            "NONE": 0
        }
        not_processed_ids = []
        for idx, action in enumerate(actions):
            try:
                order_id_impact = int(action.get("Oid"))
                action_id = action.get("Id")


                order_uuid_str = OrderMiiUUID(market, order_id_impact).to_uuid_string()
                order = pata_client.retrieve_order(market, order_uuid_str)
                print(f"\nOrder details for {order_uuid_str} ({market}):")
                for key, value in order.items():
                    print(f"  {key}: {value}")

                if not order:
                    stats["Not_Processed"] += 1
                    not_processed_ids.append({"market": market, "action_id": action_id})
                    continue

                reason, amount = PATARules.calculate_action_reason_and_amount(order)
                if amount is None:
                    print(f"⚠️ Skipping action {action_id} for market {market}: amount is None")
                    stats["Not_Modified"] += 1
                    # not_processed_ids.append({"market": market, "action_id": action_id, "reason": "amount_is_none"})
                    continue
                print(f"checking VAT for market: {market}")

                amount_without_vat = common_utils.exclude_VAT(amount,market)


                if reason in ("OTHER", "ITEM_RETURNED"):
                    result = impact_client.reverse_action(action_id, amount_without_vat, reason)
                    print("✅ Returned from reverse_action")
                    print(f"result: {result}")
                    if result is None:
                        stats["Not_Processed"] += 1
                        not_processed_ids.append({"market": market, "action_id": action_id})
                        continue
                    else:
                        stats[reason] += 1

                elif reason == "ORDER_UPDATE":
                    result=impact_client.update_action(action_id, amount_without_vat, reason)
                    print("✅ Returned from update_action")
                    print(f"result: {result}")
                    if result is None:
                        stats["Not_Processed"] += 1
                        not_processed_ids.append({"market": market, "action_id": action_id})
                        continue
                    else:
                        stats[reason] += 1

                else:
                    if reason in stats:
                        stats[reason] += 1

            except Exception as e:
                print(f"❌ Exception while processing action {action_id}: {e}")
                stats["Not_Processed"] += 1
                not_processed_ids.append({"market": market, "action_id": action.get("Id"), "error": str(e)})

        # Calculate Not_Modified
        # Calculate Not_Modified
        stats["Not_Modified"] = stats["total_actions"] - (
                stats["Not_Processed"] + stats["OTHER"] + stats["ITEM_RETURNED"] + stats["ORDER_UPDATE"]
        )

        return {
            "stats": stats,
            "not_processed": not_processed_ids
        }


