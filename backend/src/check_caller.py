"""
Check what's currently saved for a specific caller.
Run from the same folder as db.py:

    python check_caller.py
"""

import db

record = db.get_caller_record("test_user_fixed")

if record is None:
    print("No record found for test_user_fixed.")
else:
    print("Record for test_user_fixed:")
    print(f"  name: {record.get('name')}")
    print(f"  language_preference: {record.get('language_preference')}")
    print(f"  facts: {record.get('facts')}")
    print(f"  last_interaction: {record.get('last_interaction')}")