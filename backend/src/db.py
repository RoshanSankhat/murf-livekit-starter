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


# ------------------------------------------------------------------
# DAY 5: EXERCISE LOOKUP TOOL
# ------------------------------------------------------------------
# Local hand-built dataset of practice exercises, tagged by subject
# and level. This is NOT a live external API - it's a local dataset,
# as allowed by the Day 5 brief when no single public source covers
# a broad "all subjects" tutor. Documented as local data in the README.


def init_exercises_db():
    """Initialize the exercises table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id SERIAL PRIMARY KEY,
            subject VARCHAR(100) NOT NULL,
            level VARCHAR(50) NOT NULL,
            topic VARCHAR(150),
            question TEXT NOT NULL,
            answer TEXT NOT NULL
        );
        """)

    conn.commit()
    cursor.close()
    conn.close()


# Starter seed set. Modest on purpose - a handful per subject/level,
# meant to be expanded over time rather than being exhaustive.
SEED_EXERCISES = [
    # Mathematics
    ("Mathematics", "beginner", "addition", "What is 7 plus 5?", "12"),
    ("Mathematics", "beginner", "subtraction", "What is 15 minus 6?", "9"),
    ("Mathematics", "intermediate", "multiplication", "What is 8 times 7?", "56"),
    ("Mathematics", "intermediate", "fractions", "What is one half plus one quarter?", "three quarters"),
    ("Mathematics", "advanced", "algebra", "Solve for x: 2x plus 3 equals 11.", "x = 4"),

    # English
    ("English", "beginner", "vocabulary", "What is another word for happy?", "glad, joyful, or cheerful"),
    ("English", "beginner", "spelling", "How do you spell the word for a young dog?", "puppy"),
    ("English", "intermediate", "grammar", "Choose the correct word: She (go/goes) to school every day.", "goes"),
    ("English", "intermediate", "reading", "What is a synonym for 'quick'?", "fast, swift, or rapid"),
    ("English", "advanced", "writing", "Name one difference between a metaphor and a simile.", "a simile uses 'like' or 'as', a metaphor states something directly is something else"),

    # Science
    ("Science", "beginner", "biology", "What part of the plant makes food using sunlight?", "the leaves"),
    ("Science", "beginner", "physics", "What force pulls objects toward the ground?", "gravity"),
    ("Science", "intermediate", "chemistry", "What is water made of, chemically?", "two hydrogen atoms and one oxygen atom, H2O"),
    ("Science", "intermediate", "biology", "What organ pumps blood through the body?", "the heart"),
    ("Science", "advanced", "physics", "What is the formula for calculating speed?", "speed = distance divided by time"),

    # Social Studies
    ("Social Studies", "beginner", "geography", "What do we call the large landmasses on Earth?", "continents"),
    ("Social Studies", "beginner", "history", "Who is usually the head of a country's government called in a democracy?", "prime minister or president, depending on the country"),
    ("Social Studies", "intermediate", "geography", "What is the longest river in the world commonly considered to be?", "the Nile or the Amazon, depending on the measurement used"),
    ("Social Studies", "intermediate", "history", "What do we call a period of major industrial growth and machine-based production?", "the Industrial Revolution"),
    ("Social Studies", "advanced", "geography", "What is the term for lines on a map that connect points of equal elevation?", "contour lines"),
]


def seed_exercises_if_empty():
    """Populate the exercises table with starter data, only if empty."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM exercises;")
    count = cursor.fetchone()[0]

    if count == 0:
        cursor.executemany(
            """
            INSERT INTO exercises (subject, level, topic, question, answer)
            VALUES (%s, %s, %s, %s, %s);
            """,
            SEED_EXERCISES,
        )
        conn.commit()

    cursor.close()
    conn.close()


def get_exercise(subject: str, level: str):
    """
    Fetch one exercise matching subject and level (case-insensitive,
    partial match on subject). Falls back to matching subject only
    (ignoring level) if no exact level match is found, and returns
    None if the subject isn't covered at all.
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Try exact subject + level match first
    cursor.execute(
        """
        SELECT subject, level, topic, question, answer
        FROM exercises
        WHERE LOWER(subject) LIKE LOWER(%s)
          AND LOWER(level) = LOWER(%s)
        ORDER BY RANDOM()
        LIMIT 1;
        """,
        (f"%{subject}%", level),
    )
    row = cursor.fetchone()

    # Fall back to subject match only, any level
    if row is None:
        cursor.execute(
            """
            SELECT subject, level, topic, question, answer
            FROM exercises
            WHERE LOWER(subject) LIKE LOWER(%s)
            ORDER BY RANDOM()
            LIMIT 1;
            """,
            (f"%{subject}%",),
        )
        row = cursor.fetchone()

    cursor.close()
    conn.close()

    return dict(row) if row else None
# ------------------------------------------------------------------
# DAY 7: HUMAN-HELP ESCALATION
# ------------------------------------------------------------------
# Two reasons an escalation is created for the Learning & Literacy track:
#   - learner_distress : learner is upset, frustrated, or wants to stop
#   - needs_teacher     : grading, a curriculum decision, or the same
#                         concept explained 3+ times with no success
# Only ever inserted after the agent has verbally asked for permission.

import uuid


def init_escalations_db():
    """Initialize the escalations table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS escalations (
            reference_id VARCHAR(20) PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            reason_code VARCHAR(50) NOT NULL,
            what_happened TEXT NOT NULL,
            what_agent_checked TEXT NOT NULL,
            urgency VARCHAR(20) NOT NULL,
            language VARCHAR(100),
            follow_up_method VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'open',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE
        );
        """)

    conn.commit()
    cursor.close()
    conn.close()


def new_escalation_reference_id() -> str:
    return "ESC-" + uuid.uuid4().hex[:8].upper()


def find_open_escalation(user_id: str, reason_code: str):
    """Same learner + same reason, still open or in_progress -> existing ticket."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT * FROM escalations
        WHERE user_id = %s AND reason_code = %s
          AND status IN ('open', 'in_progress')
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        (user_id, reason_code),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(row) if row else None


def create_escalation_record(
    user_id: str,
    reason_code: str,
    what_happened: str,
    what_agent_checked: str,
    urgency: str,
    language: str,
    follow_up_method: str,
) -> dict:
    """Insert a new escalation and return the created row."""
    conn = get_connection()
    cursor = conn.cursor()

    reference_id = new_escalation_reference_id()
    now = datetime.now()

    cursor.execute(
        """
        INSERT INTO escalations (
            reference_id, user_id, reason_code, what_happened,
            what_agent_checked, urgency, language, follow_up_method,
            status, notes, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open', '', %s, %s);
        """,
        (
            reference_id, user_id, reason_code, what_happened,
            what_agent_checked, urgency, language, follow_up_method,
            now, now,
        ),
    )

    conn.commit()
    cursor.close()
    conn.close()

    return {
        "reference_id": reference_id,
        "user_id": user_id,
        "reason_code": reason_code,
        "what_happened": what_happened,
        "what_agent_checked": what_agent_checked,
        "urgency": urgency,
        "language": language,
        "follow_up_method": follow_up_method,
        "status": "open",
        "created_at": now.isoformat(),
    }


def append_escalation_note(reference_id: str, note: str):
    """Append a note to an existing escalation and bump updated_at."""
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()
    stamped_note = f"\n[{now.isoformat()}] {note}"

    cursor.execute(
        """
        UPDATE escalations
        SET notes = notes || %s, updated_at = %s
        WHERE reference_id = %s;
        """,
        (stamped_note, now, reference_id),
    )

    conn.commit()
    cursor.close()
    conn.close()


def set_escalation_status(reference_id: str, status: str):
    """status must be one of: open, in_progress, resolved"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE escalations
        SET status = %s, updated_at = %s
        WHERE reference_id = %s;
        """,
        (status, datetime.now(), reference_id),
    )

    conn.commit()
    cursor.close()
    conn.close()


def get_escalation(reference_id: str):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("SELECT * FROM escalations WHERE reference_id = %s;", (reference_id,))
    row = cursor.fetchone()

    cursor.close()
    conn.close()
    return dict(row) if row else None


def list_escalations(status: str = None):
    """Used by the dashboard. Pass status to filter, or None for all."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if status:
        cursor.execute(
            "SELECT * FROM escalations WHERE status = %s ORDER BY created_at DESC;",
            (status,),
        )
    else:
        cursor.execute("SELECT * FROM escalations ORDER BY created_at DESC;")

    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(r) for r in rows]
# ------------------------------------------------------------------
# DAY 8: CALL ANALYTICS
# ------------------------------------------------------------------
# Success definition (Learning & Literacy track):
#   A call is "successful" if the learner received a practice exercise
#   AND attempted/answered it before the call ended.
# Everything else is recorded as "failed", with a failure_reason.
# No transcript or PII is stored here - only outcome metadata.

def init_calls_db():
    """Initialize the calls table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            call_id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(255),
            channel VARCHAR(20) NOT NULL,
            outcome VARCHAR(20) NOT NULL DEFAULT 'failed',
            failure_reason VARCHAR(50),
            started_at TIMESTAMP WITH TIME ZONE NOT NULL,
            ended_at TIMESTAMP WITH TIME ZONE,
            duration_seconds INTEGER
        );
        """)

    conn.commit()
    cursor.close()
    conn.close()


def start_call_record(call_id: str, user_id: str, channel: str):
    """Insert a row the moment a call begins."""
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()
    cursor.execute(
        """
        INSERT INTO calls (call_id, user_id, channel, outcome, started_at)
        VALUES (%s, %s, %s, 'failed', %s)
        ON CONFLICT (call_id) DO NOTHING;
        """,
        (call_id, user_id, channel, now),
    )

    conn.commit()
    cursor.close()
    conn.close()


def end_call_record(call_id: str, outcome: str, failure_reason: str = None):
    """Close out a call row with its final outcome ('success' or 'failed')."""
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()
    cursor.execute(
        """
        UPDATE calls
        SET outcome = %s,
            failure_reason = %s,
            ended_at = %s,
            duration_seconds = EXTRACT(EPOCH FROM (%s - started_at))::INT
        WHERE call_id = %s;
        """,
        (outcome, failure_reason, now, now, call_id),
    )

    conn.commit()
    cursor.close()
    conn.close()


def get_call_stats():
    """Used by the dashboard for the three headline numbers."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE outcome = 'success') AS successful,
            COUNT(*) FILTER (WHERE outcome = 'failed') AS failed
        FROM calls;
        """)
    row = cursor.fetchone()

    cursor.close()
    conn.close()
    return dict(row)


def list_calls(limit: int = 25):
    """Recent calls for the dashboard's history table. No transcript/PII."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT call_id, channel, outcome, failure_reason,
               started_at, ended_at, duration_seconds
        FROM calls
        ORDER BY started_at DESC
        LIMIT %s;
        """,
        (limit,),
    )
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    for r in rows:
        if r.get("started_at"):
            r["started_at"] = r["started_at"].isoformat()
        if r.get("ended_at"):
            r["ended_at"] = r["ended_at"].isoformat()

    return [dict(r) for r in rows]