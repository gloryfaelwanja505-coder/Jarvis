# JARVIS

JARVIS is a local-first personal assistant with a FastAPI backend, a React
command-center UI, persistent SQLite data, and an opt-in scheduled calling
control plane. Calls default to disabled. Internet audio, online AI providers,
and chargeable telephone calls are reported as unavailable until their
dependencies and explicit permissions are configured.

## What works

- Local Ollama chat with persistent conversation history by default. Ollama
  responses stream into the UI and chat data stays on-device when Ollama runs
  locally. OpenAI Responses API remains available by selecting another
  `JARVIS_AI_PROVIDER` and configuring its key.
- Persistent chat-task status and checkpoints, safe interruption recovery, and
  user-confirmed retries. A completed request ID returns its saved response;
  unfinished work is never replayed automatically.
- User-approved preferences and configurable assistant personality persist
  locally and can inform future conversations.
- Local email/message drafts can be reviewed and approved, with status and
  audit history. Approval does not send; delivery providers are not configured.
- Editable daily morning and evening schedules (defaults: 07:00 and 17:00
  Africa/Nairobi time), Do Not Disturb, retry controls, and call history.
- Persistent call sessions and attempt outcomes, unique daily occurrence keys,
  active-call overlap protection, and recovery of missed/interrupted calls
  after a backend restart.
- Token-protected schedule/history APIs and WebSocket signaling; optional
  HTTPS/WSS enforcement.
- Optional Ollama, Gemini, and Groq voice-conversation backends. Ollama is the
  default and can operate locally when a matching model is installed.
- Optional WebRTC audio with authenticated SDP/ICE signaling, microphone and
  speaker controls, browser reconnection, and local Whisper/Piper adapters.
- Optional Twilio outbound telephone calls and signed status/media webhooks.
  Test mode is on by default and blocks paid calls.

The UI reports the current runtime capabilities. No live WebRTC audio or
telephone call has been verified in this environment. A browser cannot receive
calls while closed, and no Android push-notification companion is included.
Keep the dashboard connected for internet calls; a backend scheduler alone
cannot wake a powered-off laptop or closed browser.

## Requirements and local setup

- Ubuntu or another Linux distribution
- Python 3.12+
- Node.js 20+ and npm
- Ollama with the configured model for local chat (default:
  `llama3.2:1b`). No cloud API key is required for this setup.

```bash
cp backend/.env.example backend/.env
```

Generate a private calling token:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Put that value in `JARVIS_CALLING_ACCESS_TOKEN` in `backend/.env`; do not
commit the file. Install and start the local app:

```bash
./scripts/install.sh
./scripts/start.sh
```

Open <http://127.0.0.1:5173>. The API listens on
<http://127.0.0.1:8000>; health is at `/api/health`. The scripts run in the
foreground; use Ctrl+C to stop them. The backend binds to localhost by default.
Calling settings and call history require the configured access token in the
calling dashboard.

For manual setup, create a Python virtual environment, install
`backend/requirements.txt`, run `uvicorn app.main:app` from `backend/`, and run
`npm install && npm run dev` from `frontend/`.

The FastAPI lifespan applies the Alembic calling migration and seeds the
07:00/17:00 schedules. Call scheduling is globally disabled by default; enable
it in the dashboard. Schedule times are interpreted in the selected IANA
timezone and saved in SQLite.

## Optional local voice stack

Install the extra Python packages only when enabling offline voice:

```bash
.venv/bin/python -m pip install -r backend/requirements-voice.txt
```

Download a compatible Vosk model yourself and set `JARVIS_VOSK_MODEL_PATH`;
models are not downloaded automatically. Background listening is opt-in from
JARVIS Settings and requires browser microphone permission, a local speech
recognizer, and a compatible openWakeWord model configured with
`JARVIS_WAKE_WORD_MODEL_PATH`. Audio is streamed to the local backend for wake
word detection; after detection, the utterance is transcribed locally. The
default requested phrase is `Hello JARVIS Scott here`
(`JARVIS_WAKE_WORD_PHRASE`). This setting labels the phrase; it does not adapt
or train a wake-word model, so the configured model must recognize that phrase.
When the local model or recognizer is missing, background listening stays
unavailable and the UI reports that state. Whisper remains an optional
alternative and may download its model on first use.

Install Piper and a compatible voice model separately, then set
`JARVIS_PIPER_BINARY` and `JARVIS_PIPER_MODEL_PATH`. Use
`JARVIS_PIPER_LENGTH_SCALE` to adjust speaking speed. Voice model downloads are
manual; nothing is fetched automatically. Browser microphone access requires
a secure context (localhost is allowed by browsers). Configure a TURN server
for networks where direct ICE/STUN connectivity is insufficient; TURN
credentials are returned only to an authenticated calling dashboard.

These are optional audio dependencies. The automated test suite does not
download speech models or claim live audio quality. If the optional packages,
local model files, or Piper binary are missing, JARVIS still starts and reports
voice features unavailable.

## AI provider configuration

Calling uses the provider selected by `JARVIS_AI_PROVIDER`; chat uses Ollama
when selected and otherwise retains the OpenAI Responses API:

| Provider | Required settings | Data handling |
| --- | --- | --- |
| `ollama` (default) | Running Ollama and a matching `JARVIS_OLLAMA_MODEL` | On-device when Ollama runs locally |
| `gemini` | `JARVIS_GEMINI_API_KEY`, optional `JARVIS_GEMINI_MODEL` | Transcript text is sent to Google |
| `groq` | `JARVIS_GROQ_API_KEY`, optional `JARVIS_GROQ_MODEL` | Transcript text is sent to Groq |

Chat supports Ollama and the existing OpenAI Responses API path. To use OpenAI
for chat instead, set `JARVIS_AI_PROVIDER=openai` and configure `OPENAI_API_KEY`.
Gemini and Groq remain supported by scheduled calling; chat does not silently
fall back to a cloud provider when local Ollama is unavailable.

Speech recognition runs locally. Audio is processed in memory and is not
recorded. The transcribed text is sent to the selected AI provider to generate
responses; transcript retention in SQLite is off by default and can be enabled
in the dashboard. Stored transcripts redact common credential formats.

## Optional telephone calling

The provider defaults to `none`, and `JARVIS_TEST_MODE=true` blocks outbound
calls even when credentials exist. Live Twilio calls require all of the
following:

1. A Twilio account with billing enabled and a configured caller ID.
2. `JARVIS_TELEPHONE_PROVIDER=twilio`, account SID, auth token, from/to numbers,
   and a public HTTPS base URL in `backend/.env`.
3. HTTPS status callbacks and a reachable WSS media-stream endpoint.
4. The local Whisper/Piper voice stack and a working AI provider.
5. `JARVIS_TEST_MODE=false`, then explicit billing consent and telephone
   fallback enablement in the dashboard.

Telephone calls can incur charges. Never disable test mode or enable fallback
unless the account, destination number, and billing implications are understood.
Credentials stay in the backend environment and are never returned to React.
`test_mode` is intentionally enabled by default; no real phone call is made by
the automated tests.

## Production and availability

- Terminate TLS at a trusted reverse proxy and set `JARVIS_REQUIRE_HTTPS=true`.
  Ensure Uvicorn trusts only that proxy's forwarded headers so HTTPS/WSS is
  recognized correctly.
- Use a single Uvicorn worker for the in-process scheduler and call signaling.
  The SQLite database is appropriate for a single-host deployment; configure a
  PostgreSQL SQLAlchemy URL and install a PostgreSQL driver for a larger
  deployment.
- Set `JARVIS_CORS_ORIGINS` to the exact dashboard origin(s). Do not expose the
  development Vite server publicly.
- Keep the backend on an always-on host for reliable scheduling. When it starts
  after a scheduled time, it records the missed occurrence instead of silently
  placing a late call. Calls interrupted by a backend restart are marked failed.
- Chat requests interrupted by a restart or graceful shutdown are marked
  interrupted in the conversation history. JARVIS does not automatically repeat
  them; the user can request one bounded retry. Chat generation times out after
  90 seconds. Chat currently has no tools for sending messages, emails, or
  initiating calls.
- Do not put AI or telephony credentials in frontend files, browser storage, or
  source control. Protect the SQLite database and `.env` file.

There is no Android companion or push notification service yet. Do not rely on
a browser tab for background delivery while the device is asleep or the app is
closed.

## API

- `GET /api/health` — process and scheduler status.
- `GET /api/ai/status` and `PUT /api/ai/model` — local Ollama status and
  selection from installed models.
- `GET|POST /api/memory`, `DELETE /api/memory/{id}` — explicitly approved
  preferences stored locally and included as conversation context.
- `GET /api/voice/status`, `POST /api/voice/transcribe`,
  `WS /api/voice/wake-word`, and `POST /api/voice/speak` — optional local voice
  capabilities. Background listening requires explicit opt-in and a configured
  local wake-word detector and speech recognizer.
- `GET /api/actions`, `POST /api/actions/drafts`, and
  `POST /api/actions/{id}/approve` — local email/message drafts and audit trail.
  Approval does not send anything; Gmail/SMS/WhatsApp adapters are unavailable.
- `POST /api/chat` and `POST /api/chat/stream` — local Ollama by default, or
  OpenAI Responses API when selected.
- `GET /api/conversations/{id}` also returns the conversation's latest chat task
  statuses for interruption recovery. Chat requests may provide a UUID
  `task_id` to make retries idempotent.
- `GET /api/calling/status` — available capabilities (no credentials).
- `GET/PUT /api/calling/schedules` — authenticated daily schedule controls.
- `GET/PUT /api/calling/preferences` — authenticated calling permissions.
- `GET /api/calling/sessions` — authenticated call history and attempts.
- `GET /api/calling/webrtc-config` — authenticated ICE/TURN configuration.
- `WS /api/calling/ws` — authenticated call controls and WebRTC signaling.
- `/api/calling/webhooks/twilio/*` — signed provider callbacks.

Calling HTTP requests use `X-Calling-Token`; the WebSocket negotiates
`jarvis.v1` and `jarvis-token.<configured-token>` subprotocols. Keep the token
private and use HTTPS/WSS off localhost.

## Development and tests

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

The tests use temporary SQLite databases, mock the OpenAI/Ollama network
boundaries, verify scheduling/timezones/authentication, and enforce test-mode
telephone safeguards. They do not prove live provider connectivity, model
quality, real browser microphone negotiation, or Twilio billing behavior.

## Project layout

```text
backend/app/             FastAPI, calling, providers, audio, security, database
backend/migrations/      Alembic schema revisions
backend/tests/           Backend API, scheduler, and calling tests
frontend/src/             React assistant and calling dashboard
scripts/                  Local install and combined startup scripts
data/                     Runtime SQLite database (ignored by Git)
```
