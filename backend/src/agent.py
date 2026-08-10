import asyncio
import logging
import os

from dotenv import load_dotenv
from livekit import rtc

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    room_io,
    function_tool,
)

from livekit.agents.llm import StopResponse

from livekit.plugins import (
    murf,
    silero,
    deepgram,
    noise_cancellation,
    openai,
)

# Cohere is accessed through its OpenAI-compatible Compatibility API.
from openai import AsyncOpenAI

# Import DB helper module
import db


# ------------------------------------------------------------------
# DATABASE INITIALIZATION
# ------------------------------------------------------------------

db.init_db()

# Day 5: initialize and seed the exercises lookup table
db.init_exercises_db()
db.seed_exercises_if_empty()

logger = logging.getLogger("agent")

load_dotenv(".env.local")
load_dotenv(".env")


# ------------------------------------------------------------------
# COHERE CONFIGURATION
# ------------------------------------------------------------------

COHERE_BASE_URL = "https://api.cohere.ai/compatibility/v1"
COHERE_MODEL = "command-a-plus-05-2026"


# ------------------------------------------------------------------
# SYSTEM PROMPT
# ------------------------------------------------------------------

SYSTEM_PROMPT = """
IDENTITY:
You are Alexa, a friendly and encouraging Learning and Literacy Coach
at "R's World". You help students and young learners learn,
understand, practice, and revise educational topics.

CORE PURPOSE:
You support a broad range of school-level Learning and Literacy topics.

SUPPORTED TOPICS INCLUDE:

- English language
- Reading
- Writing
- Vocabulary
- Pronunciation
- Grammar
- Spelling
- Mathematics
- Basic arithmetic
- Algebra
- Geometry
- Science
- General science concepts
- Physics at school level
- Chemistry at school level
- Biology at school level
- Social studies
- History
- Geography
- General knowledge related to education
- Basic computer and technology concepts
- Study skills
- Basic problem solving
- Other normal primary and secondary school learning topics

OBJECTIVES:

1. Help learners understand educational concepts clearly.
2. Explain difficult concepts using simple language.
3. Give examples and practice questions when useful.
4. Encourage learners when they make mistakes.
5. Help learners improve reading, writing, vocabulary,
   pronunciation, and comprehension.
6. Help learners practice mathematics and other school subjects.
7. Ask follow-up questions when needed to understand
   what the learner wants to learn.
8. Check periodically if the learner wants to continue,
   practice more, or try another educational topic.
9. Remember relevant information from previous conversations
   when it is available.
10. When it feels useful, ASK the learner if they'd like to try a
    practice question. Only call fetch_next_exercise if they say yes,
    or if they directly asked for practice/a question themselves.
    Speak the question naturally, not as a data dump.

11. SOURCE HONESTY FOR PRACTICE QUESTIONS:
    Practice questions come from the local hand-built practice dataset.
    The dataset was prepared on August 10, 2026.
    When giving a practice question, make it clear that the question
    comes from the local practice set and mention the preparation date
    when appropriate.

12. DATABASE GROUNDING:
    When a practice question is supplied by the Day 5 lookup hook,
    use the exact question provided by the lookup.
    NEVER invent, replace, rewrite, or substitute the question.
    NEVER claim a question came from the practice bank unless it was
    actually retrieved from the practice database.

KNOWLEDGE:

- You can help with normal primary and secondary school
  educational subjects.
- You can explain concepts step by step.
- You can solve educational problems and explain the reasoning.
- You can provide examples and practice exercises.
- You should not pretend to know information you are unsure about.
- You do NOT need to restrict learning to English, reading,
  or vocabulary.
- Advanced college-level subjects may be outside your scope.

LANGUAGE & PRONUNCIATION (CRITICAL):

- DEFAULT LANGUAGE IS ENGLISH:
  Always begin, greet, and default to clear standard English.

- LANGUAGE MIRRORING:
  Respond in English when the user speaks English.
  ONLY switch to Hindi or Hinglish when the user speaks Hindi,
  Hinglish, or explicitly requests Hindi.

- DEVANAGARI RULE:
  When speaking Hindi words, write them using Devanagari
  script so the TTS engine pronounces them naturally.

LEARNING STYLE:

- Explain concepts according to the learner's level.
- Use simple examples before difficult examples.
- For mathematics, show the steps clearly.
- For science, explain concepts using simple real-world examples.
- For English, help with vocabulary, grammar, reading,
  pronunciation, spelling, and writing.
- For history and geography, explain facts clearly and
  provide useful context.
- If the learner says they do not understand,
  explain the same concept in a simpler way.
- Never make the learner feel embarrassed for asking questions.

MEMORY & CONSENT (CRITICAL):

- Before calling save_caller_info, you MUST ask the learner
  out loud for permission, e.g.:
  "Can I remember this for next time we talk?"
- If the learner says no, do NOT call save_caller_info.
  Continue the conversation normally without saving anything.
- If the learner says yes, call save_caller_info with what
  you learned about them.
- Never claim you have saved something unless the tool call
  actually succeeded.

GUARDRAILS & REFUSALS:

- Educational questions should be answered whenever possible.
- Do NOT refuse a question merely because it is mathematics,
  science, history, geography, or another school subject.
- If a question is outside the educational purpose of the agent,
  politely redirect the learner toward learning.

Refusal:
"I can help with learning and educational topics.
Let us choose something you would like to learn."

- Never Shame:
  NEVER use words like "bad", "wrong", "dumb", or "incorrect".
  Frame mistakes as positive learning opportunities.

- Never Diagnose:
  NEVER suggest or mention learning disabilities.

- Escalation:
  If the learner is frustrated or asks for human support,
  run the escalation script.

ESCALATION SCRIPT:

"If you are finding this topic difficult, I can connect you
with our senior teacher. Would you like me to forward your request?"

STYLE (OPTIMIZED FOR SPEECH):

- Keep sentences short and easy to understand.
- Use natural conversational English.
- Avoid unnecessary technical language.
- NEVER use markdown formatting, bullet points, brackets,
  special symbols, or emojis in spoken responses.
"""


# ------------------------------------------------------------------
# FIRST-TIME GREETING
# ------------------------------------------------------------------

FIRST_TIME_GREETING = (
    "Hello! I am Alexa, your learning coach from R's World. "
    "What would you like to learn today?"
)


# ------------------------------------------------------------------
# CALLER IDENTITY
# ------------------------------------------------------------------

def resolve_user_id(ctx: JobContext) -> str:
    """Derive a stable per-caller user_id."""

    for participant in ctx.room.remote_participants.values():
        if participant.identity:
            return participant.identity

    return "guest"


async def resolve_user_id_async(
    ctx: JobContext,
    timeout: float = 3.0,
    poll_interval: float = 0.1,
) -> str:
    """Same as resolve_user_id, but waits briefly for participant identity."""

    elapsed = 0.0

    while elapsed < timeout:
        user_id = resolve_user_id(ctx)

        if user_id != "guest":
            return user_id

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    logger.warning(
        "No named participant identity appeared - falling back to 'guest'."
    )

    return "guest"


# ------------------------------------------------------------------
# DATABASE HELPERS
# ------------------------------------------------------------------

async def get_latest_record(user_id: str):
    """Retrieve the saved caller record for this specific user_id."""

    return await asyncio.to_thread(
        db.get_caller_record,
        user_id,
    )


async def persist_caller_record(
    user_id: str,
    name: str,
    language: str,
    facts: dict,
):
    """Save/update a single caller record for this specific user_id."""

    await asyncio.to_thread(
        db.save_caller_record,
        user_id,
        name,
        language,
        facts,
    )


async def fetch_exercise(
    subject: str,
    level: str,
):
    """Run the sync exercise lookup off the event loop."""

    return await asyncio.to_thread(
        db.get_exercise,
        subject,
        level,
    )


# ------------------------------------------------------------------
# KEYWORD-BASED TOPIC FALLBACK
# ------------------------------------------------------------------

_TOPIC_KEYWORDS = {
    "fractions": "fractions",
    "algebra": "algebra",
    "geometry": "geometry",
    "multiplication": "multiplication",
    "addition": "addition and subtraction",
    "subtraction": "addition and subtraction",
    "vocabulary": "vocabulary",
    "spelling": "spelling",
    "grammar": "grammar",
    "reading": "reading",
    "writing": "writing",
    "biology": "biology",
    "physics": "physics",
    "chemistry": "chemistry",
    "geography": "geography",
    "history": "history",
    "mathematics": "mathematics",
    "math": "mathematics",
    "english": "English",
    "science": "science",
    "social studies": "social studies",
}


def guess_topic_from_text(
    user_texts: list[str],
):
    combined = " ".join(user_texts).lower()

    for keyword, label in _TOPIC_KEYWORDS.items():
        if keyword in combined:
            return label

    return None


# ------------------------------------------------------------------
# DAY 5 - PRACTICE REQUEST DETECTION
# ------------------------------------------------------------------

_PRACTICE_KEYWORDS = (
    "practice",
    "practice question",
    "practice questions",
    "exercise",
    "exercises",
    "quiz me",
    "test me",
    "give me a question",
    "give me question",
    "ask me a question",
    "ask me question",
    "question to solve",
    "question for me",
)


_SUBJECT_KEYWORDS = {
    "social studies": "Social Studies",
    "mathematics": "Mathematics",
    "maths": "Mathematics",
    "math": "Mathematics",
    "english": "English",
    "reading": "English",
    "writing": "English",
    "vocabulary": "English",
    "spelling": "English",
    "grammar": "English",
    "science": "Science",
    "biology": "Science",
    "physics": "Science",
    "chemistry": "Science",
    "history": "Social Studies",
    "geography": "Social Studies",
}


_LEVEL_KEYWORDS = {
    "beginner": "beginner",
    "basic": "beginner",
    "easy": "beginner",
    "intermediate": "intermediate",
    "medium": "intermediate",
    "advanced": "advanced",
    "hard": "advanced",
}


def is_practice_request(text: str) -> bool:
    """
    Detect an explicit request for a practice question.

    This prevents the database lookup from firing for normal
    educational conversation.
    """

    normalized = text.lower().strip()

    return any(
        keyword in normalized
        for keyword in _PRACTICE_KEYWORDS
    )


def detect_subject(text: str):
    """
    Map the learner's words to one supported database subject.
    """

    normalized = text.lower()

    # Longer phrases are checked first.
    for keyword in sorted(
        _SUBJECT_KEYWORDS,
        key=len,
        reverse=True,
    ):
        if keyword in normalized:
            return _SUBJECT_KEYWORDS[keyword]

    return None


def detect_level(text: str) -> str:
    """
    Map common difficulty words to database levels.
    """

    normalized = text.lower()

    for keyword, level in _LEVEL_KEYWORDS.items():
        if keyword in normalized:
            return level

    return "beginner"


# ------------------------------------------------------------------
# TOPIC SUMMARY - COHERE
# ------------------------------------------------------------------

_summary_client = AsyncOpenAI(
    base_url=COHERE_BASE_URL,
    api_key=os.getenv(
        "COHERE_API_KEY",
        "",
    ).strip(),
)


async def summarize_session_topic(
    user_texts: list[str],
    fallback: str,
) -> str:
    """Summarize the caller's messages into a short topic phrase using Cohere."""

    conversation_snippet = " | ".join(
        t
        for t in user_texts[-8:]
        if t.strip()
    )

    if len(conversation_snippet) < 15:
        return (
            guess_topic_from_text(user_texts)
            or fallback
        )

    try:
        response = await asyncio.wait_for(
            _summary_client.chat.completions.create(
                model=COHERE_MODEL,
                max_tokens=20,
                temperature=0.3,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You summarize a short piece of tutoring "
                            "conversation into a topic label. Reply with "
                            "ONLY the topic label itself - nothing else, "
                            "no explanation, no restating these instructions."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Conversation: 'can you help me with 7 times 8' "
                            "| 'what about 9 times 6'\n"
                            "Topic label:"
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": "multiplication tables",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Conversation: {conversation_snippet}\n"
                            "Topic label:"
                        ),
                    },
                ],
            ),
            timeout=5.0,
        )

        raw_content = response.choices[0].message.content

        summary = (
            (raw_content or "")
            .strip()
            .strip('"')
            .strip("'")
        )

        if not summary:
            return (
                guess_topic_from_text(user_texts)
                or fallback
            )

        bad_signals = [
            "topic phrase",
            "topic label",
            "5-8 words",
            "punctuation",
            "should not quote",
            "no punctuation",
            "we need to output",
            "instructions",
        ]

        looks_like_echo = any(
            signal in summary.lower()
            for signal in bad_signals
        )

        if looks_like_echo:
            return (
                guess_topic_from_text(user_texts)
                or fallback
            )

        if len(summary) <= 100:
            return summary

    except asyncio.TimeoutError:
        logger.warning(
            "Cohere topic summary generation timed out."
        )

    except Exception as e:
        logger.error(
            f"Cohere topic summary generation failed: {e}"
        )

    return (
        guess_topic_from_text(user_texts)
        or fallback
    )


# ------------------------------------------------------------------
# ASSISTANT
# ------------------------------------------------------------------

class Assistant(Agent):

    def __init__(
        self,
        user_id: str,
    ) -> None:

        super().__init__(
            instructions=SYSTEM_PROMPT
        )

        self.user_id = user_id

    # --------------------------------------------------------------
    # DAY 5 - DETERMINISTIC LOOKUP HOOK
    # --------------------------------------------------------------

    async def on_user_turn_completed(
        self,
        turn_ctx,
        new_message,
    ) -> None:
        """
        Day 5 deterministic practice lookup.

        This runs after the user's turn and before the normal
        LLM response.

        When the learner explicitly asks for a practice question,
        the question is fetched directly from PostgreSQL.
        """

        user_text = (
            new_message.text_content or ""
        ).strip()

        if not user_text:
            return

        logger.info(
            f"DAY 5 HOOK: learner said: {user_text}"
        )

        # Do not trigger the database lookup for ordinary conversation.
        if not is_practice_request(user_text):
            return

        subject = detect_subject(user_text)
        level = detect_level(user_text)

        logger.info(
            f"DAY 5 HOOK: practice request detected. "
            f"subject={subject}, level={level}"
        )

        # ----------------------------------------------------------
        # SUBJECT NOT SPECIFIED
        # ----------------------------------------------------------

        if subject is None:

            await self.session.say(
                "Sure. Which subject would you like to practice?",
                allow_interruptions=True,
            )

            raise StopResponse()

        # ----------------------------------------------------------
        # REAL POSTGRESQL LOOKUP
        # ----------------------------------------------------------

        try:

            exercise = await fetch_exercise(
                subject,
                level,
            )

        except Exception as e:

            logger.error(
                f"DAY 5 HOOK: exercise database lookup failed: {e}"
            )

            await self.session.say(
                "I cannot reach my practice question bank right now. "
                "I can still explain the topic directly if you would like.",
                allow_interruptions=True,
            )

            raise StopResponse()

        # ----------------------------------------------------------
        # NO DATA
        # ----------------------------------------------------------

        if exercise is None:

            logger.info(
                f"DAY 5 HOOK: no exercise found for "
                f"subject={subject}, level={level}"
            )

            await self.session.say(
                f"I do not have a practice question for "
                f"{subject} at that level yet. "
                f"I can explain the topic or help you practice "
                f"another subject.",
                allow_interruptions=True,
            )

            raise StopResponse()

        # ----------------------------------------------------------
        # DAY 5 STEP 5 - SOURCE + DATE
        # ----------------------------------------------------------

        source_date = "August 10, 2026"

        spoken_response = (
            "Here's a question from my local hand-built "
            "practice set, prepared on "
            f"{source_date}. "
            f"{exercise['question']}"
        )

        # ----------------------------------------------------------
        # VERIFICATION LOGS
        # ----------------------------------------------------------

        logger.info(
            "DAY 5 FUNCTION LOOKUP: SUCCESS"
        )

        logger.info(
            f"DAY 5 FUNCTION LOOKUP: "
            f"subject={exercise['subject']}"
        )

        logger.info(
            f"DAY 5 FUNCTION LOOKUP: "
            f"level={exercise['level']}"
        )

        logger.info(
            f"DAY 5 FUNCTION LOOKUP: "
            f"topic={exercise['topic']}"
        )

        logger.info(
            f"DAY 5 FUNCTION LOOKUP: "
            f"exact question={exercise['question']}"
        )

        # ----------------------------------------------------------
        # SPEAK THE REAL DATABASE QUESTION
        # ----------------------------------------------------------

        await self.session.say(
            spoken_response,
            allow_interruptions=True,
        )

        # Stop Cohere from generating another answer.
        raise StopResponse()

    # --------------------------------------------------------------
    # DAY 4 - CALLER LOOKUP
    # --------------------------------------------------------------

    @function_tool
    async def lookup_caller(
        self,
    ) -> str:
        """Look up existing caller information and learning facts."""

        try:

            record = await get_latest_record(
                self.user_id
            )

        except Exception as e:

            logger.error(
                f"lookup_caller DB error: {e}"
            )

            return (
                "Caller lookup isn't available right now "
                "(database unreachable). Continue the conversation "
                "normally without relying on saved history for this turn."
            )

        if record:

            return (
                f"Caller Found: Name: {record['name']}, "
                f"Language: {record['language_preference']}, "
                f"Learning Facts: {record['facts']}"
            )

        return "No previous record found for this caller."

    # --------------------------------------------------------------
    # DAY 4 - SAVE CALLER INFO
    # --------------------------------------------------------------

    @function_tool
    async def save_caller_info(
        self,
        name: str,
        language_preference: str,
        current_level: str,
        topics_covered: str,
        struggles_or_mistakes: str,
    ) -> str:
        """Save caller profile and learning facts after verbal permission."""

        facts = {
            "current_level": current_level,
            "topics_covered": topics_covered,
            "struggles_or_mistakes": struggles_or_mistakes,
        }

        try:

            await persist_caller_record(
                self.user_id,
                name,
                language_preference,
                facts,
            )

        except Exception as e:

            logger.error(
                f"save_caller_info DB error: {e}"
            )

            return (
                "Saving isn't available right now "
                "(database unreachable). "
                "Let the learner know you couldn't save that just now, "
                "but you can keep helping them for the rest of this call."
            )

        return (
            "Caller profile and learning facts successfully "
            "saved to database."
        )

    # --------------------------------------------------------------
    # DAY 5 - FUNCTION TOOL
    # --------------------------------------------------------------

    @function_tool
    async def fetch_next_exercise(
        self,
        subject: str,
        level: str,
    ) -> str:
        """
        Fetch a real practice question from the local PostgreSQL
        exercise dataset for the requested subject and level.
        """

        try:

            exercise = await fetch_exercise(
                subject,
                level,
            )

        except Exception as e:

            logger.error(
                f"Exercise lookup failed: {e}"
            )

            return (
                "The practice question bank isn't reachable right now. "
                "Apologize briefly to the learner, and offer to explain "
                "the concept directly instead of giving a practice question."
            )

        if exercise is None:

            return (
                f"No exercise is available yet for the subject '{subject}'. "
                f"Let the learner know this topic isn't in the practice "
                f"bank yet, and offer to explain the concept instead."
            )

        return (
            f"Exercise found - subject: {exercise['subject']}, "
            f"level: {exercise['level']}, "
            f"topic: {exercise['topic']}. "
            f"Question: {exercise['question']} "
            f"Correct answer: {exercise['answer']}"
        )


# ------------------------------------------------------------------
# LIVEKIT SERVER
# ------------------------------------------------------------------

server = AgentServer()


def prewarm(
    proc: JobProcess,
):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(
    agent_name="my-agent"
)
async def my_agent(
    ctx: JobContext,
):

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # --------------------------------------------------------------
    # COHERE API KEY
    # --------------------------------------------------------------

    cohere_key = os.getenv(
        "COHERE_API_KEY",
        "",
    ).strip()

    if not cohere_key:

        logger.error(
            "COHERE_API_KEY is missing! "
            "Make sure COHERE_API_KEY is set in .env.local."
        )

    # --------------------------------------------------------------
    # AGENT SESSION - COHERE
    # --------------------------------------------------------------

    session = AgentSession(

        stt=deepgram.STT(
            model="nova-3",
            language="multi",
        ),

        llm=openai.LLM(
            model=COHERE_MODEL,
            api_key=cohere_key,
            base_url=COHERE_BASE_URL,
        ),

        tts=murf.TTS(
            model="falcon-2",
            voice="Alicia",
        ),

        vad=ctx.proc.userdata["vad"],

        preemptive_generation=False,
    )

    # --------------------------------------------------------------
    # CONNECT TO USER FIRST
    # --------------------------------------------------------------

    await ctx.connect()

    user_id = await resolve_user_id_async(
        ctx
    )

    logger.info(
        f"Resolved caller user_id: {user_id}"
    )

    # --------------------------------------------------------------
    # START SESSION
    # --------------------------------------------------------------

    await session.start(

        agent=Assistant(
            user_id=user_id
        ),

        room=ctx.room,

        room_options=room_io.RoomOptions(

            audio_input=room_io.AudioInputOptions(

                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),

            ),

        ),

    )

    # ==============================================================
    # DYNAMIC GREETING
    # ==============================================================

    try:

        caller_record = await get_latest_record(
            user_id
        )

    except Exception as e:

        logger.error(
            "Could not look up caller record, "
            f"falling back to first-time greeting: {e}"
        )

        caller_record = None

    if caller_record is None:

        greeting_text = FIRST_TIME_GREETING

    else:

        name = caller_record.get(
            "name",
            "there",
        )

        facts = caller_record.get(
            "facts",
            {},
        )

        if isinstance(
            facts,
            dict,
        ):

            previous_topic = facts.get(
                "topics_covered",
                "",
            )

            if not previous_topic:

                previous_messages = facts.get(
                    "last_session_messages",
                    [],
                )

                if previous_messages:

                    previous_topic = (
                        previous_messages[0]
                    )

        else:

            previous_topic = str(
                facts
            )

        if not previous_topic:

            previous_topic = (
                "our previous learning session"
            )

        if len(previous_topic) > 100:

            previous_topic = (
                previous_topic[:100]
                + "..."
            )

        greeting_text = (
            f"Welcome back, {name}! "
            f"Last time we spoke about {previous_topic}. "
            f"Would you like to continue with that, "
            f"or is there something else I can help you "
            f"with today?"
        )

    await session.say(
        greeting_text,
        allow_interruptions=True,
    )

    # ==============================================================
    # AUTOMATIC SHUTDOWN / DISCONNECT SAVING
    # ==============================================================

    async def _do_shutdown_save():

        chat_history = []

        if hasattr(
            session,
            "history",
        ):

            if callable(
                getattr(
                    session.history,
                    "messages",
                    None,
                )
            ):

                chat_history = (
                    session.history.messages()
                )

            elif isinstance(
                getattr(
                    session.history,
                    "messages",
                    None,
                ),
                list,
            ):

                chat_history = (
                    session.history.messages
                )

        user_texts = []

        for msg in chat_history:

            if (
                hasattr(msg, "role")
                and msg.role == "user"
                and hasattr(msg, "content")
                and msg.content
            ):

                content = msg.content

                if isinstance(
                    content,
                    list,
                ):

                    content = " ".join(
                        str(item)
                        for item in content
                    )

                user_texts.append(
                    str(content)
                )

        if not user_texts:

            logger.info(
                "No user conversation found to save."
            )

            return

        existing = (
            db.get_caller_record(
                user_id
            )
            or {}
        )

        name = existing.get(
            "name",
            "Learner",
        )

        language = existing.get(
            "language_preference",
            "English",
        )

        existing_facts = existing.get(
            "facts",
            {},
        )

        if not isinstance(
            existing_facts,
            dict,
        ):

            existing_facts = {}

        fallback_topic = existing_facts.get(
            "topics_covered",
            "a recent learning session",
        )

        # ----------------------------------------------------------
        # COHERE TOPIC SUMMARY
        # ----------------------------------------------------------

        previous_topic = await summarize_session_topic(
            user_texts,
            fallback=fallback_topic,
        )

        facts = {

            "current_level": existing_facts.get(
                "current_level",
                "Intermediate",
            ),

            "topics_covered": previous_topic,

            "struggles_or_mistakes": existing_facts.get(
                "struggles_or_mistakes",
                "None",
            ),

            "last_session_messages": user_texts[-5:],
        }

        db.save_caller_record(
            user_id,
            name,
            language,
            facts,
        )

        logger.info(
            f"Auto-saved session progress "
            f"for user_id={user_id}."
        )

    async def on_shutdown():

        try:

            await asyncio.wait_for(
                _do_shutdown_save(),
                timeout=8.0,
            )

        except asyncio.TimeoutError:

            logger.error(
                "Shutdown save timed out entirely."
            )

        except Exception as e:

            logger.error(
                f"Auto-save on shutdown failed: {e}"
            )

    ctx.add_shutdown_callback(
        on_shutdown
    )


# ------------------------------------------------------------------
# RUN APPLICATION
# ------------------------------------------------------------------

if __name__ == "__main__":
    cli.run_app(server)