from clients.ImpactClient import ImpactClient
from clients.PATAclient import PATAClient
from helpers.logger import get_logger
from utils.CommonUtils import common_utils
from utils.OrderMiiUUID import OrderMiiUUID
from helpers.PATARules import PATARules
import os
import json
logger = get_logger(__name__)

class main:

    def process_single_market(self, campaign_id, market, start_date=None, end_date=None):


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
                raise FileNotFoundError(f"Resource not found for market {market}.")
            else:
                raise RuntimeError(f"API error for market {market}")

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
        # Track action IDs for each state
        actions_by_state = {
            "OTHER": [],
            "ITEM_RETURNED": [],
            "ORDER_UPDATE": [],
            "Not_Modified": [],
            "Not_Processed": [],
            "NONE": []
        }
        export_rows = []
        not_processed_ids = []
        for idx, action in enumerate(actions):
            try:
                order_id_impact = int(action.get("Oid"))
                ad_id_impact = int(action.get("AdId"))

                action_id = action.get("Id")


                order_uuid_str = OrderMiiUUID(market, order_id_impact).to_uuid_string()
                order = pata_client.retrieve_order(market, order_uuid_str)
                print(f"\nOrder details for {order_id_impact}, {order_uuid_str} ({market}):")
                for key, value in order.items():
                    print(f"  {key}: {value}")

                if not order:
                    stats["Not_Processed"] += 1
                    not_processed_ids.append({"market": market, "action_id": action_id})
                    print(f"Order couldn't be retrieved from PATA /not processed {order_uuid_str}")
                    # actions_by_state["Not_Processed"].append(order_uuid_str)
                    actions_by_state["Not_Processed"].append({
                        "orderId": order_id_impact,
                        "amount": None,
                        "reason": "Failed to process order"})
                    continue

                reason, amount = PATARules.calculate_action_reason_and_amount(order)
                if amount is None:
                    print(f"⚠️ Skipping action {action_id} for market {market}: amount is None")
                    stats["Not_Modified"] += 1
                    # not_processed_ids.append({"market": market, "action_id": action_id, "reason": "amount_is_none"})
                    continue
                print(f"checking VAT for market: {market}")
                print(f"amount with VAT:{amount}")

                amount_without_vat = common_utils.exclude_VAT(amount,market)
                print(f"amount after VAT:{amount_without_vat}")

                export_rows.append({
                    "orderId": order_id_impact,
                    "amount": amount_without_vat,
                    "reason": reason
                })

                if reason in ("OTHER", "ITEM_RETURNED"):
                    result = impact_client.reverse_action(action_id, amount_without_vat, reason)
                    print("✅ Returned from reverse_action")
                    print(f"result: {result}")
                    if result is None:
                        stats["Not_Processed"] += 1
                        not_processed_ids.append({"market": market, "action_id": order_id_impact})
                        # actions_by_state["Not_Processed"].append(order_uuid_str)
                        actions_by_state["Not_Processed"].append({
                            "orderId": order_id_impact,
                            "amount": None,
                            "reason": "Not Processed"})
                        print(f"Order couldn't be reversed  /not processed {order_uuid_str} {order_id_impact} {result}")

                        continue
                    else:
                        stats[reason] += 1
                        actions_by_state[reason].append({
                            "orderId": order_id_impact,
                            "amount": amount_without_vat,
                            "reason": reason})


                elif reason == "ORDER_UPDATE":
                    result=impact_client.update_action(action_id, amount_without_vat, reason)
                    print("✅ Returned from update_action")
                    print(f"result: {result}")
                    if result is None:
                        stats["Not_Processed"] += 1
                        not_processed_ids.append({"market": market, "action_id": order_id_impact})
                        # actions_by_state["Not_Processed"].append(order_uuid_str)
                        actions_by_state["Not_Processed"].append({
                            "orderId": order_id_impact,
                            "amount": None,
                            "reason": "Not Processed"})
                        print(f"Order couldn't be updated  /not processed {order_uuid_str} {order_id_impact} {result}")
                        continue
                    else:
                        stats[reason] += 1
                        # actions_by_state[reason].append(order_id_impact)
                        actions_by_state[reason].append({
                            "orderId": order_id_impact,
                            "amount": amount_without_vat,
                            "reason": reason})


                else:
                    if reason in stats:
                        stats[reason] += 1
                        # actions_by_state[reason].append(order_id_impact)
                        actions_by_state[reason].append({
                            "orderId": order_id_impact,
                            "amount": amount_without_vat,
                            "reason": reason})


            except Exception as e:
                print(f"❌ Exception while processing action {order_id_impact}: {e}")
                stats["Not_Processed"] += 1
                not_processed_ids.append({"market": market, "action_id": action.get("Id"), "error": str(e)})
                actions_by_state["Not_Processed"].append({
                    "orderId": order_id_impact,
                    "amount": None,
                    "reason": "Not Processed"})
                # actions_by_state["Not_Processed"].append(order_uuid_str)
                print(f"Order couldn't be processed {order_id_impact} {order_id_impact} ")

        # Calculate Not_Modified
        stats["Not_Modified"] = stats["total_actions"] - (
                stats["Not_Processed"] + stats["OTHER"] + stats["ITEM_RETURNED"] + stats["ORDER_UPDATE"]
        )
        print(f"not modified: {stats["Not_Modified"]}")
        all_processed_ids = (
                actions_by_state["OTHER"] +
                actions_by_state["ITEM_RETURNED"] +
                actions_by_state["ORDER_UPDATE"] +
                actions_by_state["Not_Processed"]
        )
        for action in actions:
            action_id = action.get("Id")
            # order_id = action.get("AdId")
            order_id = action.get("Oid")

            if action_id not in all_processed_ids:
                actions_by_state["Not_Modified"].append({
                    "orderId": order_id,
                    "amount": None,
                    "reason": "Not Modified"})

        print("\n=== Action IDs by state ===")
        for state, records in actions_by_state.items():
            for record in records:
                order_id = record.get("orderId")
                amount = record.get("amount")
                print(f"{order_id}, {amount}, {state}")


        print(actions_by_state)
        print(not_processed_ids)
        return {
            "stats": stats,
            "not_processed": not_processed_ids,
            "actions_by_state": actions_by_state
        }


