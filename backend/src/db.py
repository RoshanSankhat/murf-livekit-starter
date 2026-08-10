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