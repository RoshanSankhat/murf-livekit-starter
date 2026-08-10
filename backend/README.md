Backend — Voice Agent with Murf Falcon TTS

The Python backend for the Voice Agent Starter. It runs a real-time voice AI pipeline using LiveKit Agents, connecting Murf Falcon TTS, Deepgram STT, and Google Gemini into a single conversational agent.

How It Works
User speaks → [Deepgram STT] → text → [LLM] → response → [Murf Falcon TTS] → audio → User hears

LiveKit handles the real-time audio transport. The agent connects to LiveKit as a participant, listens for user speech, and responds with synthesized audio.

Setup
1. Install dependencies
bash
cd backend
uv sync
2. Configure environment
bash
cp .env.example .env.local

Fill in your keys in .env.local:

Variable	Where to get it
LIVEKIT_URL	LiveKit Cloud → Settings
LIVEKIT_API_KEY	LiveKit Cloud → Settings
LIVEKIT_API_SECRET	LiveKit Cloud → Settings
MURF_API_KEY	murf.ai/api/dashboard
DEEPGRAM_API_KEY	deepgram.com
GOOGLE_API_KEY	aistudio.google.com — not used in this build, see LLM section below
OPENROUTER_API_KEY	openrouter.ai — used for the LLM and for topic summarization

For LiveKit Cloud users, you can auto-populate LiveKit credentials:

bash
lk cloud auth
lk app env -w -d .env.local
3. Download models
bash
uv run python src/agent.py download-files

This downloads Silero VAD and the LiveKit turn detector models.

4. Run the agent
bash
# Development mode (auto-reload)
uv run python src/agent.py dev

# Or test directly in your terminal (no frontend needed)
uv run python src/agent.py console

# Production
uv run python src/agent.py start
Configuration

All configuration lives in src/agent.py.

System prompt

The SYSTEM_PROMPT constant at the top of agent.py controls what your agent does. Change it to build any voice-powered use case.

Example prompts

Customer Support (default):

You are a friendly and efficient customer support agent for a tech company. Help users with account issues, billing questions, and product troubleshooting. Be concise, empathetic, and solution-oriented. If you don't know something, say so honestly and offer to escalate.

Language Tutor:

You are a patient and encouraging language tutor helping the user practice conversational Spanish. Speak primarily in Spanish but switch to English to explain grammar or vocabulary when needed. Correct mistakes gently and suggest better phrasing. Keep conversations natural and fun.

AI Receptionist:

You are a professional receptionist for a medical clinic. Help callers schedule appointments, answer questions about office hours and services, and take messages for doctors. Be warm but efficient. Ask for the caller's name and reason for calling upfront.

Interview Coach:

You are an experienced interview coach. Conduct mock interviews with the user for software engineering roles. Ask one behavioral or technical question at a time, let the user answer fully, then give specific feedback on their response — what was strong, what could improve, and a suggested reframe. Keep the tone encouraging but honest.

Sales Assistant:

You are a knowledgeable sales assistant for an electronics store. Help customers find the right product by asking about their needs, budget, and preferences. Compare options clearly, highlight trade-offs, and make a recommendation. Never be pushy — focus on helping the customer make the best decision for them.

Fitness Coach:

You are an upbeat personal fitness coach. Help users plan workouts, suggest exercises for specific muscle groups, and answer questions about form and technique. Ask about their fitness level and any injuries before recommending exercises. Keep instructions clear and motivating.

Storyteller / Bedtime Narrator:

You are a creative storyteller who tells original bedtime stories for children aged 4–8. Ask the child (or parent) for a character name, a favorite animal, and a setting, then weave a short, calming story. Use vivid but simple language. End each story on a peaceful, sleepy note.

Meeting Summarizer:

You are a meeting assistant. The user will describe what happened in a meeting or read you their notes. Summarize the key decisions, action items (with owners if mentioned), and any open questions. Be concise and structured. Ask clarifying questions if something is ambiguous.

Trivia Game Host:

You are an enthusiastic trivia game host. Ask the user one trivia question at a time from a mix of categories — science, history, pop culture, geography, and sports. Wait for their answer, tell them if they're right or wrong, give a brief fun fact, then move to the next question. Keep score and announce it every 5 questions.

Mental Health Check-in Companion:

You are a gentle, non-clinical wellness companion. Help users talk through their day, reflect on how they're feeling, and practice simple grounding exercises like deep breathing or gratitude lists. You are not a therapist — if the user expresses serious distress or mentions self-harm, gently encourage them to reach out to a professional or crisis helpline.
Voice

Set the voice argument in the murf.TTS(...) call:

python
tts=murf.TTS(
    voice="en-US-matthew",    # Change this
    style="Conversation",
    tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
    text_pacing=True
)

Some voice options:

Voice ID	Description
Anisha	Indian English, female (default)
Pooja	Indian English, female
Samar	Indian English, male
Amara	US English, female
Hazel	UK English, female
Bertie	UK English, male
Gordon	US English, male

Browse all 150+ voices: Murf Voice Library.

STT (Speech-to-Text)

Default is Deepgram Nova-3. Change in the AgentSession(stt=...) call:

python
stt=deepgram.STT(model="nova-3")
LLM

This build uses OpenRouter's free tier (openrouter/free), set in the AgentSession(llm=...) call. Note: the free tier can be slow or occasionally return empty responses — see the Day 4 section below for how the agent handles that.

To switch:

OpenRouter (current): Set OPENROUTER_API_KEY in .env.local
Gemini: Set GOOGLE_API_KEY, install livekit-agents[google], and change the llm= argument
OpenAI: Set OPENAI_API_KEY, install livekit-agents[openai], and change the llm= argument
Memory & Practice Exercises (Day 4 / Day 5)

Memory (Day 4): Caller data is stored in a local Postgres callers table (db.py), only after the agent asks for consent. On session end, a short topic summary (not the raw last message) is saved so returning-caller greetings sound natural. Because the free-tier LLM is occasionally unreliable, topic summarization has a timeout and a keyword-based fallback so a bad/slow model response never breaks the greeting.

Practice exercises (Day 5): fetch_next_exercise(subject, level) pulls from a local hand-built dataset (Postgres exercises table, db.py), not a live external API — there's no single public API covering practice questions across all subjects this agent tutors (Math, English, Science, Social Studies). Seeded with ~20 starter questions across 3 difficulty levels. If the database is unreachable, the tool returns a graceful spoken fallback instead of crashing or going silent.

Testing

The project includes an eval suite based on the LiveKit Agents testing framework:

bash
uv run pytest

Tests are in tests/test_agent.py and use LLM-as-judge evaluations to verify the agent behaves correctly (friendly greetings, grounding, refusing harmful requests).

To run tests in CI, you'll need to add LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET as repository secrets.

Deployment
Railway

Show Image

Set these environment variables in Railway:

MURF_API_KEY
DEEPGRAM_API_KEY
OPENROUTER_API_KEY
LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
Docker

A production-ready Dockerfile is included:

bash
docker build -t murf-voice-agent .
docker run --env-file .env.local murf-voice-agent
Project Structure
backend/
├── src/
│   ├── agent.py          # Agent entrypoint — pipeline, prompt, config
│   └── db.py              # Postgres helpers — caller memory + exercises table
├── tests/
│   └── test_agent.py     # LLM-judged eval suite
├── .env.example           # Environment variable template
├── pyproject.toml         # Python dependencies (uv)
├── Dockerfile             # Production container
└── railway.toml           # Railway deploy config
Links
Murf Falcon TTS Docs
Murf Voice Library
LiveKit Agents Docs
Deepgram Nova-3 Docs
License

MIT — see LICENSE.