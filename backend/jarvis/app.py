"""Flask API. Local-only: loopback bind, origin allow-list, per-launch session token.

Endpoints (all JSON, prefix /api/v1):
  GET  /health                     no token
  GET  /session                    no token; returns the token to allowed origins only
  GET  /status                     capabilities (llm, stt, online, automation)
  GET  /system                     live telemetry for the HUD
  POST /plan      {text, session_id}
  POST /execute   {plan_id, session_id}
  POST /confirm   {confirmation_id, decision: confirm|cancel, session_id}
  POST /command   {text, session_id}          plan + execute
  POST /transcribe  raw audio body            offline STT
  POST /speak     {text}  -> audio/wav         offline TTS
  GET  /logs/recent
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import queue
import threading
from dataclasses import dataclass
from typing import Any

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from jarvis import __version__
from jarvis.actions import build_registry
from jarvis.actions.base import ActionError
from jarvis.actions.system import telemetry
from jarvis.ai.provider import AiProvider, build_provider
from jarvis.config import Settings
from jarvis.core.context import Connectivity, ExecContext
from jarvis.core.intent import IntentMatcher
from jarvis.core.pipeline import Pipeline
from jarvis.files.search import FileSearchService
from jarvis.logging_setup import recent_events
from jarvis.platform import get_platform_adapter, platform_name
from jarvis.platform.apps import AppRegistry
from jarvis.platform.base import PlatformAdapter
from jarvis.storage.store import JsonStore, new_id
from jarvis.vision.ocr import OcrEngine
from jarvis.voice.stt import Transcriber
from jarvis.voice.tts import Synthesizer

log = logging.getLogger("jarvis.api")

WAKE_PROMPT = "Jarvis, are you up?"
# Biases Whisper toward the words people use with JARVIS ("write" not "right", "note", app names).
COMMAND_PROMPT = (
    "Jarvis, write me a program. Make a note. Remind me tomorrow at 5 pm. Open Chrome. Search YouTube. "
    "What's on my screen? Schedule a meeting on Friday."
)
PUBLIC_PATHS = {"/api/v1/health", "/api/v1/session"}
MAX_AUDIO_BYTES = 10 * 1024 * 1024


@dataclass
class Services:
    settings: Settings
    pipeline: Pipeline
    files: FileSearchService
    ai: AiProvider
    platform: PlatformAdapter
    connectivity: Connectivity
    transcriber: Transcriber
    synthesizer: Synthesizer
    ocr: OcrEngine
    store: JsonStore


def build_services(
    settings: Settings,
    *,
    platform: PlatformAdapter | None = None,
    ai: AiProvider | None = None,
    files: FileSearchService | None = None,
    connectivity: Connectivity | None = None,
    synthesizer: Synthesizer | None = None,
    transcriber: Transcriber | None = None,
    ocr: OcrEngine | None = None,
    store: JsonStore | None = None,
) -> Services:
    apps = AppRegistry(settings.app_overrides)
    platform = platform or get_platform_adapter()
    ai = ai or build_provider(settings)
    files = files or FileSearchService(settings.search_roots)
    connectivity = connectivity or Connectivity()
    ocr = ocr or OcrEngine(settings.tesseract_cmd)
    store = store or JsonStore(settings.data_dir / "data")
    pipeline = Pipeline(
        ocr=ocr,
        store=store,
        settings=settings,
        registry=build_registry(),
        matcher=IntentMatcher(apps),
        ai=ai,
        platform=platform,
        apps=apps,
        files=files,
        connectivity=connectivity,
    )
    transcriber = transcriber or Transcriber(
        settings.stt_model, settings.stt_device, settings.stt_compute_type, str(settings.models_dir)
    )
    synthesizer = synthesizer or Synthesizer(settings.tts_voice, settings.voices_dir, settings.tts_rate)
    return Services(settings, pipeline, files, ai, platform, connectivity, transcriber, synthesizer, ocr, store)


def _automation_available(platform: PlatformAdapter) -> bool:
    if platform.os_key == "linux" and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return False
    import importlib.util

    return importlib.util.find_spec("pyautogui") is not None


def create_app(services: Services) -> Flask:
    settings = services.settings
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_AUDIO_BYTES
    CORS(
        app,
        origins=list(settings.allowed_origins),
        allow_headers=["Content-Type", "X-Jarvis-Token"],
        methods=["GET", "POST", "OPTIONS"],
    )

    def error(code: str, message: str, status: int):
        return jsonify({"error_code": code, "reply": message}), status

    @app.before_request
    def guard():
        # DNS-rebinding defence: only answer requests addressed to a loopback host name.
        host = (request.host or "").rsplit(":", 1)[0].strip("[]")
        if host not in ("127.0.0.1", "localhost", "::1"):
            return error("FORBIDDEN_HOST", "JARVIS only answers requests addressed to localhost.", 403)
        if request.method == "OPTIONS":
            return None
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") not in settings.allowed_origins:
            log.warning("Rejected request from origin %s", origin)
            return error("FORBIDDEN_ORIGIN", "This origin is not allowed to control JARVIS.", 403)
        if request.path.startswith("/api/") and request.path not in PUBLIC_PATHS:
            supplied = request.headers.get("X-Jarvis-Token", "")
            if not hmac.compare_digest(supplied, settings.token):
                return error("UNAUTHORIZED", "Missing or invalid session token.", 401)
        return None

    def body() -> dict:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def session_id(data: dict) -> str:
        sid = str(data.get("session_id") or "default")
        return sid[:64]

    def capabilities() -> dict:
        ai_ok = services.ai.available()
        return {
            "llm": ai_ok,
            "llm_model": settings.llm_model if settings.llm_enabled else None,
            "llm_error": getattr(services.ai, "last_error", None) if not ai_ok else None,
            "stt": services.transcriber.installed(),
            "stt_model": settings.stt_model,
            "tts": settings.tts_enabled and services.synthesizer.available(),
            "tts_voice": settings.tts_voice,
            "screen_ocr": services.ocr.engine_name(),
            "vision_model": settings.vision_model if services.ai.vision_available() else None,
            "storage_recovered": list(services.store.recovered),
            "online": services.connectivity.online(),
            "automation": _automation_available(services.platform),
        }

    @app.get("/api/v1/health")
    def health():
        return jsonify({"ok": True, "name": "JARVIS", "version": __version__})

    @app.get("/api/v1/session")
    def session():
        return jsonify(
            {
                "token": settings.token,
                "platform": platform_name(),
                "version": __version__,
                "capabilities": capabilities(),
            }
        )

    @app.get("/api/v1/status")
    def status():
        return jsonify({"platform": platform_name(), "capabilities": capabilities()})

    @app.get("/api/v1/system")
    def system():
        ctx = ExecContext(
            settings,
            services.platform,
            services.pipeline.apps,
            services.files,
            services.ai,
            services.connectivity,
            services.pipeline.sessions.get("default"),
        )
        return jsonify(telemetry(ctx))

    @app.post("/api/v1/plan")
    def plan():
        data = body()
        return jsonify(services.pipeline.plan(str(data.get("text", "")), session_id(data)).model_dump())

    @app.post("/api/v1/execute")
    def execute():
        data = body()
        return jsonify(services.pipeline.execute(str(data.get("plan_id", "")), session_id(data)).model_dump())

    @app.post("/api/v1/execute/stream")
    def execute_stream():
        """Like /execute, but streams answer text as it is generated (Server-Sent Events).

        Events: {"type": "delta", "text": "..."} while the model writes, then {"type": "done", "response": {...}}.
        """
        data = body()
        plan_id, sid = str(data.get("plan_id", "")), session_id(data)
        events: queue.Queue = queue.Queue()

        def work() -> None:
            try:
                resp = services.pipeline.execute(plan_id, sid, on_delta=lambda t: events.put(("delta", t)))
                events.put(("done", resp.model_dump()))
            except Exception:  # noqa: BLE001 - report instead of leaving the client hanging
                log.exception("Streaming execute failed")
                events.put(
                    (
                        "done",
                        {
                            "request_id": "",
                            "status": "error",
                            "reply": "Something went wrong inside JARVIS.",
                            "results": [],
                            "error_code": "INTERNAL_ERROR",
                            "success": False,
                            "response_type": "error",
                            "speech": "Something went wrong inside JARVIS.",
                        },
                    )
                )

        threading.Thread(target=work, name="jarvis-stream", daemon=True).start()

        def generate():
            while True:
                kind, payload = events.get()
                if kind == "delta":
                    yield f"data: {json.dumps({'type': 'delta', 'text': payload})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'done', 'response': payload})}\n\n"
                    return

        return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/confirm")
    def confirm():
        data = body()
        decision = data.get("decision")
        if decision not in ("confirm", "cancel"):
            return error("INVALID_PARAMS", "decision must be 'confirm' or 'cancel'.", 400)
        resp = services.pipeline.confirm(str(data.get("confirmation_id", "")), decision, session_id(data))
        return jsonify(resp.model_dump())

    @app.post("/api/v1/command")
    def command():
        data = body()
        return jsonify(services.pipeline.command(str(data.get("text", "")), session_id(data)).model_dump())

    @app.post("/api/v1/transcribe")
    def transcribe():
        audio = request.get_data(cache=False)
        content_type = (request.content_type or "").split(";")[0]
        suffix = {
            "audio/webm": ".webm",
            "audio/ogg": ".ogg",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/mp4": ".m4a",
            "audio/mpeg": ".mp3",
        }.get(content_type, ".webm")
        try:
            # Wake-phrase checks are biased toward the name so "Jarvis" isn't heard as "Travis".
            prompt = WAKE_PROMPT if request.args.get("hint") == "wake" else COMMAND_PROMPT
            text, confidence = services.transcriber.transcribe_detailed(audio, suffix, prompt)
        except ActionError as exc:
            status_code = 503 if exc.code == "STT_UNAVAILABLE" else 422
            return error(exc.code, exc.message, status_code)
        return jsonify({"text": text, "confidence": confidence})

    @app.post("/api/v1/speak")
    def speak():
        if not settings.tts_enabled:
            return error("TTS_UNAVAILABLE", "Offline speech is disabled (JARVIS_TTS_ENABLED=false).", 503)
        text = str(body().get("text", ""))
        try:
            audio = services.synthesizer.synthesize(text)
        except ActionError as exc:
            status_code = 503 if exc.code == "TTS_UNAVAILABLE" else 422
            return error(exc.code, exc.message, status_code)
        return Response(audio, mimetype="audio/wav", headers={"Cache-Control": "no-store"})

    # ---- notes / tasks / events for the productivity pages (same store the assistant uses) -----
    page_collections = ("notes", "tasks", "events")
    editable = {
        "notes": {"title", "content", "color", "previous"},
        "tasks": {"title", "completed", "priority", "due", "due_time"},
        "events": {"title", "date", "time"},
    }

    def clean_item(kind: str, raw: Any) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("expected an object")
        item = {k: v for k, v in raw.items() if k in editable[kind]}
        for key, value in item.items():
            if isinstance(value, str) and len(value) > 5000:
                raise ValueError(f"{key} is too long")
        if "title" in item and not str(item["title"]).strip():
            raise ValueError("title can't be empty")
        return item

    @app.get("/api/v1/items/<kind>")
    def list_items(kind: str):
        if kind not in page_collections:
            return error("NOT_FOUND", "Unknown collection.", 404)
        return jsonify({"items": services.store.load(kind)})

    @app.post("/api/v1/items/<kind>")
    def create_item(kind: str):
        if kind not in page_collections:
            return error("NOT_FOUND", "Unknown collection.", 404)
        try:
            item = clean_item(kind, request.get_json(silent=True))
        except ValueError as exc:
            return error("INVALID_PARAMS", str(exc), 400)
        if not item.get("title"):
            return error("INVALID_PARAMS", "title is required", 400)
        return jsonify({"item": services.store.add(kind, item)}), 201

    @app.patch("/api/v1/items/<kind>/<item_id>")
    def update_item(kind: str, item_id: str):
        if kind not in page_collections:
            return error("NOT_FOUND", "Unknown collection.", 404)
        try:
            patch = clean_item(kind, request.get_json(silent=True))
        except ValueError as exc:
            return error("INVALID_PARAMS", str(exc), 400)
        item = services.store.update(kind, item_id, patch)
        return jsonify({"item": item}) if item else error("NOT_FOUND", "That item no longer exists.", 404)

    @app.delete("/api/v1/items/<kind>/<item_id>")
    def delete_item(kind: str, item_id: str):
        if kind not in page_collections:
            return error("NOT_FOUND", "Unknown collection.", 404)
        if not services.store.delete(kind, item_id):
            return error("NOT_FOUND", "That item no longer exists.", 404)
        return jsonify({"deleted": item_id})

    @app.post("/api/v1/items/<kind>/import")
    def import_items(kind: str):
        """One-time migration of data the old frontend kept in browser localStorage."""
        if kind not in page_collections:
            return error("NOT_FOUND", "Unknown collection.", 404)
        incoming = (request.get_json(silent=True) or {}).get("items")
        if not isinstance(incoming, list) or len(incoming) > 2000:
            return error("INVALID_PARAMS", "items must be a list (max 2000)", 400)
        existing = services.store.load(kind)
        known = {(x.get("title"), x.get("date"), x.get("content")) for x in existing}
        added = 0
        for raw in incoming:
            try:
                item = clean_item(kind, raw)
            except ValueError:
                continue
            sig = (item.get("title"), item.get("date"), item.get("content"))
            if item.get("title") and sig not in known:
                existing.append({"id": str(raw.get("id") or "") or None, **item})
                known.add(sig)
                added += 1

        for x in existing:
            x["id"] = x.get("id") or new_id()
        services.store.save(kind, existing)
        return jsonify({"imported": added, "items": existing})

    @app.get("/api/v1/logs/recent")
    def logs_recent():
        return jsonify({"events": recent_events.list(80)})

    @app.errorhandler(413)
    def too_large(_exc):
        return error("TOO_LARGE", "That upload is too large.", 413)

    @app.errorhandler(404)
    def not_found(_exc):
        return error("NOT_FOUND", "Unknown endpoint.", 404)

    @app.errorhandler(Exception)
    def unhandled(exc):
        log.exception("Unhandled API error")
        return error("INTERNAL_ERROR", "Something went wrong inside JARVIS.", 500)

    return app
