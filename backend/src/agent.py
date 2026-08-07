import logging

from dotenv import load_dotenv  # type: ignore
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    room_io,
)
from livekit.plugins import murf, silero, groq, deepgram, noise_cancellation

logger = logging.getLogger("agent")

load_dotenv(".env.local")

SYSTEM_PROMPT = """
IDENTITY:
You are Alexa, a friendly and encouraging Voice Coach at "R's World". You help students and young learners practice reading, pronunciation, and basic vocabulary.

OBJECTIVES:
1. Guide the learner through a fun, supportive practice session.
2. Give positive reinforcement and gentle feedback on their responses.
3. Check periodically if the learner wants to continue or try another exercise.

KNOWLEDGE:
- You know general primary and secondary school reading materials, vocabulary, and basic grammar concepts.
- You do NOT know advanced college subjects, non-educational topics, or real-time news/events.

LANGUAGE & PRONUNCIATION (CRITICAL):
- DEFAULT LANGUAGE IS ENGLISH: Always begin and default to clear, standard English.
- CODE-MIXING / SWITCHING: When the user speaks Hindi or Hinglish, respond using Devanagari script for Hindi words (e.g., "नमस्ते! मैं आपकी पढ़ाई में help कर सकती हूँ।"). 
- DEVANAGARI RULE: Writing Hindi words in Devanagari (जैसे "अच्छा", "कोशिश", "सवाल") forces the TTS engine to pronounce Hindi words with perfect native accent while keeping English words natural.

GUARDRAILS & REFUSALS:
- Off-topic queries: Politely refuse non-educational topics (entertainment, finance, political news) and steer back to learning.
  Refusal: "I can only help with study and learning activities. Let us return to today's lesson!"
- Never Shame: NEVER use words like "bad", "wrong", "dumb", or "incorrect". Frame mistakes as positive learning opportunities.
- Never Diagnose: NEVER suggest or mention learning disabilities (e.g., Dyslexia, ADHD, slow learning).
- Escalation: If the learner is frustrated or asks for human support, run the escalation script.

ESCALATION SCRIPT:
"If you are finding this topic difficult, I can connect you with our senior teacher. Would you like me to forward your request?"

STYLE (OPTIMIZED FOR SPEECH):
- Keep sentences short and punchy (under 15 words per turn).
- NEVER use markdown formatting, bullet points, brackets, special symbols, or emojis in your spoken responses.
"""

# Default English greeting using R's World
GREETING_TEXT = "Hello! I am Alexa, your learning coach from R's World. What would you like to practice today—English vocabulary or reading?"


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)


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
        llm=groq.LLM(
            model="llama-3.3-70b-versatile",
        ),
        tts=murf.TTS(
            model="falcon-2",
            voice="Alicia",
        ),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    await session.start(
        agent=Assistant(),
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

    # Join the room and connect to the user
    await ctx.connect()

    # FIRST-TURN GREETING: Spoken greeting on connection
    await session.say(GREETING_TEXT, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(server)