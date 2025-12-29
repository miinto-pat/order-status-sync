import csv
import datetime
import io
import json
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Any

from google.cloud import storage, secretmanager

from constants.Constants import VAT
from helpers import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # parent of utils/

CONFIG_PATH = PROJECT_ROOT / "config.json"
class common_utils:
    @staticmethod
    def read_json(filepath):
        """Reads the contents of a JSON file."""
        try:
            if not os.path.exists(filepath):  # Check if the file exists
                print(f"Error: File not found at {filepath}")
                return None

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)  # Load JSON data into a Python dictionary or list
                return data
        except FileNotFoundError:
            print(f"Error: File not found at {filepath}")
            return None
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON format in {filepath}")
            return None
        except Exception as e:
            print(f"Unexpected error reading {filepath}: {e}")
            return None

    @staticmethod
    def format_date(date_string):
        dt = datetime.datetime.strptime(date_string, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


    @staticmethod
    def load_config(filename: str = "config.json", fallback_to_env: bool = True) -> Dict[str, Any]:
        """
        Load configuration dict from a JSON file (searched in several sensible locations)
        or, if not found, from the environment variable `impact_secret_json` / `IMPACT_SECRET_JSON`.

        Search order (file):
          1. CWD/config.json
          2. project root (parent of this utils folder)/config.json
          3. utils/config.json (rare but possible)

        If no file found and fallback_to_env is True, tries environment variable.
        Raises FileNotFoundError if neither present, or ValueError on invalid JSON.
        """
        here = Path(__file__).resolve().parent  # utils/...
        candidates = [
            Path.cwd() / filename,  # when running tests or docker with WORKDIR
            here.parent / filename,  # project root /config.json
            here / filename  # utils/config.json
        ]

        for p in candidates:
            try:
                p = p.resolve()
            except Exception:
                # ignore resolution problems, continue
                pass
            if p.exists() and p.is_file():
                try:
                    with p.open("r", encoding="utf-8") as fh:
                        return json.load(fh)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in config file {p}: {e}") from e

        # Fall back to environment variable (JSON content)
        if fallback_to_env:
            env_json = os.getenv("impact_secret_json") or os.getenv("IMPACT_SECRET_JSON")
            if env_json:
                try:
                    return json.loads(env_json)
                except json.JSONDecodeError as e:
                    raise ValueError("Invalid JSON in environment variable impact_secret_json") from e

        raise FileNotFoundError(
            f"No {filename} found in {', '.join(str(x) for x in candidates)} and "
            "impact_secret_json / IMPACT_SECRET_JSON env var is not set."
        )

    @staticmethod
    def exclude_VAT(cost, market):
        vat_rate = VAT.get(market)
        if cost is None:
            print(f"⚠️ exclude_VAT: cost is None for market {market}, returning 0")
        print(f"VAT rate for market: {market} is {vat_rate}")
        if vat_rate is None:
            raise ValueError(f"No VAT rate found for market '{market}'")
        # return cost / (1 + vat_rate / 100)

        net_cost = Decimal(str(cost)) / (Decimal("1") + Decimal(str(vat_rate)) / Decimal("100"))
        return float(net_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @staticmethod
    def create_market_csv(market, actions_by_state,allowed_states,target_state):
        rows = []

        for state, items in actions_by_state.items():
            if not items or state not in allowed_states:
                continue
            for entry in items:
                if target_state == "processed":
                    rows.append([
                        entry.get("orderId"),
                        entry.get("amount"),
                        state
                    ])
                else:
                    rows.append([
                        state,
                        entry.get("orderId"),
                    ])

        # If no rows, do not create a file
        if not rows:
            print("No items to write. CSV file not created.")
            return None

        # Prepare header
        if target_state == "processed":
            header = [ "orderId",  "amount","state"]
        else:
            header = ["state", "orderId"]

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerows(rows)

        filename = f"{market}_{target_state}_results.csv"
        tmp_dir = "/tmp"
        file_path = os.path.join(tmp_dir, filename)
        # output_dir = os.path.join(os.getcwd(), "output")
        # os.makedirs(output_dir, exist_ok=True)
        # file_path = os.path.join(output_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(output.getvalue())

        print(f"Created CSV: {file_path}")

        return file_path


    # Upload ZIP to GCS
    @staticmethod
    def upload_zip_to_gcs(local_zip_path, bucket_name="impact-bot-temp-files"):
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob_name = os.path.basename(local_zip_path)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_zip_path)
        return blob_name


