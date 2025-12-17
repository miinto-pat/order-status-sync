from datetime import datetime, date, time, timezone

import os
from zoneinfo import ZoneInfo
import pytz

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

    countries = {
        "Germany": "Europe/Berlin",
        "France": "Europe/Paris",
        "UK": "Europe/London",
        "USA": "America/New_York"
    }

    def local_to_utc_from_campaign(self,campaign_id, local_start_str, local_end_str):
        """
        local_start_str, local_end_str: strings in "YYYY-MM-DD" format
        """
        MARKET_TIMEZONES = {
            "DE": "Europe/Berlin",
            "FR": "Europe/Paris",
            "UK": "Europe/London",
            "DK": "Europe/Copenhagen",
            "NO": "Europe/Oslo",
            "BE": "Europe/Brussels",
            "NL": "Europe/Amsterdam",
            "SE": "Europe/Stockholm",
            "IT": "Europe/Rome",
            "ES": "Europe/Madrid",
            "PL": "Europe/Warsaw"
        }
        # Parse strings to date objects
        local_start = datetime.strptime(local_start_str, "%Y-%m-%d").date()
        local_end = datetime.strptime(local_end_str, "%Y-%m-%d").date()

        market_code = COUNTRY_CODES_AND_CAMPAIGNS.get(campaign_id)
        if market_code is None:
            raise ValueError(f"Unknown campaign ID: {campaign_id}")

        tz_name = MARKET_TIMEZONES.get(market_code)
        if tz_name is None:
            raise ValueError(f"No timezone found for market code: {market_code}")

        tz = ZoneInfo(tz_name)

        # Combine date + time, pass tzinfo directly
        start_local = datetime.combine(local_start, time.min, tzinfo=tz)
        end_local = datetime.combine(local_end, time.max, tzinfo=tz)

        # Convert to UTC
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc = end_local.astimezone(ZoneInfo("UTC"))

        return start_utc.isoformat(), end_utc.isoformat()

        market_code = constants.Constants.COUNTRY_CODES_AND_CAMPAIGNS.get(campaign_id)
        if market_code is None:
            raise ValueError(f"Unknown campaign ID: {campaign_id}")

        tz_name = MARKET_TIMEZONES.get(market_code)
        if tz_name is None:
            raise ValueError(f"No timezone found for market code: {market_code}")

        tz = ZoneInfo(tz_name)

        start_local = datetime.combine(local_start, time.min, tzinfo=tz)
        end_local = datetime.combine(local_end, time.max, tzinfo=tz)

        # Convert to UTC
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc = end_local.astimezone(ZoneInfo("UTC"))

        return start_utc.isoformat(), end_utc.isoformat()

    from datetime import datetime

    def to_impact_datetime_utc(self,value):
        """
        Accepts datetime or ISO string
        Returns Impact-compatible UTC timestamp string with Z
        """
        if isinstance(value, str):
            value = datetime.fromisoformat(value)

        # # Ensure UTC
        # if value.tzinfo is None:
        #     from datetime import timezone
        #     value = value.replace(tzinfo=timezone.utc)
        # else:
        #     value = value.astimezone(timezone.utc)

        # Format without microseconds, add Z
        return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


    def get_actions(self,campaign_id, start_date, end_date, page_size=1000, page_number=1):
        start_utc, end_utc = self.local_to_utc_from_campaign(campaign_id, start_date, end_date)
        print(start_utc, end_utc)

        url=BASE_URL+self.username+"/Actions?"

        start_param = self.to_impact_datetime_utc(start_utc)
        end_param = self.to_impact_datetime_utc(end_utc)

        print(start_param, end_param)
        params = {
            "ActionDateStart": start_param,
            "ActionDateEnd": end_param,
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
                print(f"url: {url}")
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
            if response.status_code not in (200, 201):
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
        url=BASE_URL+self.username+"/Actions"
        logger.info(f"Retrieving action {action_id}")
        body={
            "ActionId":action_id,
            "Amount":amount,
            "Reason":reason

        }
        print(f"update action body: {action_id}, {body}")
        try:
            response = requests.put(
                url,
                auth = HTTPBasicAuth(self.username, self.password),
                headers = {"Accept": "application/json"},
                data = body
            )
            print(f"update code response {response}")
            if response.status_code not in (200, 201):
                logger.error(f"Error {response.status_code}: {response.text}")
                return None

            data = response.json()
            logger.info(f"Update response: {data}")

            return data

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
            if response.status_code not in (200, 201):
                logger.error(f"Error {response.status_code}: {response.text}")
                return None

            data = response.json()
            logger.info(f"Update response: {data}")

            return data

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