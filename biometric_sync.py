import time
import json
import os
import logging
import requests
from datetime import datetime
from zk import ZK, const
from zk.exception import ZKNetworkError

# ==== CONFIGURATION ====
DEVICE_IP = ''  #'122.1**.1**.4'
DEVICE_PORT = 4370
ERP_SITE = ''  #'http://localhost:8000'
API_KEY = ''    #'5554******01632'
API_SECRET = ''   #'0311******3cbe0'
DEVICE_ID = ''  # Device 1 (Optional but helpful for ERPNext)
LAST_SYNC_FILE = "last_sync.json"
LOG_FILE = "biometric_sync.log"

MAX_RETRIES = 3
CHUNK_SIZE = 100
SKIP_AUTO_ATTENDANCE = 0
CLEAR_DEVICE_AFTER_SYNC = False
IMPORT_START_DATE = datetime.strptime("2025-06-25 00:00:00", "%Y-%m-%d %H:%M:%S")

# === SETUP LOGGING ===
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_last_successful_sync_from_log():
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            for line in reversed(lines):
                if "Synced check-in for user" in line:
                    parts = line.split(" at ")
                    if len(parts) == 2:
                        timestamp_str = parts[1].strip()
                        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
    except Exception as e:
        logging.warning(f"Could not read last sync time from log: {e}")
    return None


def load_last_sync_time():
    last_sync_file_time = None
    last_log_time = get_last_successful_sync_from_log()

    # From JSON file
    try:
        with open(LAST_SYNC_FILE, "r") as f:
            data = json.load(f)
            last_sync_file_time = datetime.fromisoformat(data["last_sync"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # Find the latest among all
    timestamps = [ts for ts in [IMPORT_START_DATE, last_log_time, last_sync_file_time] if ts]
    return max(timestamps) if timestamps else datetime.min


def save_last_sync_time(new_time):
    with open(LAST_SYNC_FILE, "w") as f:
        json.dump({"last_sync": new_time.isoformat()}, f)


def push_log_to_erpnext(record):
    timestamp = record.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')
    log_type = 'IN' if record.punch == 1 else 'OUT'
    data = {
        "employee_field_value": str(record.user_id),
        "timestamp": timestamp,
        "device_id": DEVICE_ID,
        "log_type": log_type,
        "skip_auto_attendance": SKIP_AUTO_ATTENDANCE,
    }
    headers = {
        "Authorization": f"token {API_KEY}:{API_SECRET}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        f"{ERP_SITE}/api/method/hrms.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field",
        json=data,
        headers=headers
    )

    if response.status_code == 200:
        logging.info(f"Synced check-in for user {record.user_id} at {timestamp}")
        return True
    else:
        logging.error(f"Failed to sync log for user {record.user_id} at {timestamp}. Error: {response.text}")
        return False


def sync_logs(current_last_sync):
    attempt = 0
    latest_synced_time = None

    while attempt < MAX_RETRIES:
        try:
            zk = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=30, force_udp=True)
            conn = zk.connect()
            conn.disable_device()

            logs = conn.get_attendance()
            logging.info(f"{len(logs)} logs pulled from device")

            new_logs = [log for log in logs if log.timestamp > current_last_sync]
            new_logs.sort(key=lambda log: log.timestamp)
            logging.info(f"{len(new_logs)} new logs found since {current_last_sync}")

            for i in range(0, len(new_logs), CHUNK_SIZE):
                chunk = new_logs[i:i + CHUNK_SIZE]
                for log in chunk:
                    success = push_log_to_erpnext(log)
                    if success:
                        latest_synced_time = log.timestamp
                    else:
                        logging.warning(f"Skipped log: {log}")
                    time.sleep(0.2)
                logging.info(f"Synced chunk {i // CHUNK_SIZE + 1}")

            if latest_synced_time:
                save_last_sync_time(latest_synced_time)

            if CLEAR_DEVICE_AFTER_SYNC:
                conn.clear_attendance()
                logging.info("Cleared attendance logs from device after sync")

            conn.enable_device()
            conn.disconnect()
            break

        except ZKNetworkError as e:
            attempt += 1
            logging.warning(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}. Retrying in 10s...")
            time.sleep(10)

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            break

    return latest_synced_time


# ==== SCHEDULER LOOP ====
if __name__ == "__main__":
    POLL_INTERVAL = 60  # seconds
    logging.info("Starting continuous biometric sync every %s seconds", POLL_INTERVAL)

    try:
        current_last_sync = load_last_sync_time()
        while True:
            new_sync_time = sync_logs(current_last_sync)
            if new_sync_time:
                current_last_sync = new_sync_time
            logging.info("Sleeping for %s seconds...", POLL_INTERVAL)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logging.info("Sync stopped by user.")