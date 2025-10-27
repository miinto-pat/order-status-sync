import requests

from constants.Constants import PATA_BASE_URL
from helpers.PATARules import PATARules
from helpers.logger import get_logger
from utils.OrderMiiUUID import OrderMiiUUID

logger = get_logger(__name__)

class PATAClient():

    def retrieve_order(self,market,order_id):
        market = market.lower()
        url=PATA_BASE_URL + market+ "/order/" + order_id
        logger.info(f"Retrieving order {str(order_id)}")
        try:
            response = requests.get(
                url,
                headers={"Accept": "application/json"}
            )
            if response.status_code != 200:
                logger.error(f"Error {response.status_code}: {response.text}")
                return None

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Error fetching order {str(order_id)}: {e}")
            return None

if __name__ == '__main__':
    PATAClient=PATAClient()
    PATARules=PATARules()
    orders ={153896:"uk",
        372221:"fr",
             2617866:"dk"}
    for order_id, market in orders.items():
        print(f"Order ID: {order_id}, Market: {market}")
        order_uuid = OrderMiiUUID(market, order_id)
        print(str(order_id))
        # order=PATAClient.retrieve_order("dk","8637e025-ae91-48de-002D-00000027FC17")
        order=PATAClient.retrieve_order(market,str(order_uuid))
        reason, amount =PATARules.calculate_action_reason_and_amount(order)
        print(f"Order Id: {order_id}, Reason: {reason}, Amount: {amount}")



