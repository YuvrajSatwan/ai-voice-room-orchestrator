# ROXSTAR AI Voice Room Assistant

Two AI participants in a multi-user LiveKit voice room, speaking natural Hindi/Hinglish:

- **Roxstar AI Dost** (`ai-dost`): male voice, calm and practical
- **Roxstar AI Sathi** (`ai-sathi`): female voice, warm and encouraging

Humans talk by voice or chat. One "room brain" hears everyone, picks which bot answers, and makes
sure only one bot speaks at a time. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ·
[docs/DECISIONS.md](docs/DECISIONS.md)

## Project layout

```
src/roxstar/
  worker.py        LiveKit entry point: wires everything for one room
  listener.py      one speech-to-text stream per human mic (+ barge-in)
  brain.py         every turn: remember -> route -> floor -> LLM -> speak
  routing.py       which bot answers
  context.py       room memory: last 12 turns + per-speaker facts
  floor.py         the "only one bot speaks" lock
  voices.py        each bot's own LiveKit participant (TTS audio + chat)
  llm.py           Gemini reply function (with fallback model)
  moderation.py    abuse filter: calm fixed reply, slur masked, LLM never called
  personas.py      Dost and Sathi: prompts and voices
  telemetry.py     per-reply latency log line
  config.py, log.py, domain.py
  token_server.py  browser tokens + worker dispatch (POST /token, GET /health)
  server.py        hosted entry point: worker in the background + token server on $PORT
web/               the room UI: React + LiveKit (presence, transcript, intelligence panel)
tests/             brain scenarios, routing, memory, floor, helpers (no network)
docs/              architecture, decisions, interview notes
```

## Prerequisites
- Python 3.11+, Node 18+
- Accounts: [LiveKit Cloud](https://cloud.livekit.io), [Sarvam AI](https://www.sarvam.ai),
  and [Gemini](https://aistudio.google.com)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
cp .env.example .env              # then fill in the keys
cd web && npm install
```

## Run (three terminals, from the repo root)

```bash
python -m roxstar.worker dev          # 1. the worker (brain + both bots)
python -m roxstar.token_server        # 2. token server on port 8000
cd web && npm run dev                 # 3. the UI on http://localhost:5174
```

To show failure handling in the demo, start the worker with `ROXSTAR_DEMO_CONTROLS=true` and
type `/fail llm` (the bot apologizes) or `/fail tts` (the answer arrives as text only) in chat.

Open the UI in two browser windows with different names (e.g. Rahul and Priya) and the same room.
Both bots join automatically. Speak, or type in the chat.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | yes | — | LiveKit Cloud project |
| `SARVAM_API_KEY` | yes (voice) | — | Sarvam speech-to-text and text-to-speech |
| `GEMINI_API_KEY` | yes | — | Gemini replies and summaries |
| `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL` | no | `gemini-3.5-flash-lite` / `gemini-flash-lite-latest` | main and fallback model |
| `SARVAM_STT_MODEL` / `SARVAM_STT_MODE` | no | `saaras:v3` / `codemix` | speech-to-text model and mode |
| `ROXSTAR_LOG_LEVEL` / `ROXSTAR_LOG_FORMAT` | no | `INFO` / `json` | logging |
| `ROXSTAR_LOG_TRANSCRIPTS` | no | off | also log conversation text (demo/debug only) |
| `ROXSTAR_DEMO_CONTROLS` | no | off | enables `/fail llm` and `/fail tts` in chat |
| `HOST` / `PORT` | no | `0.0.0.0` / `8000` | token server bind address |
| `VITE_TOKEN_URL` (in `web/.env`) | no | `http://127.0.0.1:8000` | where the UI asks for tokens |

## Deploy (Render)
`render.yaml` defines two services: `roxstar-backend` runs `python -m roxstar.server` (the worker
plus the token server on `$PORT`), and `roxstar-frontend` builds `web/` as a static site. The
token server has no user authentication, so a public deployment lets anyone who finds the URL
join rooms and start the bots (and spend API credits).

## Test

```bash
pytest            # scenarios run against fake bots and a fake LLM, no keys needed
ROXSTAR_LIVE_TESTS=1 pytest tests/test_style_live.py -v   # Hinglish style vs real Gemini
ruff check src tests
```

## Measured latency
Median over 17 live voice replies: LLM 1.2 s, first bot audio 3.0 s after the final
transcript (p90 4.8 s). Breakdown in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#7-measured-latency).

## Status
- ✅ Phase 1: both bots live in the room, multi-user listening, two-bot routing, barge-in, failure handling
- ✅ Phase 2: Hinglish even for English, reply only when relevant, short replies, style tests, voices (`shubh`, `simran`)
- ✅ Phase 3: live checks (two humans, reconnect, `/fail` demo switch, latency measured)
- ✅ Phase 4: "Abhi tak kya discuss hua?" rolling summary, moderation
- ✅ Git repository and Render deployment config
- ⏳ Demo video, cost notes
