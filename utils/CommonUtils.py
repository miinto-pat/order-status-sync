import datetime
import json
import os
from pathlib import Path
from typing import Dict, Any


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
