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

    def main(self):
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        CONFIG_FILE_PATH = os.path.join(BASE_DIR, "config.json")
        data = common_utils.read_json(CONFIG_FILE_PATH)
        campaign_ids = data.get("campaign_ids", [])
        print("Campaign IDs:", campaign_ids)


        for campaign_id in campaign_ids:
            market = COUNTRY_CODES_AND_CAMPAIGNS.get(campaign_id)
            impact_client = ImpactClient(CONFIG_FILE_PATH,market)
            pata_client = PATAClient()
            actions = impact_client.get_actions(campaign_id)
            logger.info(f"Total actions retrieved for market {market}: {len(actions)}")
            for action in actions:
                order_id_impact=int(action.get("Oid"))
                logger.info(f"Order ID from impact: {order_id_impact}")
                order_uuid = OrderMiiUUID(market, order_id_impact)
                order_uuid_str=order_uuid.to_uuid_string()
                order=pata_client.retrieve_order(market,order_uuid_str)
                print(order)
                order_id_pata = order.get("data", {}).get("orderId")
                logger.info(f"Order ID from PATA: {order_id_pata}")
                if order_id_impact!=order_id_pata:
                    logger.info(f"Order ID mismatch")
                print(PATARules.calculate_action_reason_and_amount(order))



if __name__ == "__main__":
    main().main()
