import asyncio
import base64
from collections import deque
import hashlib
import hmac
import importlib.util
import json
import logging
import shutil
from urllib.parse import urlsplit, urlunsplit
from xml.sax.saxutils import escape

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, sessionmaker

from app.calling.audio.speech_input import WhisperSpeechInput
from app.calling.audio.speech_output import PiperSpeechOutput
from app.calling.audio.voice_activity import VoiceActivityDetector
from app.calling.call_memory import append_transcript
from app.calling.conversation_engine import ConversationEngine
from app.config import Settings
from app.models import CallSession

logger = logging.getLogger(__name__)


class TelephoneUnavailable(RuntimeError):
    pass


class TelephoneCallUncertain(TelephoneUnavailable):
    pass


class TwilioTelephoneProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        if self.settings.telephone_provider != "twilio" or not self.settings.telephone_credentials_configured:
            return False
        parsed = urlsplit(self.settings.twilio_public_base_url or "")
        return parsed.scheme == "https" and bool(parsed.netloc)

    @property
    def voice_stream_available(self) -> bool:
        return (
            importlib.util.find_spec("faster_whisper") is not None
            and importlib.util.find_spec("numpy") is not None
            and shutil.which(self.settings.piper_binary) is not None
            and self.settings.piper_model_path is not None
            and self.settings.piper_model_path.is_file()
        )

    async def place_call(self, session: CallSession) -> str:
        if self.settings.test_mode:
            raise TelephoneUnavailable("Test mode prevents live telephone calls.")
        if not self.configured or not self.voice_stream_available:
            raise TelephoneUnavailable(
                "Twilio and local voice services must be fully configured before dialing."
            )
        account_sid = self.settings.twilio_account_sid.get_secret_value()
        base_url = self.settings.twilio_public_base_url.rstrip("/")
        public_host = urlsplit(base_url).netloc
        status_url = f"{base_url}/api/calling/webhooks/twilio/status?call_id={session.id}"
        stream_url = f"wss://{public_host}/api/calling/webhooks/twilio/media?call_id={session.id}"
        twiml = f'<Response><Connect><Stream url="{escape(stream_url)}" /></Connect></Response>'
        payload = [
            ("To", self.settings.twilio_to_number.get_secret_value()),
            ("From", self.settings.twilio_from_number.get_secret_value()),
            ("Twiml", twiml),
            ("StatusCallback", status_url),
            ("StatusCallbackEvent", "initiated"),
            ("StatusCallbackEvent", "ringing"),
            ("StatusCallbackEvent", "answered"),
            ("StatusCallbackEvent", "completed"),
            ("StatusCallbackMethod", "POST"),
        ]
        try:
            async with httpx.AsyncClient(
                auth=(account_sid, self.settings.twilio_auth_token.get_secret_value()),
                timeout=20.0,
            ) as client:
                response = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json",
                    data=payload,
                )
                response.raise_for_status()
                try:
                    body = response.json()
                except ValueError as exc:
                    raise TelephoneCallUncertain(
                        "Twilio accepted the request but returned an unreadable call result."
                    ) from exc
                if not isinstance(body, dict):
                    raise TelephoneCallUncertain(
                        "Twilio accepted the request but returned an invalid call result."
                    )
                call_sid = str(body.get("sid", ""))
                if not call_sid:
                    raise TelephoneCallUncertain(
                        "Twilio accepted the request without returning a call identifier."
                    )
                return call_sid
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise TelephoneCallUncertain(
                    "Twilio returned a server error; the call state is unknown."
                ) from exc
            raise TelephoneUnavailable(
                "Twilio rejected the telephone call request."
            ) from exc
        except httpx.TimeoutException as exc:
            raise TelephoneCallUncertain(
                "Twilio did not confirm the call result before timing out."
            ) from exc
        except httpx.HTTPError as exc:
            raise TelephoneCallUncertain(
                "The Twilio request failed after submission; the call state is unknown."
            ) from exc

    async def stream_conversation(
        self,
        websocket: WebSocket,
        call_id: str,
        session_factory: sessionmaker[Session],
    ) -> None:
        if not self.voice_stream_available:
            await websocket.close(code=1013, reason="Local speech services are unavailable.")
            return
        await websocket.accept()
        speech_input = WhisperSpeechInput(self.settings)
        speech_output = PiperSpeechOutput(self.settings)
        ai_engine = ConversationEngine(self.settings)
        detector = VoiceActivityDetector(sample_rate=8_000, threshold=0.018)
        history: deque[tuple[str, str]] = deque(maxlen=20)
        stream_id: str | None = None
        response_task: asyncio.Task[None] | None = None
        try:
            while True:
                message = json.loads(await websocket.receive_text())
                if not isinstance(message, dict):
                    raise ValueError("Invalid media stream message.")
                event_type = message.get("event")
                if event_type == "start":
                    start = message.get("start", {})
                    stream_id = str(start.get("streamSid", ""))
                    if start.get("callSid") != self._external_call_id(session_factory, call_id):
                        await websocket.close(code=4403, reason="Telephony session mismatch.")
                        return
                    continue
                if event_type == "stop":
                    return
                if event_type != "media" or stream_id is None:
                    continue
                media = message.get("media", {})
                encoded = media.get("payload") if isinstance(media, dict) else None
                if not isinstance(encoded, str) or len(encoded) > 24_000:
                    continue
                pcm_8k = decode_mulaw(base64.b64decode(encoded, validate=True))
                phrase = detector.process(pcm_8k)
                if phrase is None:
                    continue
                if response_task is not None and not response_task.done():
                    response_task.cancel()
                    await asyncio.gather(response_task, return_exceptions=True)
                    await websocket.send_json({"event": "clear", "streamSid": stream_id})
                response_task = asyncio.create_task(
                    self._respond_to_utterance(
                        websocket,
                        stream_id,
                        call_id,
                        phrase,
                        history,
                        speech_input,
                        speech_output,
                        ai_engine,
                        session_factory,
                    )
                )
        except WebSocketDisconnect:
            logger.info("Twilio media stream disconnected for call %s", call_id)
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("Twilio sent malformed audio data for call %s", call_id)
        finally:
            if response_task is not None and not response_task.done():
                response_task.cancel()
                await asyncio.gather(response_task, return_exceptions=True)
            await ai_engine.close()

    @staticmethod
    def _external_call_id(session_factory: sessionmaker[Session], call_id: str) -> str | None:
        with session_factory() as db:
            session = db.get(CallSession, call_id)
            return session.external_call_id if session is not None else None

    async def _respond_to_utterance(
        self,
        websocket: WebSocket,
        stream_id: str,
        call_id: str,
        phrase: bytes,
        history: deque[tuple[str, str]],
        speech_input: WhisperSpeechInput,
        speech_output: PiperSpeechOutput,
        ai_engine: ConversationEngine,
        session_factory: sessionmaker[Session],
    ) -> None:
        try:
            import numpy as np

            phrase_16k = np.repeat(np.frombuffer(phrase, dtype=np.int16), 2).astype(np.int16).tobytes()
            text = await asyncio.to_thread(speech_input.transcribe, phrase_16k)
            if not text:
                return
            history.append(("user", text))
            context = "morning"
            with session_factory() as db:
                session = db.get(CallSession, call_id)
                if session is None:
                    return
                append_transcript(db, session, "owner", text)
                context = session.schedule.prompt_context if session.schedule else "morning"
            reply = await ai_engine.reply(context, history)
            history.append(("assistant", reply))
            with session_factory() as db:
                session = db.get(CallSession, call_id)
                if session is None:
                    return
                append_transcript(db, session, "assistant", reply)
            pcm, sample_rate = await speech_output.synthesize(reply)
            pcm_8k = resample_pcm(pcm, sample_rate, 8_000)
            for offset in range(0, len(pcm_8k), 320):
                samples = pcm_8k[offset : offset + 320]
                if len(samples) < 320:
                    samples = samples + bytes(320 - len(samples))
                await websocket.send_json(
                    {
                        "event": "media",
                        "streamSid": stream_id,
                        "media": {"payload": base64.b64encode(encode_mulaw(samples)).decode("ascii")},
                    }
                )
                await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Could not process Twilio voice turn for call %s", call_id)

    def verify_webhook(self, public_url: str, form_values: dict[str, str], signature: str | None) -> bool:
        if not self.configured or not signature:
            return False
        configured_url = urlsplit(self.settings.twilio_public_base_url or "")
        requested = urlsplit(public_url)
        url = urlunsplit(
            (configured_url.scheme, configured_url.netloc, requested.path, requested.query, "")
        )
        canonical = url + "".join(key + form_values[key] for key in sorted(form_values))
        expected = base64.b64encode(
            hmac.new(
                self.settings.twilio_auth_token.get_secret_value().encode(),
                canonical.encode(),
                hashlib.sha1,
            ).digest()
        ).decode()
        return hmac.compare_digest(expected, signature)


def twilio_status_is_final(status: str) -> bool:
    return status in {"completed", "busy", "no-answer", "canceled", "failed"}


def decode_mulaw(encoded: bytes) -> bytes:
    decoded = bytearray()
    for item in encoded:
        value = (~item) & 0xFF
        magnitude = ((value & 0x0F) << 3) + 0x84
        magnitude <<= (value & 0x70) >> 4
        sample = magnitude - 0x84
        if value & 0x80:
            sample = -sample
        decoded.extend(int(sample).to_bytes(2, "little", signed=True))
    return bytes(decoded)


def encode_mulaw(pcm_s16le: bytes) -> bytes:
    if len(pcm_s16le) % 2:
        raise ValueError("PCM must contain complete 16-bit samples.")
    encoded = bytearray()
    for offset in range(0, len(pcm_s16le), 2):
        sample = int.from_bytes(pcm_s16le[offset : offset + 2], "little", signed=True)
        sign = 0x80 if sample < 0 else 0
        magnitude = min(abs(sample), 32635) + 0x84
        exponent = max(0, min(7, magnitude.bit_length() - 8))
        mantissa = (magnitude >> (exponent + 3)) & 0x0F
        encoded.append((~(sign | (exponent << 4) | mantissa)) & 0xFF)
    return bytes(encoded)


def resample_pcm(pcm_s16le: bytes, input_rate: int, output_rate: int) -> bytes:
    if input_rate <= 0 or output_rate <= 0 or len(pcm_s16le) % 2:
        raise ValueError("Invalid PCM sample rate or data.")
    import numpy as np

    samples = np.frombuffer(pcm_s16le, dtype=np.int16)
    if not samples.size:
        return b""
    output_length = max(1, round(samples.size * output_rate / input_rate))
    positions = np.linspace(0, samples.size - 1, output_length)
    resampled = np.interp(positions, np.arange(samples.size), samples)
    return np.clip(resampled, -32768, 32767).astype(np.int16).tobytes()
