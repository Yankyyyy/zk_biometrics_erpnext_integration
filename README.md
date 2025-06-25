# Biometric Attendance Sync Tool (For ERPNext)

Python Scripts to poll your biometric attendance system (BAS) for logs and sync with your ERPNext instance.

Prerequisites:
Python 3.6+
Internet connection for requirements setup

Setup:
API Secret*
API Key*
*Note: Both generated in your ERPNext instance. Check ERPNext docs for reference.

Configuring ERPNext Biometric Sync Tool:
CLI : The biometric_sync.py file is the "backbone" of this project. The steps are -
1. Setup Specifications by editing the biometric_sync.py file similar to the examples given besides the values which needs to be configured.
2. Setup dependencies
3. Run the script using python3 biometric_sync.py