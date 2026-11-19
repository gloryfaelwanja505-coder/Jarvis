from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.ai_manager import AIManager
from app.ai.context_manager import ContextManager
from app.api.assistant import router as assistant_router
from app.api.calling import router as calling_router
from app.api.calling_webhooks import router as calling_webhooks_router
from app.api.system import router as system_router
from app.api.voice import router as voice_router
from app.api.routes.chat import recover_interrupted_tasks, router as chat_router
from app.calling.call_manager import CallManager
from app.calling.call_routing import CallRouter
from app.calling.call_sessions import CallConnectionHub
from app.calling.conversation_engine import ConversationEngine
from app.calling.providers.telephone import TwilioTelephoneProvider
from app.calling.providers.webrtc import WebRTCVoiceProvider
from app.calling.scheduler import CallScheduler, ensure_calling_defaults
from app.config import Settings, get_settings
from app.database.base import Base
from app.database.migrations import upgrade_calling_schema
from app.database.session import create_database_engine, create_session_factory
from app.models import AssistantProfile
from app.models.conversation import Conversation, Message
from app.services.ai import ai_is_configured, chat_provider, configured_model
from app.voice.audio_manager import AudioManager
from app.voice.text_to_speech import TextToSpeech
from app.voice.voice_pipeline import VoicePipeline

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    engine = create_database_engine(app_settings.resolved_database_url())
    session_factory = create_session_factory(engine)
    hub = CallConnectionHub()
    webrtc = WebRTCVoiceProvider(app_settings, session_factory)
    telephone = TwilioTelephoneProvider(app_settings)
    ai_manager = AIManager(app_settings)
    ai_context = ContextManager()
    audio_manager = AudioManager(app_settings)
    voice_pipeline = VoicePipeline(audio_manager)
    text_to_speech = TextToSpeech(app_settings)
    conversation_engine = ConversationEngine(app_settings)
    call_router = CallRouter(app_settings, session_factory, hub, webrtc, telephone, conversation_engine)
    call_manager = CallManager(app_settings, session_factory, hub, call_router)
    webrtc.on_connected = call_manager.mark_connected
    webrtc.on_disconnected = call_manager.mark_disconnected
    scheduler = CallScheduler(session_factory, call_manager)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database_ready = False
        try:
            Base.metadata.create_all(
                bind=engine,
                tables=[Conversation.__table__, Message.__table__],
            )
            upgrade_calling_schema(app_settings.resolved_database_url())
            database_ready = True
            with session_factory.begin() as db:
                profile = db.get(AssistantProfile, 1)
                if profile is None:
                    db.add(
                        AssistantProfile(
                            id=1,
                            selected_model=app_settings.ollama_model,
                            personality=ai_manager.personality,
                        )
                    )
                else:
                    app_settings.ollama_model = profile.selected_model
                    ai_manager.personality = profile.personality
            ensure_calling_defaults(session_factory, app_settings.default_timezone)
            recover_interrupted_tasks(session_factory)
            await scheduler.start()
            yield
        finally:
            await scheduler.shutdown()
            if database_ready:
                recover_interrupted_tasks(
                    session_factory,
                    "JARVIS shut down before this response was saved. No action was replayed.",
                )
            await webrtc.close_all()
            await hub.close()
            await conversation_engine.close()
            engine.dispose()

    app = FastAPI(title="JARVIS API", version="0.1.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.session_factory = session_factory
    app.state.ai_manager = ai_manager
    app.state.ai_context = ai_context
    app.state.audio_manager = audio_manager
    app.state.voice_pipeline = voice_pipeline
    app.state.text_to_speech = text_to_speech
    app.state.calling_hub = hub
    app.state.calling_webrtc = webrtc
    app.state.calling_telephone = telephone
    app.state.calling_manager = call_manager
    app.state.calling_scheduler = scheduler
    app.state.calling_conversation_engine = conversation_engine
    from app.calling.security import CallingRateLimiter

    app.state.calling_rate_limiter = CallingRateLimiter()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-Calling-Token"],
    )
    app.include_router(chat_router, prefix="/api")
    app.include_router(assistant_router, prefix="/api")
    app.include_router(voice_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    app.include_router(calling_router, prefix="/api/calling")
    app.include_router(calling_webhooks_router, prefix="/api/calling/webhooks")

    @app.get("/api/health")
    async def health() -> dict[str, str | bool]:
        if (
            hasattr(app.state.ai_manager, "router")
            and app_settings.default_ai_provider is not None
            and app_settings.ai_provider not in {"openai", "groq"}
        ):
            provider = app.state.ai_manager.router.last_provider or app_settings.effective_ai_provider
            configured = any(
                item["configured"]
                for item in (await app.state.ai_manager.router.status())["providers"]
            )
            return {
                "status": "ok",
                "service": "jarvis",
                "ai_configured": configured,
                "ai_available": configured,
                "ai_provider": provider,
                "model": app.state.ai_manager.router.model(provider if provider != "auto" else "ollama"),
                "calling_auth_configured": app_settings.calling_auth_configured,
                "scheduler_running": scheduler.running,
            }
        configured = ai_is_configured(app_settings)
        available = (
            await conversation_engine.is_available()
            if app_settings.ai_provider == "ollama"
            else configured
        )
        return {
            "status": "ok",
            "service": "jarvis",
            "ai_configured": configured,
            "ai_available": available,
            "ai_provider": chat_provider(app_settings),
            "model": configured_model(app_settings),
            "calling_auth_configured": app_settings.calling_auth_configured,
            "scheduler_running": scheduler.running,
        }

    return app


app = create_app()
