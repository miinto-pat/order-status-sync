import datetime
import json
import os


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
        formatted_dt = datetime.datetime.strftime(date_string, '%Y-%m-%dT%H:%M:%SZ')
        return formatted_dt