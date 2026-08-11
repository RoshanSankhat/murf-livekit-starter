import asyncio
import logging
import os

from dotenv import load_dotenv
from livekit import api, rtc

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

13. OUTBOUND COMPLIANCE (DAY 6):
    If the user indicates they want to stop, opt-out, or hang up,
    say a brief, polite goodbye, then IMMEDIATELY call the end_call
    tool to actually end the call. Do not just acknowledge verbally -
    you must call end_call every time the user asks to stop or hang up.

KNOWLEDGE:
- You can help with normal primary and secondary school educational subjects.
- You can explain concepts step by step.
- You can solve educational problems and explain the reasoning.
- You can provide examples and practice exercises.
- You should not pretend to know information you are unsure about.
- You do NOT need to restrict learning to English, reading, or vocabulary.
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
- For English, help with vocabulary, grammar, reading, pronunciation, spelling, and writing.
- For history and geography, explain facts clearly and provide useful context.
- If the learner says they do not understand, explain the same concept in a simpler way.
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
# GREETINGS & COMPLIANT OPENINGS
# ------------------------------------------------------------------

# Day 6 Strict Outbound Opening Requirement (Who, Why, How to Opt-out)
OUTBOUND_OPENING = (
    "Hello! This is Alexa, your Learning and Literacy Coach from R's World, "
    "calling for your scheduled daily educational practice session. "
    "If you would like to stop receiving these calls, you can say stop calling or hang up at any time. "
    "Are you ready for a quick practice question today?"
)

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


def is_sip_participant(ctx: JobContext) -> bool:
    """Check if any remote participant connected over SIP telephony (phone call)."""
    for participant in ctx.room.remote_participants.values():
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            return True
    return False


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


def guess_topic_from_text(user_texts: list[str]):
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
    normalized = text.lower().strip()
    return any(keyword in normalized for keyword in _PRACTICE_KEYWORDS)


def detect_subject(text: str):
    normalized = text.lower()
    for keyword in sorted(_SUBJECT_KEYWORDS, key=len, reverse=True):
        if keyword in normalized:
            return _SUBJECT_KEYWORDS[keyword]
    return None


def detect_level(text: str) -> str:
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
    api_key=os.getenv("COHERE_API_KEY", "").strip(),
)


async def summarize_session_topic(
    user_texts: list[str],
    fallback: str,
) -> str:
    conversation_snippet = " | ".join(
        t for t in user_texts[-8:] if t.strip()
    )

    if len(conversation_snippet) < 15:
        return guess_topic_from_text(user_texts) or fallback

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
                            "ONLY the topic label itself - nothing else."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Conversation: {conversation_snippet}\nTopic label:",
                    },
                ],
            ),
            timeout=5.0,
        )

        raw_content = response.choices[0].message.content
        summary = (raw_content or "").strip().strip('"').strip("'")

        if summary and len(summary) <= 100:
            return summary

    except Exception as e:
        logger.error(f"Cohere topic summary generation failed: {e}")

    return guess_topic_from_text(user_texts) or fallback


# ------------------------------------------------------------------
# ASSISTANT
# ------------------------------------------------------------------

class Assistant(Agent):

    def __init__(self, user_id: str, ctx: JobContext) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self.user_id = user_id
        self._ctx = ctx

    # --------------------------------------------------------------
    # DAY 5 - DETERMINISTIC LOOKUP HOOK
    # --------------------------------------------------------------

    async def on_user_turn_completed(
        self,
        turn_ctx,
        new_message,
    ) -> None:
        user_text = (new_message.text_content or "").strip()

        if not user_text or not is_practice_request(user_text):
            return

        logger.info(f"DAY 5 HOOK: practice request detected: {user_text}")

        subject = detect_subject(user_text)
        level = detect_level(user_text)

        if subject is None:
            await self.session.say(
                "Sure. Which subject would you like to practice?",
                allow_interruptions=True,
            )
            raise StopResponse()

        try:
            exercise = await fetch_exercise(subject, level)
        except Exception as e:
            logger.error(f"DAY 5 HOOK: database lookup failed: {e}")
            await self.session.say(
                "I cannot reach my practice question bank right now. "
                "I can still explain the topic directly if you would like.",
                allow_interruptions=True,
            )
            raise StopResponse()

        if exercise is None:
            await self.session.say(
                f"I do not have a practice question for {subject} at that level yet.",
                allow_interruptions=True,
            )
            raise StopResponse()

        source_date = "August 10, 2026"
        spoken_response = (
            f"Here's a question from my local hand-built practice set, prepared on {source_date}. "
            f"{exercise['question']}"
        )

        await self.session.say(spoken_response, allow_interruptions=True)
        raise StopResponse()

    # --------------------------------------------------------------
    # FUNCTION TOOLS
    # --------------------------------------------------------------

    @function_tool
    async def lookup_caller(self) -> str:
        """Look up existing caller information and learning facts."""
        try:
            record = await get_latest_record(self.user_id)
        except Exception as e:
            return "Caller lookup isn't available right now."

        if record:
            return f"Caller Found: Name: {record['name']}, Facts: {record['facts']}"
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
        """Save caller profile and learning facts after verbal permission."""
        facts = {
            "current_level": current_level,
            "topics_covered": topics_covered,
            "struggles_or_mistakes": struggles_or_mistakes,
        }
        try:
            await persist_caller_record(self.user_id, name, language_preference, facts)
        except Exception as e:
            return "Saving isn't available right now."
        return "Caller profile and learning facts successfully saved."

    @function_tool
    async def fetch_next_exercise(self, subject: str, level: str) -> str:
        """Fetch a practice question from the PostgreSQL exercise dataset."""
        try:
            exercise = await fetch_exercise(subject, level)
        except Exception as e:
            return "The practice question bank isn't reachable right now."

        if exercise is None:
            return f"No exercise is available yet for {subject}."

        return f"Exercise found: {exercise['question']} Answer: {exercise['answer']}"

    @function_tool
    async def end_call(self) -> str:
        """Call this when the learner wants to stop, opt out, or hang up
        (e.g. says 'stop calling', 'hang up', 'not interested', 'remove me').
        Say a brief goodbye BEFORE calling this, since the call will be
        disconnected immediately after this tool runs."""
        try:
            # Give the goodbye audio a moment to actually play out over SIP
            await asyncio.sleep(1.5)

            await self._ctx.api.room.delete_room(
                api.DeleteRoomRequest(room=self._ctx.room.name)
            )
            logger.info(f"Call ended via end_call tool for room={self._ctx.room.name}")
            return "Call ended successfully."
        except Exception as e:
            logger.error(f"end_call failed: {e}")
            return "Failed to end the call cleanly."


# ------------------------------------------------------------------
# LIVEKIT SERVER
# ------------------------------------------------------------------

server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):

    ctx.log_context_fields = {"room": ctx.room.name}

    cohere_key = os.getenv("COHERE_API_KEY", "").strip()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.LLM(
            model=COHERE_MODEL,
            api_key=cohere_key,
            base_url=COHERE_BASE_URL,
        ),
        tts=murf.TTS(model="falcon-2", voice="Alicia"),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=False,
    )

    await ctx.connect()
    user_id = await resolve_user_id_async(ctx)

    # ==============================================================
    # AUTO-CLEANUP WHEN THE CALLEE HANGS UP (e.g. Linphone hangup button)
    # ==============================================================
    # If the SIP leg disconnects from the other side, the LiveKit room
    # doesn't automatically go away. Without this, the agent keeps running
    # and someone has to manually run a delete_room script to clean up.

    async def _cleanup_room_after_sip_hangup():
        try:
            await ctx.api.room.delete_room(
                api.DeleteRoomRequest(room=ctx.room.name)
            )
            logger.info(
                f"Room deleted after SIP participant hangup: room={ctx.room.name}"
            )
        except Exception as e:
            logger.error(f"Failed to delete room after SIP disconnect: {e}")

    def _on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info(
            f"participant_disconnected fired: identity={participant.identity}, kind={participant.kind}"
        )
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            logger.info(
                f"SIP participant '{participant.identity}' hung up - ending call and cleaning up room."
            )
            asyncio.create_task(_cleanup_room_after_sip_hangup())

    ctx.room.on("participant_disconnected", _on_participant_disconnected)

    await session.start(
        agent=Assistant(user_id=user_id, ctx=ctx),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    # ==============================================================
    # DAY 6 - DYNAMIC GREETING / OUTBOUND COMPLIANCE SELECTION
    # ==============================================================

    # 1. If this call is over SIP (Telephony/Outbound Phone Call)
    if is_sip_participant(ctx):
        greeting_text = OUTBOUND_OPENING
        logger.info("Outbound SIP participant detected - using compliant Day 6 opening script.")

    # 2. Standard Web/Inbound Dynamic Greeting Flow
    else:
        try:
            caller_record = await get_latest_record(user_id)
        except Exception as e:
            caller_record = None

        if caller_record is None:
            greeting_text = FIRST_TIME_GREETING
        else:
            name = caller_record.get("name", "there")
            facts = caller_record.get("facts", {})
            previous_topic = (
                facts.get("topics_covered", "our previous learning session")
                if isinstance(facts, dict) else "our previous learning session"
            )
            greeting_text = (
                f"Welcome back, {name}! Last time we spoke about {previous_topic}. "
                f"Would you like to continue with that, or practice something else today?"
            )

    await session.say(greeting_text, allow_interruptions=True)

    # ==============================================================
    # AUTOMATIC SHUTDOWN / DISCONNECT SAVING
    # ==============================================================

    async def _do_shutdown_save():
        chat_history = []
        if hasattr(session, "history"):
            chat_history = (
                session.history.messages()
                if callable(getattr(session.history, "messages", None))
                else getattr(session.history, "messages", [])
            )

        user_texts = [
            str(msg.content) for msg in chat_history
            if hasattr(msg, "role") and msg.role == "user" and getattr(msg, "content", None)
        ]

        if not user_texts:
            return

        existing = db.get_caller_record(user_id) or {}
        name = existing.get("name", "Learner")
        language = existing.get("language_preference", "English")
        existing_facts = existing.get("facts", {}) if isinstance(existing.get("facts"), dict) else {}

        previous_topic = await summarize_session_topic(
            user_texts, fallback=existing_facts.get("topics_covered", "a recent session")
        )

        facts = {
            "current_level": existing_facts.get("current_level", "Intermediate"),
            "topics_covered": previous_topic,
            "struggles_or_mistakes": existing_facts.get("struggles_or_mistakes", "None"),
            "last_session_messages": user_texts[-5:],
        }

        db.save_caller_record(user_id, name, language, facts)
        logger.info(f"Auto-saved session progress for user_id={user_id}.")

    async def on_shutdown():
        try:
            await asyncio.wait_for(_do_shutdown_save(), timeout=8.0)
        except Exception as e:
            logger.error(f"Auto-save on shutdown failed: {e}")

    ctx.add_shutdown_callback(on_shutdown)


if __name__ == "__main__":
    cli.run_app(server)