import datetime
import os

import requests
from requests.auth import HTTPBasicAuth

from constants.Constants import BASE_URL, COUNTRY_CODES_AND_CAMPAIGNS
from helpers.logger import get_logger
from utils.CommonUtils import common_utils

logger = get_logger(__name__)

class ImpactClient:
    def __init__(self,data, market):
        if isinstance(data, str):  # path to config file
            self.config = common_utils.read_json(data)
            print(data)
            print(self.config)
        else:  # already a dictionary
            self.config = data
        account_SID = f"account_SID_{market}"
        print(f"SID: {account_SID}")
        token = f"token_{market}"
        print(f"token: {token}")

        self.username = self.config.get(account_SID)
        self.password = self.config.get(token)



    def get_actions(self,campaign_id, start_date, end_date, page_size=1000, page_number=1):
        print(self.username)
        print(BASE_URL)
        url=BASE_URL+self.username+"/Actions?"
        if isinstance(end_date, str):
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str=common_utils.format_date(end_date_str)
        start_date_str=common_utils.format_date(start_date_str)
        params = {
            "ActionDateStart": start_date_str,
            "ActionDateEnd": end_date_str,
            "ActionStatus": "APPROVED,PENDING,TRACKING",
            "PageSize":page_size,
            "PageNumber":page_number,
            "CampaignId":campaign_id
        }

        all_actions = []
        while True:
            try:
                response = requests.get(
                    url,
                    auth=HTTPBasicAuth(self.username, self.password),
                    headers={"Accept": "application/json"},
                    params=params
                )
                if response.status_code != 200:
                    logger.error(f"Error {response.status_code}: {response.text}")
                    raise ValueError(f"Error {response.status_code}: {response.text}")


                data = response.json()
                actions = data.get("Actions", [])
                all_actions.extend(actions)

                logger.info(
                    f"Campaign {campaign_id}: Retrieved {len(actions)} actions "
                    f"(page {params['PageNumber']})."
                )

                # Stop if less than PageSize returned (no more pages)
                if len(actions) < params["PageSize"]:
                    break

                params["PageNumber"] += 1

            except requests.RequestException as e:
                raise ValueError(f"Error fetching actions: {e}")


        return all_actions


    def retrieve_action(self,action_id):
        url=BASE_URL+self.username+"/Actions/"+action_id
        logger.info(f"Retrieving action {action_id}")
        try:
            response = requests.get(
                url,
                auth=HTTPBasicAuth(self.username, self.password),
                headers={"Accept": "application/json"}
            )
            if response.status_code != 200:
                logger.error(f"Error {response.status_code}: {response.text}")
                logger.error(
                    f"Failed to retrieve action {action_id} "
                    f"(status {response.status_code}). Response: {response.text}"
                )
                return None

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Error fetching action {action_id}: {e}")
            return None

    def update_action(self,action_id,amount,reason):
        url=BASE_URL+self.username+"/Actions/"+action_id
        logger.info(f"Retrieving action {action_id}")
        body={
            "ActionId":action_id,
            "Amount":amount,
            "Reason":reason

        }
        try:
            response = requests.put(
                url,
                auth = HTTPBasicAuth(self.username, self.password),
                headers = {"Accept": "application/json"},
                data = body
            )
            if response.status_code != 200:
                logger.error(f"Error {response.status_code}: {response.text}")
                return None

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Error updating action {action_id}: {e}")
            return None

    def reverse_action(self, action_id, amount, reason):
        url = BASE_URL + self.username + "/Actions"
        logger.info(f"Retrieving action {action_id}")
        body = {
            "ActionId": action_id,
            "Amount": amount,
            "Reason": reason

        }
        try:
            response = requests.delete(
                url,
                auth=HTTPBasicAuth(self.username, self.password),
                headers={"Accept": "application/json"},
                data=body
            )
            if response.status_code != 200:
                logger.error(f"Error {response.status_code}: {response.text}")
                return None

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Error updating action {action_id}: {e}")
            return None


if __name__=="__main__":
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CONFIG_FILE_PATH = os.path.join(BASE_DIR, "config.json")
    market="DK"
    impact_client=ImpactClient(CONFIG_FILE_PATH,market)
    campaign_ids=impact_client.campaign_ids
    for campaign_id in campaign_ids:
        actions = impact_client.get_actions(campaign_id)
        logger.info(f"Total actions retrieved for campaign {campaign_id}: {len(actions)}")

        action_id=actions[0].get("Id")
        action=impact_client.retrieve_action(action_id)
        if action:
            print("Retrieved action:")
            print(action)
        else:
            logger.warning(f"Could not retrieve action {action_id}")