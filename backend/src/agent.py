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

from livekit.plugins import (
    murf,
    silero,
    openai,
    deepgram,
    noise_cancellation,
)

# Import DB helper module
import db

# Initialize PostgreSQL database table on launch
db.init_db()

logger = logging.getLogger("agent")

load_dotenv(".env.local")


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
    """
    Derive a stable per-caller user_id.

    Priority:
    1. The remote participant's identity (set by your frontend token /
       SIP caller number) - this is what makes memory actually per-person.
    2. A fallback "guest" id if no participant identity is available yet
       (e.g. testing before a participant has joined).
    """
    for participant in ctx.room.remote_participants.values():
        if participant.identity:
            return participant.identity

    # Fallback used only if called before a participant is present.
    return "guest"


# ------------------------------------------------------------------
# DATABASE HELPERS (run sync psycopg2 calls off the event loop)
# ------------------------------------------------------------------


async def get_latest_record(user_id: str):
    """Retrieve the saved caller record for this specific user_id."""
    return await asyncio.to_thread(db.get_caller_record, user_id)


async def persist_caller_record(user_id: str, name: str, language: str, facts: dict):
    """Save/update a single caller record for this specific user_id."""
    await asyncio.to_thread(
        db.save_caller_record,
        user_id,
        name,
        language,
        facts,
    )


# ------------------------------------------------------------------
# ASSISTANT
# ------------------------------------------------------------------


class Assistant(Agent):

    def __init__(self, user_id: str) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self.user_id = user_id

    @function_tool
    async def lookup_caller(self) -> str:
        """Look up existing caller information and learning facts."""

        record = await get_latest_record(self.user_id)

        if record:
            return (
                f"Caller Found: Name: {record['name']}, "
                f"Language: {record['language_preference']}, "
                f"Learning Facts: {record['facts']}"
            )

        return "No previous record found for this caller."

    @function_tool
    async def save_caller_info(
        self,
        name: str,
        language_preference: str,
        current_level: str,
        topics_covered: str,
        struggles_or_mistakes: str,
    ) -> str:
        """
        Save caller profile and learning facts.
        Only call this AFTER the caller has given verbal permission.
        """

        facts = {
            "current_level": current_level,
            "topics_covered": topics_covered,
            "struggles_or_mistakes": struggles_or_mistakes,
        }

        await persist_caller_record(
            self.user_id,
            name,
            language_preference,
            facts,
        )

        return "Caller profile and learning facts successfully saved to database."


# ------------------------------------------------------------------
# LIVEKIT SERVER
# ------------------------------------------------------------------

server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3",
            language="multi",
        ),
        llm=openai.LLM(
            model="openrouter/free",
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        ),
        tts=murf.TTS(
            model="falcon-2",
            voice="Alicia",
        ),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=False,
    )

    # --------------------------------------------------------------
    # CONNECT TO USER FIRST so we have a real participant identity
    # --------------------------------------------------------------

    await ctx.connect()

    user_id = resolve_user_id(ctx)
    logger.info(f"Resolved caller user_id: {user_id}")

    # --------------------------------------------------------------
    # START SESSION
    # --------------------------------------------------------------

    await session.start(
        agent=Assistant(user_id=user_id),
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
    # FIRST-TIME vs RETURNING CALLER
    # ==============================================================

    caller_record = await get_latest_record(user_id)

    if caller_record is None:

        # ----------------------------------------------------------
        # FIRST-TIME CALLER
        # ----------------------------------------------------------

        greeting_text = FIRST_TIME_GREETING

    else:

        # ----------------------------------------------------------
        # RETURNING CALLER
        # ----------------------------------------------------------

        name = caller_record.get("name", "there")
        facts = caller_record.get("facts", {})

        # ----------------------------------------------------------
        # GET PREVIOUS TOPIC
        # ----------------------------------------------------------

        if isinstance(facts, dict):

            previous_topic = facts.get("topics_covered", "")

            if not previous_topic:

                previous_messages = facts.get("last_session_messages", [])

                if previous_messages:
                    previous_topic = previous_messages[0]

        else:
            previous_topic = str(facts)

        if not previous_topic:
            previous_topic = "our previous learning session"

        if len(previous_topic) > 100:
            previous_topic = previous_topic[:100] + "..."

        # ----------------------------------------------------------
        # RETURNING GREETING
        # ----------------------------------------------------------

        greeting_text = (
            f"Welcome back, {name}! "
            f"Last time we spoke about {previous_topic}. "
            f"Would you like to continue with that, "
            f"or is there something else I can help you with today?"
        )

    # Speak greeting
    await session.say(
        greeting_text,
        allow_interruptions=True,
    )

    # ==============================================================
    # AUTOMATIC SHUTDOWN / DISCONNECT SAVING
    # ==============================================================

    def on_shutdown():

        try:

            # Safely check for history messages
            chat_history = []
            if hasattr(session, "history"):
                if callable(getattr(session.history, "messages", None)):
                    chat_history = session.history.messages()
                elif isinstance(getattr(session.history, "messages", None), list):
                    chat_history = session.history.messages

            user_texts = []

            for msg in chat_history:

                if (
                    hasattr(msg, "role")
                    and msg.role == "user"
                    and hasattr(msg, "content")
                    and msg.content
                ):

                    content = msg.content

                    if isinstance(content, list):
                        content = " ".join(str(item) for item in content)

                    user_texts.append(str(content))

            if not user_texts:
                logger.info("No user conversation found to save.")
                return

            # NOTE: this auto-save on shutdown bypasses the verbal-consent
            # gate described in the system prompt. Day 4 requires consent
            # before saving, especially outside pure learning-progress
            # data. Keep this ONLY if you treat "topics covered this
            # session" as low-sensitivity progress tracking that's fine
            # to log automatically; for anything more personal, remove
            # this block and rely solely on the save_caller_info tool
            # call (which the agent only triggers after asking).

            existing = db.get_caller_record(user_id) or {}

            name = existing.get("name", "Learner")
            language = existing.get("language_preference", "English")

            previous_topic = user_texts[-1].strip()

            if len(previous_topic) > 100:
                previous_topic = previous_topic[:100] + "..."

            existing_facts = existing.get("facts", {})

            if not isinstance(existing_facts, dict):
                existing_facts = {}

            facts = {
                "current_level": existing_facts.get("current_level", "Intermediate"),
                "topics_covered": previous_topic,
                "struggles_or_mistakes": existing_facts.get(
                    "struggles_or_mistakes", "None"
                ),
                "last_session_messages": user_texts[-5:],
            }

            db.save_caller_record(
                user_id,
                name,
                language,
                facts,
            )

            logger.info(f"Auto-saved session progress for user_id={user_id}.")

        except Exception as e:
            logger.error(f"Auto-save on shutdown failed: {e}")

    ctx.add_shutdown_callback(on_shutdown)


# ------------------------------------------------------------------
# RUN APPLICATION
# ------------------------------------------------------------------

if __name__ == "__main__":
    cli.run_app(server)
