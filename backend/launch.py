"""One-command start for JARVIS: Ollama (if needed), the backend, the frontend, and the JARVIS window.

    python launch.py                      start everything and open JARVIS
    python launch.py --install-autostart  also start JARVIS automatically when you log in
    python launch.py --remove-autostart   stop starting at login

Run it with the Python of the JARVIS environment (e.g. `conda activate ultron` first).

The window is a Chrome (or Edge) app window with its own profile, started with flags that let JARVIS speak and
listen without first being clicked (browsers otherwise block audio until the page is clicked) and keep listening
in the background. The microphone is pre-approved for the JARVIS page only, in that separate profile.

While running, the launcher restarts a crashed backend or frontend, and reopens the window after the laptop wakes
up if it was closed. The backend itself detects the wake-up and sends the briefing.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
sys.path.insert(0, str(BACKEND_DIR))

from jarvis.config import load_settings  # noqa: E402
from jarvis.wake_watch import SLEEP_GAP_S  # noqa: E402

try:
    from dotenv import load_dotenv
except ImportError:  # optional
    load_dotenv = None

log = logging.getLogger("jarvis.launcher")

FRONTEND_PORT = int(os.environ.get("JARVIS_FRONTEND_PORT", "8080"))
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BROWSER_FLAGS = (
    "--autoplay-policy=no-user-gesture-required",  # speak and listen without a first click
    "--disable-background-timer-throttling",  # keep the wake listener running when the window is in the back
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--no-first-run",
    "--no-default-browser-check",
)


# ---------------------------------------------------------------- helpers
def reachable(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - local URLs only
            return resp.status < 500
    except Exception:  # noqa: BLE001
        return False


def wait_for(url: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if reachable(url):
            return True
        time.sleep(0.5)  # polling a local server with a deadline
    return False


def child_env() -> dict[str, str]:
    """On Windows a conda env that wasn't activated (e.g. started from the Startup folder) misses its DLL folders,
    and onnxruntime/numpy then fail with "DLL load failed". Put them on PATH for the processes we start."""
    env = dict(os.environ)
    if sys.platform == "win32":
        root = Path(sys.executable).parent
        extra = [root, root / "Library" / "bin", root / "Library" / "usr" / "bin", root / "Scripts"]
        env["PATH"] = os.pathsep.join([*(str(p) for p in extra if p.is_dir()), env.get("PATH", "")])
    return env


def spawn(argv: list[str], cwd: Path, log_file: Path) -> subprocess.Popen:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    out = open(log_file, "ab")  # noqa: SIM115 - handed to the child process
    return subprocess.Popen(  # noqa: S603
        argv, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, creationflags=NO_WINDOW, env=child_env()
    )


def find_browser() -> list[str] | None:
    """Chrome first, then Edge, then Chromium. Returns the argv prefix."""
    if sys.platform == "win32":
        roots = [os.environ.get(k, "") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for rel in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"):
            for root in roots:
                path = Path(root) / rel
                if root and path.exists():
                    return [str(path)]
        return None
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "brave-browser",
    ):
        path = shutil.which(name)
        if path:
            return [path]
    if shutil.which("flatpak"):
        for app_id in ("com.google.Chrome", "org.chromium.Chromium", "com.microsoft.Edge"):
            if subprocess.run(["flatpak", "info", app_id], capture_output=True, check=False).returncode == 0:  # noqa: S603, S607
                return ["flatpak", "run", app_id]
    return None


def prepare_profile(profile: Path) -> None:
    """Pre-approve the microphone for the JARVIS page in its own browser profile (first run only)."""
    prefs = profile / "Default" / "Preferences"
    if prefs.exists():
        return
    prefs.parent.mkdir(parents=True, exist_ok=True)
    allow = {"setting": 1}
    exceptions = {
        "media_stream_mic": {f"{FRONTEND_URL},*": allow, f"http://127.0.0.1:{FRONTEND_PORT},*": allow},
    }
    prefs.write_text(json.dumps({"profile": {"content_settings": {"exceptions": exceptions}}}), encoding="utf-8")


def window_running(profile: Path) -> bool:
    import psutil

    marker = f"--user-data-dir={profile}"
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if marker in (proc.info["cmdline"] or []):
                return True
        except psutil.Error:
            continue
    return False


def open_window(profile: Path, briefing: bool) -> None:
    url = FRONTEND_URL + ("/?briefing=1" if briefing else "/")
    browser = find_browser()
    if browser is None:
        import webbrowser

        log.warning("Chrome/Edge not found; opening the default browser (click the page once to enable audio).")
        webbrowser.open(url)
        return
    prepare_profile(profile)
    argv = [*browser, f"--app={url}", f"--user-data-dir={profile}", *BROWSER_FLAGS]
    subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
    log.info("Opened the JARVIS window")


# ---------------------------------------------------------------- autostart
def _autostart_entry() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup\JARVIS.cmd"
    return Path.home() / ".config" / "autostart" / "jarvis.desktop"


def install_autostart() -> Path:
    entry = _autostart_entry()
    entry.parent.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable)
    script = Path(__file__).resolve()
    if sys.platform == "win32":
        pythonw = python.with_name("pythonw.exe")
        exe = pythonw if pythonw.exists() else python
        entry.write_text(f'@echo off\r\nstart "" "{exe}" "{script}" --at-login\r\n', encoding="utf-8")
    else:
        entry.write_text(
            "[Desktop Entry]\nType=Application\nName=JARVIS\nComment=Start the JARVIS assistant\n"
            f'Exec="{python}" "{script}" --at-login\nX-GNOME-Autostart-enabled=true\nTerminal=false\n',
            encoding="utf-8",
        )
    return entry


def remove_autostart() -> bool:
    entry = _autostart_entry()
    if entry.exists():
        entry.unlink()
        return True
    return False


# ---------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(description="Start JARVIS")
    parser.add_argument("--install-autostart", action="store_true", help="start JARVIS when you log in")
    parser.add_argument("--remove-autostart", action="store_true", help="stop starting JARVIS at login")
    parser.add_argument("--at-login", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-window", action="store_true", help="start the servers only")
    args = parser.parse_args()

    if args.remove_autostart:
        print("Removed." if remove_autostart() else "JARVIS wasn't set to start at login.")
        return 0
    if args.install_autostart:
        print(f"JARVIS will start when you log in ({install_autostart()}).")

    if load_dotenv is not None:
        load_dotenv(BACKEND_DIR / ".env")
    settings = load_settings()
    logs = settings.logs_dir
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(logs / "launcher.log", encoding="utf-8")],
    )
    backend_url = f"http://{settings.host}:{settings.port}/api/v1/health"
    profile = settings.data_dir / "browser-profile"
    children: dict[str, subprocess.Popen] = {}

    def ensure_ollama() -> None:
        if not settings.llm_enabled or reachable(settings.llm_url + "/api/version"):
            return
        ollama = shutil.which("ollama")
        if ollama and settings.llm_url.startswith(("http://127.0.0.1", "http://localhost")):
            log.info("Starting Ollama")
            children["ollama"] = spawn([ollama, "serve"], BACKEND_DIR, logs / "ollama.log")

    def ensure_backend() -> None:
        if reachable(backend_url):
            return
        log.info("Starting the JARVIS backend")
        children["backend"] = spawn(
            [sys.executable, str(BACKEND_DIR / "run.py")], BACKEND_DIR, logs / "backend.out.log"
        )

    def ensure_frontend() -> None:
        if reachable(FRONTEND_URL):
            return
        node = shutil.which("node")
        vite = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not node or not vite.exists():
            log.error("The frontend isn't installed. Run `npm ci` in %s first.", FRONTEND_DIR)
            return
        log.info("Starting the JARVIS frontend")
        argv = [node, str(vite), "--port", str(FRONTEND_PORT), "--strictPort"]
        children["frontend"] = spawn(argv, FRONTEND_DIR, logs / "frontend.out.log")

    def stop_on_signal(signum, frame):  # noqa: ARG001 - signal handler signature
        raise KeyboardInterrupt

    # Closing the window, logging out or `kill` must also stop the backend, frontend and Ollama we started.
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop_on_signal)

    ensure_ollama()
    ensure_backend()
    ensure_frontend()
    ok = wait_for(backend_url, 90) and wait_for(FRONTEND_URL, 60)
    if not ok:
        log.error("JARVIS didn't start. See the logs in %s", logs)
    if not args.no_window:
        open_window(profile, briefing=args.at_login)
    print("JARVIS is running. Keep this window open; press Ctrl+C to stop JARVIS.")

    last_wall, last_mono = time.time(), time.monotonic()
    try:
        while True:
            time.sleep(5)  # supervision interval
            wall, mono = time.time(), time.monotonic()
            woke = (wall - last_wall) - (mono - last_mono) > SLEEP_GAP_S or (mono - last_mono) > 5 + SLEEP_GAP_S
            last_wall, last_mono = wall, mono
            for name, proc in list(children.items()):
                if proc.poll() is not None:
                    log.warning("%s stopped (exit code %s); restarting it", name, proc.returncode)
                    children.pop(name)
            ensure_ollama()
            ensure_backend()
            ensure_frontend()
            if woke and not args.no_window and not window_running(profile):
                log.info("Woke up and the JARVIS window was closed; reopening it")
                wait_for(FRONTEND_URL, 30)
                open_window(profile, briefing=False)
    except KeyboardInterrupt:
        log.info("Stopping JARVIS")
    finally:
        for proc in children.values():
            proc.terminate()
        for proc in children.values():
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
