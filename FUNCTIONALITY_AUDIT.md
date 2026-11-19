# JARVIS functionality audit

This checklist reflects the implementation present in this workspace; there is
no Git metadata here to compare with the interrupted agent's branch or recover
its diff.

## Assistant

- [x] New conversation, recent-history navigation, persisted history, and
  streamed chat are connected to the FastAPI API. Chat uses the configured
  local Ollama model by default; OpenAI remains an explicit alternative.
- [x] Ollama model reachability is checked by the health endpoint, the UI
  distinguishes an unavailable local model, and chat does not silently fall
  back to a cloud provider.
- [x] The model selector lists installed local models and persists explicit
  model changes through the backend.
- [x] Personality settings and approved user preferences are persisted in
  SQLite and included in assistant context.
- [x] Stop response marks the task interrupted; saved requests can be retried
  explicitly, with a bounded retry count and no automatic replay.
- [x] Settings report the configured provider/model and explain local history
  and data handling. They do not claim to change backend-only configuration.
- [x] Help opens a concise guide. Composer options explain that attachments are
  not implemented rather than silently doing nothing.
- [x] Assistant state reflects backend availability, generation, streaming,
  failure, and recovery; it does not display a simulated “live” state.
- [x] Push-to-talk captures one browser utterance only after explicit user
  action; local Vosk transcription and Piper playback are optional, configured
  capabilities. Wake-word/background listening is not active.
- [x] Email and message drafts can be saved and approved locally. Approval
  changes the draft state and records an audit event; it does not send anything.
- [x] Computer control is not enabled.
- [x] Health, conversation-history, chat, timeout, and stream errors have
  visible feedback.

## Scheduled calling

- [x] Access token unlock/sign-out, schedules, timezone, retry count and delay,
  DND, transcript retention, telephone consent, call history, and refresh use the
  authenticated calling API.
- [x] WebSocket signaling, microphone/speaker controls, answer/decline/end,
  connection status, and reconnect behavior reflect actual browser/backend
  events. Live media/telephone availability comes from backend capability
  checks; unavailable dependencies are not simulated.
- [x] The API enforces bounded retries, duplicate daily-occurrence protection,
  active-call exclusion, billing consent, and no retry after an uncertain
  telephone result. Duplicate answer/decline/end controls are idempotent.
- [x] Call dashboard request and signaling errors are surfaced to the user.

## Voice and communication boundaries

- [x] Voice status reports whether local recognition/synthesis dependencies and
  models are configured. Missing voice dependencies do not prevent startup.
- [x] Microphone permission is requested by an explicit push-to-talk action;
  no hidden or continuous recording is enabled.
- [x] Draft creation and approval have persisted API/UI paths and user-visible
  status. No Gmail OAuth, SMS, WhatsApp, or Android telephony delivery adapter
  is configured, so actual communication is unavailable.
- [ ] Wake-word background listening, Gmail authorization/delivery, supported
  messaging delivery, and an Android cellular bridge remain unimplemented.

## Runtime recovery

- [x] Conversations and messages persist in SQLite.
- [x] Chat task status, request identity, attempt count, and ordered checkpoints
  persist in SQLite. An identical completed request returns its saved response;
  concurrent or mismatched duplicate IDs are rejected.
- [x] Startup and graceful shutdown mark unfinished chat tasks interrupted.
  Recovery is visible in the conversation, and retry requires a user action.
- [x] Startup marks unfinished call attempts failed with a restart outcome;
  calls are not automatically repeated.
- [x] Chat generation has a 90-second server timeout and permits at most one
  explicit retry. Existing scheduled-call occurrence keys and interrupted-call
  recovery remain in place.
- [x] Local Ollama requests use the configured model and the same JARVIS
  instructions, stream deltas through the existing chat UI, and persist the
  resulting response/task state.

## Visual and responsive review

- [x] Replaced remote font loading and the blue/cyan base palette with dark
  charcoal, botanical green, muted surfaces, and restrained warm lighting.
- [x] Reduced decorative orbit/glow animation; retained reduced-motion support.
- [x] Desktop two-column layout, tablet collapse, and mobile navigation/composer
  layouts have responsive CSS rules.
- [x] Browser checks at 320, 390, 768, 1024, and 1440 CSS pixels found no
  horizontal overflow. The mobile history drawer, Help, and unavailable-
  attachment notice were exercised. The calling page was checked at the same
  widths; its 320px layout was adjusted to avoid overflow.
- [x] Local Ollama generation was verified end-to-end through JARVIS with no
  OpenAI key configured. External cloud AI, WebRTC media, and telephone
  providers were not exercised.

## Final verification

- [x] Backend tests: 62 passed (one upstream Starlette/httpx deprecation
  warning).
- [x] Frontend tests: 10 passed.
- [x] Frontend production build completed successfully.
- [x] Browser interaction and responsive checks completed at 320, 390, 768,
  1024, and 1440 CSS pixels.
- [ ] External cloud AI, WebRTC media, and telephone-provider behavior remain
  unverified.

## Outstanding dependencies / limitations

- Vosk, Piper, and wake-word model files are optional and were not installed or
  exercised in this environment. Wake-word listening is not running. File
  attachments, computer control, Android push notifications, and live provider
  media are not implemented or are dependency-gated.
- A retry starts a new model generation for a saved chat prompt; it does not
  replay external actions. JARVIS currently has no chat tools for sending email,
  messaging, or placing phone calls. Scheduled calls remain a separate,
  explicitly configured feature.
- Approved communication drafts are persisted but are not delivered. Gmail,
  SMS/WhatsApp, and Android phone-bridge integrations are not configured.
- A browser tab must remain open to receive browser-mediated calls.
