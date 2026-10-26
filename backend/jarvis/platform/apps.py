"""Allow-listed applications JARVIS may launch or close.

Launch specs are argv lists or OS "start" targets — never shell strings. Extend
or override entries with `JARVIS_CONFIG_FILE` (see `.env.example`).

Linux spec forms:   ["binary", "arg"]           first available binary wins
                    {"flatpak": "com.app.Id"}   used if that flatpak is installed
Windows spec forms: {"start": "chrome"}         ShellExecute (App Paths / URI)
                    {"argv": ["notepad.exe"]}   resolved via PATH
                    {"argv": [...], "new_console": true}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AppEntry:
    name: str
    display_name: str
    aliases: tuple[str, ...]
    linux: tuple[Any, ...] = ()
    windows: tuple[Any, ...] = ()
    process_names: dict[str, tuple[str, ...]] = field(default_factory=dict)
    is_browser: bool = False

    def processes_for(self, os_key: str) -> tuple[str, ...]:
        return self.process_names.get(os_key, ())


DEFAULT_APPS: tuple[AppEntry, ...] = (
    AppEntry(
        "chrome",
        "Chrome",
        ("chrome", "google chrome", "chromium"),
        linux=(
            ["google-chrome"],
            ["google-chrome-stable"],
            ["chromium-browser"],
            ["chromium"],
            {"flatpak": "com.google.Chrome"},
            {"flatpak": "org.chromium.Chromium"},
        ),
        windows=({"start": "chrome"},),
        process_names={"linux": ("chrome", "chromium", "chromium-browser"), "windows": ("chrome.exe",)},
        is_browser=True,
    ),
    AppEntry(
        "firefox",
        "Firefox",
        ("firefox", "mozilla firefox", "mozilla"),
        linux=(["firefox"], {"flatpak": "org.mozilla.firefox"}),
        windows=({"start": "firefox"},),
        process_names={"linux": ("firefox", "firefox-bin"), "windows": ("firefox.exe",)},
        is_browser=True,
    ),
    AppEntry(
        "edge",
        "Microsoft Edge",
        ("edge", "microsoft edge"),
        linux=(["microsoft-edge"], ["microsoft-edge-stable"]),
        windows=({"start": "msedge"},),
        process_names={"linux": ("msedge",), "windows": ("msedge.exe",)},
        is_browser=True,
    ),
    AppEntry(
        "vscode",
        "VS Code",
        ("vs code", "vscode", "visual studio code", "code editor", "code"),
        linux=(["code"], ["codium"], {"flatpak": "com.visualstudio.code"}),
        windows=({"argv": ["code"]},),
        process_names={"linux": ("code", "codium"), "windows": ("Code.exe",)},
    ),
    AppEntry(
        "terminal",
        "Terminal",
        ("terminal", "command prompt", "console", "shell window", "cmd"),
        linux=(["ptyxis"], ["gnome-terminal"], ["konsole"], ["xfce4-terminal"], ["xterm"]),
        windows=({"start": "wt"}, {"argv": ["cmd.exe"], "new_console": True}),
        process_names={
            "linux": ("ptyxis", "gnome-terminal-server", "konsole", "xfce4-terminal", "xterm"),
            "windows": ("WindowsTerminal.exe",),
        },
    ),
    AppEntry(
        "spotify",
        "Spotify",
        ("spotify",),
        linux=(["spotify"], {"flatpak": "com.spotify.Client"}),
        windows=({"start": "spotify:"},),
        process_names={"linux": ("spotify",), "windows": ("Spotify.exe",)},
    ),
    AppEntry(
        "calculator",
        "Calculator",
        ("calculator", "calc"),
        linux=(["gnome-calculator"], ["kcalc"], ["galculator"], {"flatpak": "org.gnome.Calculator"}),
        windows=({"argv": ["calc.exe"]},),
        process_names={
            "linux": ("gnome-calculator", "kcalc", "galculator"),
            "windows": ("CalculatorApp.exe", "calc.exe"),
        },
    ),
    AppEntry(
        "file_manager",
        "File Manager",
        ("file manager", "files", "file explorer", "explorer", "nautilus"),
        linux=(["nautilus"], ["dolphin"], ["thunar"], ["nemo"]),
        windows=({"argv": ["explorer.exe"]},),
        # Never close explorer.exe on Windows — it is the desktop shell.
        process_names={"linux": ("nautilus", "dolphin", "thunar", "nemo")},
    ),
    AppEntry(
        "settings",
        "Settings",
        ("settings", "system settings", "control center", "control panel"),
        linux=(["gnome-control-center"], ["systemsettings"]),
        windows=({"start": "ms-settings:"},),
        process_names={"linux": ("gnome-control-center", "systemsettings"), "windows": ("SystemSettings.exe",)},
    ),
    AppEntry(
        "text_editor",
        "Text Editor",
        ("notepad", "text editor", "editor", "gedit"),
        linux=(["gnome-text-editor"], ["gedit"], ["kate"], ["mousepad"], {"flatpak": "org.gnome.TextEditor"}),
        windows=({"argv": ["notepad.exe"]},),
        process_names={
            "linux": ("gnome-text-editor", "gedit", "kate", "mousepad"),
            "windows": ("Notepad.exe", "notepad.exe"),
        },
    ),
)


class AppRegistry:
    def __init__(self, overrides: dict[str, Any] | None = None) -> None:
        self._apps: dict[str, AppEntry] = {a.name: a for a in DEFAULT_APPS}
        for name, raw in (overrides or {}).items():
            self._apps[name] = AppEntry(
                name=name,
                display_name=raw.get("display_name", name.replace("_", " ").title()),
                aliases=tuple(a.lower() for a in raw.get("aliases", [name])),
                linux=tuple(raw.get("linux", ())),
                windows=tuple(raw.get("windows", ())),
                process_names={k: tuple(v) for k, v in raw.get("process_names", {}).items()},
                is_browser=bool(raw.get("is_browser", False)),
            )
        self._alias_index: dict[str, str] = {}
        for app in self._apps.values():
            self._alias_index[app.name] = app.name
            for alias in app.aliases:
                self._alias_index[alias] = app.name

    def get(self, name: str) -> AppEntry | None:
        return self._apps.get(name)

    def resolve(self, spoken: str) -> AppEntry | None:
        key = " ".join(spoken.lower().replace("_", " ").split())
        for suffix in (" app", " application", " browser", " window"):
            if key.endswith(suffix) and key[: -len(suffix)] in self._alias_index:
                key = key[: -len(suffix)]
        name = self._alias_index.get(key)
        return self._apps.get(name) if name else None

    def all(self) -> list[AppEntry]:
        return list(self._apps.values())

    def aliases(self) -> list[str]:
        return sorted(self._alias_index, key=len, reverse=True)
