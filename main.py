from clients.ImpactClient import ImpactClient
from clients.PATAclient import PATAClient
from helpers.logger import get_logger
from utils.CommonUtils import common_utils
from utils.OrderMiiUUID import OrderMiiUUID
from helpers.PATARules import PATARules
import os
import json
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
logger = get_logger(__name__)


def _measure(timer, name, **context):
    if timer is None:
        return nullcontext()
    return timer.measure(name, **context)


def _get_pata_max_workers(config):
    value = os.getenv("PATA_MAX_WORKERS")
    if value is None and config:
        value = config.get("pata_max_workers") or config.get("PATA_MAX_WORKERS")

    if value is None:
        return 5

    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        logger.warning("Invalid PATA_MAX_WORKERS value %r. Falling back to 5.", value)
        return 5


def _retrieve_pata_order(pata_client, market, order_uuid_str, campaign_id, action_id, order_id_impact, timer):
    with _measure(
        timer,
        "pata.retrieve_order",
        campaign_id=campaign_id,
        market=market,
        action_id=action_id,
        order_id=order_id_impact,
    ):
        return pata_client.retrieve_order(market, order_uuid_str)


class main:

    def process_single_market(self, campaign_id, market, start_date=None, end_date=None, timer=None):


        with _measure(timer, "market.config_load", campaign_id=campaign_id, market=market):
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            CONFIG_FILE_PATH = os.path.join(BASE_DIR, "config.json")

            # Load configuration safely (from file or environment)
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
        with _measure(timer, "market.init_clients", campaign_id=campaign_id, market=market):
            impact_client = ImpactClient(data, market=market)
            pata_client = PATAClient()
            pata_max_workers = _get_pata_max_workers(data)
            logger.info("Using %s PATA worker(s) for market %s.", pata_max_workers, market)

        # ✅ Fetch actions with robust error handling
        try:
            with _measure(timer, "impact.get_actions", campaign_id=campaign_id, market=market):
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
        pata_order_futures = {}
        executor = None

        if actions and pata_max_workers > 1:
            executor = ThreadPoolExecutor(max_workers=pata_max_workers)
            for idx, action in enumerate(actions):
                try:
                    order_id_impact = int(action.get("Oid"))
                    action_id = action.get("Id")
                    order_uuid_str = OrderMiiUUID(market, order_id_impact).to_uuid_string()
                except Exception:
                    continue

                pata_order_futures[idx] = executor.submit(
                    _retrieve_pata_order,
                    pata_client,
                    market,
                    order_uuid_str,
                    campaign_id,
                    action_id,
                    order_id_impact,
                    timer,
                )

        for idx, action in enumerate(actions):
            try:
                order_id_impact = int(action.get("Oid"))
                ad_id_impact = int(action.get("AdId"))

                action_id = action.get("Id")


                order_uuid_str = OrderMiiUUID(market, order_id_impact).to_uuid_string()
                if idx in pata_order_futures:
                    order = pata_order_futures[idx].result()
                else:
                    order = _retrieve_pata_order(
                        pata_client,
                        market,
                        order_uuid_str,
                        campaign_id,
                        action_id,
                        order_id_impact,
                        timer,
                    )
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

                with _measure(
                    timer,
                    "rules.calculate_action_reason_and_amount",
                    campaign_id=campaign_id,
                    market=market,
                    action_id=action_id,
                    order_id=order_id_impact,
                ):
                    reason, amount = PATARules.calculate_action_reason_and_amount(order)
                if amount is None:
                    print(f"⚠️ Skipping action {action_id} for market {market}: amount is None")
                    stats["Not_Modified"] += 1
                    # not_processed_ids.append({"market": market, "action_id": action_id, "reason": "amount_is_none"})
                    continue
                print(f"checking VAT for market: {market}")
                print(f"amount with VAT:{amount}")

                with _measure(
                    timer,
                    "vat.exclude",
                    campaign_id=campaign_id,
                    market=market,
                    action_id=action_id,
                    order_id=order_id_impact,
                ):
                    amount_without_vat = common_utils.exclude_VAT(amount,market)
                print(f"amount after VAT:{amount_without_vat}")

                export_rows.append({
                    "orderId": order_id_impact,
                    "amount": amount_without_vat,
                    "reason": reason
                })

                if reason in ("OTHER", "ITEM_RETURNED"):
                    with _measure(
                        timer,
                        "impact.reverse_action",
                        campaign_id=campaign_id,
                        market=market,
                        action_id=action_id,
                        order_id=order_id_impact,
                        reason=reason,
                    ):
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
                    with _measure(
                        timer,
                        "impact.update_action",
                        campaign_id=campaign_id,
                        market=market,
                        action_id=action_id,
                        order_id=order_id_impact,
                        reason=reason,
                    ):
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

        if executor is not None:
            executor.shutdown(wait=True)

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


