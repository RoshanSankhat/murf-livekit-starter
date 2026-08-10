"""
Quick verification script for Day 5.
Run this from the same folder as db.py:

    python check_exercises.py

It just prints out what's in the exercises table.
"""

import db

conn = db.get_connection()
cursor = conn.cursor()

cursor.execute("SELECT subject, level, topic FROM exercises ORDER BY subject, level;")
rows = cursor.fetchall()

cursor.close()
conn.close()

if not rows:
    print("No rows found. The table may not have been seeded yet.")
    print("Make sure you've run agent.py at least once (it calls")
    print("db.init_exercises_db() and db.seed_exercises_if_empty() on launch).")
else:
    print(f"Found {len(rows)} exercises:\n")
    for subject, level, topic in rows:
        print(f"  {subject:<16} {level:<14} {topic}")