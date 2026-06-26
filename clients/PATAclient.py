from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import id_token

from constants.Constants import INTERNAL_ORDER_SERVICE_BASE_URL
from helpers.PATARules import PATARules
from helpers.logger import get_logger
from utils.OrderMiiUUID import OrderMiiUUID
import requests
logger = get_logger(__name__)

from google.auth import default
from google.auth.transport.requests import Request
from google.auth.impersonated_credentials import IDTokenCredentials

class PATAClient:

    def get_id_token(self,audience):

        try:
            return id_token.fetch_id_token(Request(), audience)

        except DefaultCredentialsError as e:
            creds, _ = default()

            id_creds = IDTokenCredentials(
                target_credentials=creds,
                target_audience=audience,
                include_email=True,
            )

            id_creds.refresh(Request())
            print(id_creds.token)
            return id_creds.token



    def retrieve_order(self,market,order_id):
        market = market.lower()
        url = (
        f"{INTERNAL_ORDER_SERVICE_BASE_URL}/{market}/orders/{order_id}?expansions[]=all"
    )
        logger.info(f"Retrieving order using the new internal service {str(order_id)}")
        try:
            token = self.get_id_token(INTERNAL_ORDER_SERVICE_BASE_URL)

            response = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}"
                },
                timeout=30,
            )

            if not response.ok:
                logger.error(f"Error {response.status_code}: {response.text}")
                return None

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Error fetching order {str(order_id)}: {e}")
            return None

if __name__ == '__main__':
    PATAClient=PATAClient()
    PATARules=PATARules()
    orders ={
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



