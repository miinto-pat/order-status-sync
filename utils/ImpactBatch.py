import csv
import io
import os
import tempfile
import zipfile
from datetime import datetime, timezone


BATCH_HEADERS = ("ActionID", "Oid", "Amount", "Reason")


def create_batch_file_name(run_id, markets):
    market_part = "-".join(markets or ["all"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_run_id = str(run_id or "manual").replace(os.sep, "_")
    return f"impact_batch_{safe_run_id}_{market_part}_{timestamp}.csv"


def create_batch_file_path(run_id, markets):
    return os.path.join(tempfile.gettempdir(), create_batch_file_name(run_id, markets))


def create_market_batch_zip_file_name(run_id, markets):
    market_part = "-".join(markets or ["all"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_run_id = str(run_id or "manual").replace(os.sep, "_")
    return f"impact_batch_by_market_{safe_run_id}_{market_part}_{timestamp}.zip"


def create_market_batch_zip_file_path(run_id, markets):
    return os.path.join(tempfile.gettempdir(), create_market_batch_zip_file_name(run_id, markets))


def format_amount(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def write_batch_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=BATCH_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "ActionID": row.get("action_id") or row.get("ActionID") or row.get("ActionId") or "",
                    "Oid": row.get("order_id") or row.get("Oid") or row.get("orderId") or "",
                    "Amount": format_amount(row.get("amount")),
                    "Reason": row.get("reason") or row.get("Reason") or "",
                }
            )


def batch_csv_content(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=BATCH_HEADERS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "ActionID": row.get("action_id") or row.get("ActionID") or row.get("ActionId") or "",
                "Oid": row.get("order_id") or row.get("Oid") or row.get("orderId") or "",
                "Amount": format_amount(row.get("amount")),
                "Reason": row.get("reason") or row.get("Reason") or "",
            }
        )
    return output.getvalue()


def write_market_batch_zip(path, rows, run_id=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows_by_market = {}
    for row in rows:
        market = row.get("market") or "Unknown"
        rows_by_market.setdefault(market, []).append(row)

    file_names = {}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for market in sorted(rows_by_market):
            file_name = f"impact_batch_{run_id or 'manual'}_{market}.csv"
            zipf.writestr(file_name, batch_csv_content(rows_by_market[market]))
            file_names[market] = file_name
    return file_names


def batch_rows_from_actions_by_state(market, actions_by_state):
    rows = []
    for reason in ("OTHER", "ITEM_RETURNED", "ORDER_UPDATE"):
        for record in actions_by_state.get(reason, []):
            rows.append(
                {
                    "market": market,
                    "action_id": record.get("actionId") or record.get("action_id"),
                    "order_id": record.get("orderId"),
                    "amount": record.get("amount"),
                    "reason": reason,
                }
            )
    return rows
