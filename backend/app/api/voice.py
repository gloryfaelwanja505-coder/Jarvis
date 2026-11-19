import io
import wave
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.calling.audio.speech_input import SpeechInputUnavailable
from app.calling.audio.speech_output import SpeechOutputUnavailable

router = APIRouter()


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.get("/voice/status")
def voice_status(request: Request) -> dict[str, object]:
    return {
        **request.app.state.audio_manager.status(),
        "text_to_speech_available": request.app.state.text_to_speech.available,
    }


@router.post("/voice/transcribe")
async def transcribe_voice(
    request: Request,
    sample_rate: Annotated[int, Query(ge=8_000, le=48_000)] = 16_000,
) -> dict[str, str]:
    if not request.app.state.audio_manager.recognition.available:
        raise HTTPException(
            status_code=503,
            detail="Offline speech recognition is not configured. Install the optional voice dependencies and set a local model path.",
        )
    if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
        raise HTTPException(status_code=415, detail="Send raw 16-bit PCM audio.")
    chunks: list[bytes] = []
    length = 0
    async for chunk in request.stream():
        length += len(chunk)
        if length > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Audio must be between 1 byte and 10 MB.")
        chunks.append(chunk)
    audio = b"".join(chunks)
    if not audio:
        raise HTTPException(status_code=413, detail="Audio must be between 1 byte and 10 MB.")
    try:
        text = request.app.state.voice_pipeline.transcribe(audio, sample_rate)
    except (SpeechInputUnavailable, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"text": text}


@router.websocket("/voice/wake-word")
async def listen_for_wake_word(websocket: WebSocket) -> None:
    detector = websocket.app.state.audio_manager.wake_word
    if not detector.available:
        await websocket.close(code=1013, reason="Local wake-word model is not configured.")
        return

    await websocket.accept()
    audio_manager = websocket.app.state.audio_manager
    audio_manager.wake_word_listening = True
    try:
        try:
            while True:
                pcm = await websocket.receive_bytes()
                if not pcm or len(pcm) > 64 * 1024 or len(pcm) % 2:
                    await websocket.close(code=1003, reason="Expected a short 16-bit PCM audio frame.")
                    return
                detected = await run_in_threadpool(detector.detect, pcm)
                await websocket.send_json({"detected": detected})
        except WebSocketDisconnect:
            return
    finally:
        audio_manager.wake_word_listening = False


@router.post("/voice/speak")
async def speak(request: Request, payload: SpeechRequest) -> Response:
    if not request.app.state.text_to_speech.available:
        raise HTTPException(status_code=503, detail="Configure a local Piper model to enable speech.")
    try:
        async def synthesize() -> tuple[bytes, int]:
            return await request.app.state.text_to_speech.synthesize(payload.text)

        pcm, sample_rate = await request.app.state.audio_manager.speak(synthesize)
    except SpeechOutputUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm)
    return Response(content=buffer.getvalue(), media_type="audio/wav")
