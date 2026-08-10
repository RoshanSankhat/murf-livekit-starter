"""
One-time cleanup for Day 5.
Run this once to fix any caller records where topics_covered got
saved as the raw instruction text (from before the summarizer fix).

    python fix_bad_topics.py
"""

import db

BAD_SIGNALS = [
    "topic phrase", "topic label", "5-8 words", "punctuation",
    "should not quote", "no punctuation", "we need to output",
    "instructions",
]

conn = db.get_connection()
cursor = conn.cursor()

cursor.execute("SELECT user_id, facts FROM callers;")
rows = cursor.fetchall()

fixed = 0

for user_id, facts in rows:
    if not isinstance(facts, dict):
        continue

    topic = str(facts.get("topics_covered", "")).lower()

    if any(signal in topic for signal in BAD_SIGNALS):
        facts["topics_covered"] = "a recent learning session"

        cursor.execute(
            "UPDATE callers SET facts = %s WHERE user_id = %s;",
            (db.json.dumps(facts), user_id),
        )
        fixed += 1
        print(f"Fixed corrupted topic for user_id: {user_id}")

conn.commit()
cursor.close()
conn.close()

print(f"\nDone. Fixed {fixed} record(s).")