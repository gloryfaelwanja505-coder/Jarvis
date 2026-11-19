# JARVIS interface redesign checkpoint

## Phase 1 audit

The app is a Vite/React single page application backed by FastAPI and SQLite. The current UI already has a persistent streaming chat, conversation list/load/restore and interruption recovery, explicit push-to-talk transcription, optional speech synthesis, runtime health and AI status, Ollama model selection, explicitly approved memory/preferences, personality settings, local communication drafts, and a separate token-protected calling dashboard.

### Existing API map

| Area | Existing routes | Frontend state |
| --- | --- | --- |
| Health | `GET /api/health` | Live backend and AI capability |
| Chat/history | `POST /api/chat/stream`, `GET /api/conversations`, `GET /api/conversations/{id}` | Working and persistent |
| Models/personality | `GET /api/ai/status`, `PUT /api/ai/model`, `PUT /api/ai/personality` | Working, Ollama model list only |
| Memory | `GET/POST /api/memory`, `DELETE /api/memory/{id}` | Explicitly approved preferences |
| Voice | `GET /api/voice/status`, `POST /api/voice/transcribe`, `POST /api/voice/speak` | Optional local dependencies; push-to-talk only |
| Action drafts | `GET /api/actions`, `POST /api/actions/drafts`, `POST /api/actions/{id}/approve` | Local drafts; approve does not send |
| Calling | Authenticated `/api/calling/*`, WebSocket signaling | Separate calling dashboard; gated by token and provider configuration |

There are no APIs for Gmail delivery, SMS/WhatsApp delivery, contacts, file browsing/upload, research storage, general automation CRUD, integrations/permissions, notifications, or live CPU/RAM/disk/service metrics. The current calling scheduler is the only scheduled activity. These should be presented as unavailable or under development until real services exist.

## Implementation phases

- [x] Phase 1: inspect frontend, backend route registrations, service calls, and capabilities.
- [x] Phase 2: establish green design tokens, expandable navigation, responsive drawer, and tablet/mobile layouts.
- [x] Phase 3: navigation, home/chat, conversation-history entry, memory, model and voice workspaces.
- [x] Phase 4: preserve the authenticated calling dashboard and surface existing communication drafts without implying delivery.
- [x] Phase 5: model and memory workspaces use the existing live endpoints.
- [x] Phase 6: live service-health view and dedicated settings page use existing status and personality APIs.
- [x] Phase 7: frontend functionality/build checks passed; live service/device verification remains unavailable here.

## Current checkpoint

The existing APIs and storage are being preserved. Destinations without a supporting API show an explicit unavailable state. The production frontend build passed and the frontend suite passed (10 tests). The backend test command could not be verified in this environment: it returned no output, and its process disappeared before a result was available. No live backend, optional audio models, telephony provider, or browser device integrations were available for end-to-end verification here. Remaining product gaps include rich Markdown/code rendering and genuine Gmail, messaging, contacts, files, research, generalized automations, permission management, and host metrics; the current backend has no APIs for these capabilities.
