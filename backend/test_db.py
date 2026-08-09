import db

try:
    print("Connecting to PostgreSQL and initializing table...")
    db.init_db()
    print("Table created/verified successfully!")

    print("Testing insert...")
    db.save_caller_record(
        user_id="user_123",
        name="Roshan",
        language_preference="English",
        facts={
            "current_level": "Intermediate",
            "topics_covered": "Verbs, Tenses",
            "struggles_or_mistakes": "Past continuous tense"
        }
    )
    print("Insert successful!")

    print("Testing retrieval...")
    record = db.get_caller_record("user_123")
    print("Retrieved Record:", record)

except Exception as e:
    print("Error connecting or writing to database:", e)