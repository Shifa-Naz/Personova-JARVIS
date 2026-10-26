"""Start the JARVIS backend.

python run.py                    start the API on 127.0.0.1:5000
python run.py --download-models  fetch the offline speech-recognition model and voice once, then exit
python run.py --check            print capability status, then exit
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional
    load_dotenv = None

from jarvis.app import build_services, create_app
from jarvis.config import load_settings, migrate_legacy_data_dir
from jarvis.logging_setup import setup_logging

log = logging.getLogger("jarvis")


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS backend")
    parser.add_argument("--download-models", action="store_true", help="download the speech model and exit")
    parser.add_argument("--check", action="store_true", help="print capability status and exit")
    args = parser.parse_args()

    if load_dotenv is not None:
        load_dotenv(Path(__file__).with_name(".env"))

    try:
        settings = load_settings()
        migrated = migrate_legacy_data_dir(settings.data_dir)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    setup_logging(settings.logs_dir, settings.debug)
    if migrated:
        log.info("Moved the old ULTRON data folder to %s (models and voices kept)", settings.data_dir)
    services = build_services(settings)

    if args.download_models:
        status = 0
        for name, fetch in (
            (f"speech-recognition model '{settings.stt_model}'", services.transcriber.load),
            (f"voice '{settings.tts_voice}'", services.synthesizer.download),
        ):
            log.info("Downloading %s ...", name)
            try:
                fetch()
                log.info("Ready: %s", name)
            except Exception as exc:  # noqa: BLE001 - report each model independently
                log.error("Could not download %s: %s", name, exc)
                status = 1
        return status

    if args.check:
        ai_ok = services.ai.available()
        print(f"Platform adapter : {services.platform.os_key}")
        print(f"Search roots     : {', '.join(str(r) for r in services.files.roots) or '(none found)'}")
        print(
            f"Offline LLM      : {'ready' if ai_ok else 'unavailable'} ({settings.llm_model})"
            + ("" if ai_ok else f" — {getattr(services.ai, 'last_error', '')}")
        )
        print(
            f"Offline STT      : {'installed' if services.transcriber.installed() else 'not installed'} ({settings.stt_model})"
        )
        synth = services.synthesizer
        tts_state = "ready" if synth.available() else ("voice not downloaded" if synth.installed() else "not installed")
        print(f"Offline TTS      : {tts_state} ({settings.tts_voice})")
        ocr_engine = services.ocr.engine_name()
        print(f"Screen OCR       : {ocr_engine or 'not installed (pip install rapidocr_onnxruntime)'}")
        print(f"Data folder      : {settings.data_dir}")
        print(f"Internet         : {'online' if services.connectivity.online() else 'offline'}")
        return 0

    services.files.start_background_indexing()
    # Load the language model now, so the first question doesn't also pay the loading time.
    threading.Thread(target=services.ai.warm_up, name="jarvis-llm-warmup", daemon=True).start()
    app = create_app(services)
    log.info(
        "JARVIS backend on http://%s:%d (allowed origins: %s)",
        settings.host,
        settings.port,
        ", ".join(settings.allowed_origins),
    )
    app.run(host=settings.host, port=settings.port, debug=settings.debug, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
