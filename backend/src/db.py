import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime

# PostgreSQL database configuration
DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "Roshan@1819",
    "host": "localhost",
    "port": "5432",
}


def get_connection():
    """Helper to establish a connection to PostgreSQL."""
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    """Initialize the PostgreSQL database table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS callers (
            user_id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255),
            language_preference VARCHAR(100),
            facts JSONB,
            last_interaction TIMESTAMP WITH TIME ZONE
        );
        """)

    conn.commit()
    cursor.close()
    conn.close()


def get_caller_record(user_id: str):
    """Retrieve caller record by user_id."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT
            user_id,
            name,
            language_preference,
            facts,
            last_interaction
        FROM callers
        WHERE user_id = %s;
        """,
        (user_id,),
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if row:
        if row.get("last_interaction"):
            row["last_interaction"] = row["last_interaction"].isoformat()

        return dict(row)

    return None


def save_caller_record(
    user_id: str,
    name: str,
    language_preference: str,
    facts: dict,
):
    """Save or update caller information using PostgreSQL UPSERT."""

    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()
    facts_json = json.dumps(facts)

    cursor.execute(
        """
        INSERT INTO callers (
            user_id,
            name,
            language_preference,
            facts,
            last_interaction
        )
        VALUES (%s, %s, %s, %s, %s)

        ON CONFLICT (user_id)
        DO UPDATE SET
            name = EXCLUDED.name,
            language_preference = EXCLUDED.language_preference,
            facts = EXCLUDED.facts,
            last_interaction = EXCLUDED.last_interaction;
        """,
        (
            user_id,
            name,
            language_preference,
            facts_json,
            now,
        ),
    )

    conn.commit()
    cursor.close()
    conn.close()
