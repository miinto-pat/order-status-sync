from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import id_token

from constants.Constants import INTERNAL_ORDER_SERVICE_BASE_URL
from helpers.PATARules import PATARules
from helpers.logger import get_logger
from utils.OrderMiiUUID import OrderMiiUUID
import requests
import threading
import time
from urllib.parse import urlencode
logger = get_logger(__name__)

from google.auth import default
from google.auth.transport.requests import Request
from google.auth.impersonated_credentials import IDTokenCredentials

class PATAClient:
    ORDER_EXPANSIONS = ("events", "voucher", "positions", "rma")

    def __init__(self, session=None, clock=None, token_ttl_seconds=3300):
        self.session = session or requests.Session()
        self.clock = clock or time.monotonic
        self.token_ttl_seconds = token_ttl_seconds
        self._token_lock = threading.Lock()
        self._cached_tokens = {}

    def get_id_token(self,audience):
        now = self.clock()
        cached = self._cached_tokens.get(audience)
        if cached and cached["expires_at"] > now:
            return cached["token"]

        with self._token_lock:
            now = self.clock()
            cached = self._cached_tokens.get(audience)
            if cached and cached["expires_at"] > now:
                return cached["token"]

            token = self._fetch_id_token(audience)
            self._cached_tokens[audience] = {
                "token": token,
                "expires_at": now + self.token_ttl_seconds,
            }
            return token

    def _fetch_id_token(self,audience):

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
        query = urlencode(
            [("expansions[]", expansion) for expansion in self.ORDER_EXPANSIONS],
            safe="[]",
        )
        url = (
            f"{INTERNAL_ORDER_SERVICE_BASE_URL}/{market}/orders/{order_id}?{query}"
        )
        logger.info(f"Retrieving order using the new internal service {str(order_id)} {url}")
        try:
            token = self.get_id_token(INTERNAL_ORDER_SERVICE_BASE_URL)

            response = self.session.get(
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



