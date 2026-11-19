import asyncio
from collections import deque
from fractions import Fraction
import importlib.util
import logging
import shutil
from typing import Any

from app.calling.audio.speech_input import WhisperSpeechInput
from app.calling.audio.speech_output import PiperSpeechOutput
from app.calling.audio.voice_activity import VoiceActivityDetector
from app.calling.call_memory import append_transcript
from app.calling.conversation_engine import ConversationEngine
from app.config import Settings

logger = logging.getLogger(__name__)


class WebRTCUnavailable(RuntimeError):
    pass


def webrtc_dependencies_installed() -> bool:
    return all(importlib.util.find_spec(module) is not None for module in ("aiortc", "av", "numpy"))


class WebRTCVoiceProvider:
    def __init__(self, settings: Settings, session_factory: Any) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self._peers: dict[str, Any] = {}
        self._tracks: dict[str, Any] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self.on_connected: Any | None = None
        self.on_disconnected: Any | None = None

    @property
    def media_available(self) -> bool:
        return (
            webrtc_dependencies_installed()
            and importlib.util.find_spec("faster_whisper") is not None
            and self.settings.piper_model_path is not None
            and self.settings.piper_model_path.is_file()
            and shutil.which(self.settings.piper_binary) is not None
        )

    async def accept_offer(self, call_id: str, sdp: str, context: str) -> str:
        if not self.media_available:
            raise WebRTCUnavailable(
                "Install aiortc, faster-whisper, and a Piper voice model to enable audio calls."
            )
        try:
            from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
        except ImportError as exc:
            raise WebRTCUnavailable("The aiortc WebRTC media engine is not installed.") from exc

        servers = [RTCIceServer(urls=server) for server in self.settings.stun_servers]
        if self.settings.turn_server and self.settings.turn_username and self.settings.turn_credential:
            servers.append(
                RTCIceServer(
                    urls=self.settings.turn_server,
                    username=self.settings.turn_username.get_secret_value(),
                    credential=self.settings.turn_credential.get_secret_value(),
                )
            )
        peer = RTCPeerConnection(RTCConfiguration(iceServers=servers))
        audio_track = _create_assistant_audio_track()
        peer.addTrack(audio_track)
        self._peers[call_id] = peer
        self._tracks[call_id] = audio_track

        @peer.on("track")
        def on_track(track: Any) -> None:
            if track.kind == "audio":
                task = asyncio.create_task(self._consume_audio(call_id, track, context, audio_track))
                self._tasks[call_id] = task

        @peer.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            if peer.connectionState == "connected" and self.on_connected is not None:
                await self.on_connected(call_id)
            elif peer.connectionState == "disconnected":
                await asyncio.sleep(8)
                if peer.connectionState != "disconnected":
                    return
                if self.on_disconnected is not None:
                    await self.on_disconnected(call_id)
                await self.close(call_id)
            elif peer.connectionState == "failed":
                if self.on_disconnected is not None:
                    await self.on_disconnected(call_id)
                await self.close(call_id)

        await peer.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        answer = await peer.createAnswer()
        await peer.setLocalDescription(answer)
        if peer.localDescription is None:
            await self.close(call_id)
            raise WebRTCUnavailable("WebRTC did not produce an SDP answer.")
        return peer.localDescription.sdp

    async def add_ice_candidate(self, call_id: str, candidate_data: dict[str, object]) -> None:
        peer = self._peers.get(call_id)
        if peer is None:
            raise WebRTCUnavailable("There is no active WebRTC session for this call.")
        candidate_value = candidate_data.get("candidate")
        if not isinstance(candidate_value, str) or not candidate_value.startswith("candidate:"):
            raise ValueError("Invalid ICE candidate.")
        try:
            from aiortc.sdp import candidate_from_sdp
        except ImportError as exc:
            raise WebRTCUnavailable("The aiortc WebRTC media engine is not installed.") from exc
        candidate = candidate_from_sdp(candidate_value.removeprefix("candidate:"))
        candidate.sdpMid = str(candidate_data.get("sdpMid") or "")
        line_index = candidate_data.get("sdpMLineIndex")
        candidate.sdpMLineIndex = int(line_index) if isinstance(line_index, int) else 0
        await peer.addIceCandidate(candidate)

    async def close(self, call_id: str) -> None:
        task = self._tasks.pop(call_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._tracks.pop(call_id, None)
        peer = self._peers.pop(call_id, None)
        if peer is not None and peer.connectionState != "closed":
            await peer.close()

    async def close_all(self) -> None:
        await asyncio.gather(*(self.close(call_id) for call_id in list(self._peers)))

    async def _consume_audio(self, call_id: str, track: Any, context: str, output_track: Any) -> None:
        try:
            import av
            import numpy as np
            from av.audio.resampler import AudioResampler
            from app.calling.conversation_engine import ConversationEngine

            resampler = AudioResampler(format="s16", layout="mono", rate=16_000)
            detector = VoiceActivityDetector()
            speech_input = WhisperSpeechInput(self.settings)
            speech_output = PiperSpeechOutput(self.settings)
            engine = ConversationEngine(self.settings)
            history: deque[tuple[str, str]] = deque(maxlen=20)
            response_task: asyncio.Task[None] | None = None
            try:
                while True:
                    frame = await track.recv()
                    if response_task is not None and response_task.done():
                        response_task.result()
                        response_task = None
                    for audio_frame in resampler.resample(frame):
                        pcm = audio_frame.to_ndarray().reshape(-1).astype(np.int16).tobytes()
                        phrase = detector.process(pcm)
                        if phrase is None:
                            continue
                        output_track.interrupt()
                        if response_task is not None and not response_task.done():
                            response_task.cancel()
                            await asyncio.gather(response_task, return_exceptions=True)
                        response_task = asyncio.create_task(
                            self._respond_to_utterance(
                                call_id,
                                context,
                                phrase,
                                history,
                                speech_input,
                                speech_output,
                                engine,
                                output_track,
                            )
                        )
            finally:
                if response_task is not None and not response_task.done():
                    response_task.cancel()
                    await asyncio.gather(response_task, return_exceptions=True)
                await engine.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Voice processing failed for call %s", call_id)
            if self.on_disconnected is not None:
                await self.on_disconnected(call_id)
            await self.close(call_id)

    async def _respond_to_utterance(
        self,
        call_id: str,
        context: str,
        phrase: bytes,
        history: deque[tuple[str, str]],
        speech_input: WhisperSpeechInput,
        speech_output: PiperSpeechOutput,
        engine: ConversationEngine,
        output_track: Any,
    ) -> None:
        text = await asyncio.to_thread(speech_input.transcribe, phrase)
        if not text:
            return
        history.append(("user", text))
        with self.session_factory() as db:
            from app.models import CallSession

            session = db.get(CallSession, call_id)
            if session is None:
                return
            append_transcript(db, session, "owner", text)
        reply = await engine.reply(context, history)
        history.append(("assistant", reply))
        with self.session_factory() as db:
            from app.models import CallSession

            session = db.get(CallSession, call_id)
            if session is None:
                return
            append_transcript(db, session, "assistant", reply)
        pcm_out, sample_rate = await speech_output.synthesize(reply)
        output_track.enqueue_wav(pcm_out, sample_rate)


def _create_assistant_audio_track() -> Any:
    from aiortc import MediaStreamTrack
    from av import AudioFrame
    import numpy as np

    class AssistantAudioTrack(MediaStreamTrack):
        kind = "audio"

        def __init__(self) -> None:
            super().__init__()
            self._frames: asyncio.Queue[bytes] = asyncio.Queue()
            self._pending = bytearray()
            self._pts = 0

        def interrupt(self) -> None:
            while not self._frames.empty():
                try:
                    self._frames.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._pending.clear()

        def enqueue_wav(self, pcm_s16le: bytes, sample_rate: int) -> None:
            import numpy as np
            import av
            from av.audio.resampler import AudioResampler

            samples = np.frombuffer(pcm_s16le, dtype=np.int16)
            source = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
            source.sample_rate = sample_rate
            resampler = AudioResampler(format="s16", layout="mono", rate=48_000)
            for frame in resampler.resample(source):
                self._pending.extend(frame.to_ndarray().reshape(-1).astype(np.int16).tobytes())
            frame_bytes = 960 * 2
            while len(self._pending) >= frame_bytes:
                self._frames.put_nowait(bytes(self._pending[:frame_bytes]))
                del self._pending[:frame_bytes]

        async def recv(self) -> Any:
            try:
                pcm = await asyncio.wait_for(self._frames.get(), timeout=0.02)
            except TimeoutError:
                pcm = bytes(960 * 2)
            frame = AudioFrame.from_ndarray(
                np.frombuffer(pcm, dtype=np.int16).reshape(1, -1),
                format="s16",
                layout="mono",
            )
            frame.sample_rate = 48_000
            frame.pts = self._pts
            frame.time_base = Fraction(1, 48_000)
            self._pts += frame.samples
            return frame

    return AssistantAudioTrack()
