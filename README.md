🛂 Biometric Attendance Sync Tool (For ERPNext)
A Python-based utility to automatically pull attendance logs from your biometric device (ZKTeco/compatible) and sync them to your ERPNext instance via REST API — with resilience, smart fallbacks, and logging baked right in.

🚀 Features
🔁 Periodic Sync: Continuously polls your biometric device every POLL_INTERVAL seconds and pushes new logs to ERPNext.

🕵️ Reliable Resumption: Automatically resumes from the last synced timestamp using a sync file and log inspection.

🔐 ERPNext Token Auth: Uses API Key + Secret headers for secure and tokenized access.

🔄 Retry Mechanism: Built-in retry logic for network or API failures (3 tries per log + exponential backoff on device failures).

🧠 Watchdog Monitoring: Triggers an error if no successful sync occurs within 24 hours.

🧹 Optional Log Cleanup: Clears attendance logs from the device post-sync (toggle via config).

📄 Verbose Logging: Logs every step and error to a file for easy debugging.

🧬 Single Instance Protection: PID file ensures only one sync instance runs at a time.

⚙️ Prerequisites
Python 3.6+
Internet (for installing dependencies & syncing to ERPNext)
pip install -r requirements.txt

🔧 Setup
Generate API Key & Secret in ERPNext:
Go to My Settings > API Access
Use the generated token for the script

Configure biometric_sync.py:
Open the script and set the following variables-

DEVICE_IP = '192.168.1.201'
DEVICE_PORT = 4370
ERP_SITE = 'http://localhost:8000'
API_KEY = 'xxxxxx'
API_SECRET = 'xxxxxx'
DEVICE_ID = 'Device 1'
LAST_SYNC_FILE = 'last_sync_device1.json'
LOG_FILE = 'biometric_sync_device1.log'
PID_FILE = 'biometric_sync_device1.pid'
Optional config:

IMPORT_START_DATE: Start syncing logs from this date if no logs are found in sync/log files.

CLEAR_DEVICE_AFTER_SYNC: Set to True if you want to auto-clear logs from device after syncing.

SKIP_AUTO_ATTENDANCE: Set to 1 if you don't want ERPNext to trigger auto attendance for logs.

CHUNK_SIZE: Process logs in manageable batches (default: 100).

MAX_RETRIES: Retry connection attempts to the device before giving up.

Run the Script:
python3 biometric_sync.py

To stop it:
Use CTRL + C or
Kill the PID mentioned in biometric_sync_device1.pid

🧪 How It Works
Sync Resume: It looks at last_sync_device1.json. If missing/corrupted, it checks the latest timestamp from the log file.

Reachability Check: Pings the device before connecting (via TCP socket test).

Device Connection: Uses the zk library to connect and download logs.

Log Filtering: Compares log timestamps and processes only new ones.

ERPNext Push: Sends each log as a POST request to:
/api/method/hrms.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field
Error Handling: Catches network or API issues and retries intelligently.

🪵 Logs & Monitoring
Log File: All sync events (success, warnings, errors) are saved in biometric_sync_device1.log

Watchdog: If no logs are successfully synced in 24 hours, it raises an error for monitoring tools.

🛑 Known Limitations
Works only with ZKTeco-like fingerprint devices supported by the zk Python library.

No UI (yet) – this is purely CLI-based.

Ensure device time is in sync with ERP server time for accurate attendance.

🧼 Optional Cleanup (Post Sync)
Want to keep the device clean and light?
CLEAR_DEVICE_AFTER_SYNC = True
This will clear attendance logs after each successful sync.

🤝 Contributing
PRs are welcome! Whether you want to add support for more device brands, a UI layer, Dockerization, or systemd service files, feel free to pitch in.

📜 License
MIT – Go wild with it. Just don’t use it to time travel or manipulate space-time.