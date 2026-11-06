import csv
import json
from pathlib import Path
import requests

# Base directory: saves right in the folder where this script lives
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

API_URL = "https://mospi-apix-api.onrender.com/api/fares/raw"
JSON_PATH = DATA_DIR / "airfare_index.json"
CSV_PATH = DATA_DIR / "airfare_index.csv"


def fetch_api_data(hours_back=24):
    print(f"Fetching API data for the last {hours_back} hours...")
    try:
        response = requests.get(
            API_URL,
            params={"hours_back": hours_back},
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "ok":
            raise RuntimeError(f"API returned error: {payload}")

        records = payload.get("data", [])
        print(f"API returned {len(records):,} records")
        return records

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error while connecting to API: {e}")


def record_key(record):
    """Generates a unique tuple hash per flight observation to avoid duplicates."""
    return (
        str(record.get("timestamp", "")),
        str(record.get("airline", "")),
        str(record.get("flight_number", "")),
        str(record.get("route", "")),
        str(record.get("travel_date", "")),
        str(record.get("departure_time", "")),
        str(record.get("arrival_time", "")),
        str(record.get("advance_window_days", "")),
        str(record.get("base_fare", "")),
        str(record.get("taxes_fees", "")),
        str(record.get("total_fare", "")),
        str(record.get("ota_source", "")),
    )


def load_existing_records():
    if not JSON_PATH.exists():
        return []

    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)

        if isinstance(payload, dict):
            return payload.get("raw_fares", [])
        if isinstance(payload, list):
            return payload
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Could not read existing file ({e}). Starting fresh.")
        return []

    return []


def merge_records(existing, new_records):
    existing_keys = {record_key(row) for row in existing}
    added = 0

    for record in new_records:
        key = record_key(record)
        if key in existing_keys:
            continue

        existing.append(record)
        existing_keys.add(key)
        added += 1

    return existing, added


def save_data(records):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Save JSON atomically (without indent=2 to prevent rapid disk inflation)
    temp_json = JSON_PATH.with_suffix(".tmp")
    with open(temp_json, "w", encoding="utf-8") as f:
        json.dump({"raw_fares": records}, f, separators=(",", ":"))
    temp_json.replace(JSON_PATH)

    # 2. Save/Update CSV for viewing
    if records:
        temp_csv = CSV_PATH.with_suffix(".tmp")
        headers = list(records[0].keys())

        with open(temp_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(records)

        temp_csv.replace(CSV_PATH)


def main():
    new_records = fetch_api_data(hours_back=24)

    if not new_records:
        print("API returned zero records. Nothing to update.")
        return

    existing_records = load_existing_records()
    print(f"Existing stored records: {len(existing_records):,}")

    merged_records, added = merge_records(existing_records, new_records)

    save_data(merged_records)

    print(f"New unique records added: {added:,}")
    print(f"Total records in dataset: {len(merged_records):,}")
    print(f"Updated files:\n - {JSON_PATH}\n - {CSV_PATH}")


if __name__ == "__main__":
    main()