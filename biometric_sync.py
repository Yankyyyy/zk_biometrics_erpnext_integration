import time
import json
import os
import logging
import requests
import socket
from datetime import datetime
from zk import ZK, const
from zk.exception import ZKNetworkError

# ==== CONFIGURATION ====
DEVICE_IP = ''  #eg '122.1**.1**.4'
DEVICE_PORT = 4370
ERP_SITE = ''  #eg 'http://localhost:8000'
API_KEY = ''    #eg '5554******01632'
API_SECRET = ''   #eg '0311******3cbe0'
DEVICE_ID = ''  #eg 'Device 1' (Optional but helpful for ERPNext)
LAST_SYNC_FILE = ''   #eg "last_sync_device1.json"
LOG_FILE = ''   #eg "biometric_sync_device1.log"
PID_FILE = ''   #eg "biometric_sync_device1.pid"

MAX_RETRIES = 100
CHUNK_SIZE = 100
SKIP_AUTO_ATTENDANCE = 0
CLEAR_DEVICE_AFTER_SYNC = False
IMPORT_START_DATE = datetime.strptime("2025-06-25 09:30:00", "%Y-%m-%d %H:%M:%S")

POLL_INTERVAL = 60  # seconds
MAX_FAILURE_DELAY = 300  # 5 minutes maximum delay on failures

# === SETUP LOGGING ===
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='a'
)
logger = logging.getLogger()

def create_pid_file():
    """Create PID file to prevent multiple instances"""
    if os.path.exists(PID_FILE):
        with open(PID_FILE, 'r') as f:
            pid = f.read().strip()
            logger.error(f"Another instance is already running (PID: {pid}). Exiting.")
            raise SystemExit(1)
    
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

def remove_pid_file():
    """Remove PID file on exit"""
    try:
        os.remove(PID_FILE)
    except OSError:
        pass

def is_device_reachable(ip, port, timeout=5):
    """Check if device is reachable"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((ip, port)) == 0
    except Exception as e:
        logger.warning(f"Device reachability check failed: {e}")
        return False

def get_last_successful_sync_from_log():
    """Extract last sync time from log file"""
    try:
        with open(LOG_FILE, "r") as f:
            for line in reversed(f.readlines()):
                if "Synced check-in for user" in line:
                    parts = line.split(" at ")
                    if len(parts) == 2:
                        timestamp_str = parts[1].strip()
                        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
    except Exception as e:
        logger.warning(f"Could not read last sync time from log: {e}")
    return None

def load_last_sync_time():
    """Load last sync time with multiple fallbacks"""
    try:
        # Try to load from sync file first
        with open(LAST_SYNC_FILE, "r") as f:
            data = json.load(f)
            file_time = datetime.fromisoformat(data["last_sync"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Could not load last sync time from file: {e}")
        file_time = None
    
    log_time = get_last_successful_sync_from_log()
    
    # Choose the most recent valid timestamp
    valid_times = [t for t in [IMPORT_START_DATE, log_time, file_time] if t is not None]
    return max(valid_times) if valid_times else IMPORT_START_DATE

def save_last_sync_time(new_time):
    """Atomically save last sync time"""
    temp_file = LAST_SYNC_FILE + ".tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump({"last_sync": new_time.isoformat()}, f)
        os.replace(temp_file, LAST_SYNC_FILE)
    except Exception as e:
        logger.error(f"Failed to save sync time: {e}")

def push_log_to_erpnext(record):
    """Push single log record to ERPNext with retry logic"""
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
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    for attempt in range(3):  # 3 retry attempts
        try:
            response = requests.post(
                f"{ERP_SITE}/api/method/hrms.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field",
                json=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Synced check-in for user {record.user_id} at {timestamp}")
                return True
            else:
                logger.warning(f"Attempt {attempt + 1}: Failed to sync log for user {record.user_id}. Status: {response.status_code}")
                if attempt < 2:
                    time.sleep(5)  # Wait before retry
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1}: Network error while syncing log: {e}")
            if attempt < 2:
                time.sleep(10)
    
    logger.error(f"Failed to sync log for user {record.user_id} after 3 attempts")
    return False

def sync_logs(current_last_sync):
    """Main sync logic with improved connection handling"""
    attempt = 0
    latest_synced_time = None
    conn = None
    
    while attempt < MAX_RETRIES:
        try:
            # Check device reachability first
            if not is_device_reachable(DEVICE_IP, DEVICE_PORT):
                raise ZKNetworkError(f"Device at {DEVICE_IP}:{DEVICE_PORT} is unreachable")
            
            # Connect to device
            zk = ZK(
                DEVICE_IP,
                port=DEVICE_PORT,
                timeout=30,
                force_udp=True,
                ommit_ping=False
            )
            conn = zk.connect()
            conn.disable_device()
            
            # Get and process logs
            logs = conn.get_attendance()
            logger.info(f"Retrieved {len(logs)} logs from device")
            
            new_logs = [log for log in logs if log.timestamp > current_last_sync]
            new_logs.sort(key=lambda log: log.timestamp)
            logger.info(f"Found {len(new_logs)} new logs since {current_last_sync}")
            
            if not new_logs:
                logger.info("No new logs to sync")
                return None
            
            # Process logs in chunks
            for i in range(0, len(new_logs), CHUNK_SIZE):
                chunk = new_logs[i:i + CHUNK_SIZE]
                for log in chunk:
                    if push_log_to_erpnext(log):
                        latest_synced_time = log.timestamp
                    time.sleep(0.1)  # Small delay between requests
                
                logger.info(f"Processed chunk {i//CHUNK_SIZE + 1}/{(len(new_logs)-1)//CHUNK_SIZE + 1}")
            
            # Update sync time if we processed any logs
            if latest_synced_time:
                save_last_sync_time(latest_synced_time)
            
            # Clear device if configured
            if CLEAR_DEVICE_AFTER_SYNC:
                conn.clear_attendance()
                logger.info("Cleared attendance logs from device")
            
            return latest_synced_time
            
        except ZKNetworkError as e:
            attempt += 1
            logger.warning(f"Network error (attempt {attempt}/{MAX_RETRIES}): {e}")
            time.sleep(min(10 * attempt, 60))  # Progressive backoff
            
        except Exception as e:
            attempt += 1
            logger.error(f"Unexpected error (attempt {attempt}/{MAX_RETRIES}): {e}", exc_info=True)
            time.sleep(min(10 * attempt, 60))
            
        finally:
            # Ensure device is re-enabled and disconnected
            if conn:
                try:
                    conn.enable_device()
                    conn.disconnect()
                except Exception as e:
                    logger.warning(f"Error while cleaning up connection: {e}")
    
    logger.error(f"Failed to sync after {MAX_RETRIES} attempts")
    return None

def main():
    """Main execution loop with watchdog"""
    logger.info("Starting biometric sync service")
    create_pid_file()
    
    try:
        failure_count = 0
        last_success = datetime.now()
        
        while True:
            try:
                current_sync = load_last_sync_time()
                logger.info(f"Starting sync from {current_sync}")
                
                new_sync = sync_logs(current_sync)
                
                if new_sync:
                    logger.info(f"Sync completed successfully up to {new_sync}")
                    failure_count = 0
                    last_success = datetime.now()
                else:
                    logger.info("Sync completed with no new records")
                
                # Check for watchdog condition (no success for 24h)
                if (datetime.now() - last_success).total_seconds() > 86400:
                    logger.error("Watchdog triggered - no successful sync in 24 hours")
                    raise RuntimeError("Watchdog timeout")
                
                # Normal sleep
                time.sleep(POLL_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Shutdown requested by user")
                break
                
            except Exception as e:
                failure_count += 1
                logger.error(f"Main loop error #{failure_count}: {e}", exc_info=True)
                
                # Progressive backoff on repeated failures
                delay = min(MAX_FAILURE_DELAY, POLL_INTERVAL * (2 ** min(failure_count, 5)))
                logger.info(f"Waiting {delay} seconds before retry...")
                time.sleep(delay)
                
    finally:
        remove_pid_file()
        logger.info("Service stopped")

if __name__ == "__main__":
    main()