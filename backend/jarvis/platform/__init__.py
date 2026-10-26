"""Select the adapter for the running operating system."""

from __future__ import annotations

import sys

from jarvis.platform.base import PlatformAdapter


def get_platform_adapter() -> PlatformAdapter:
    if sys.platform == "win32":
        from jarvis.platform.windows import WindowsAdapter

        return WindowsAdapter()
    if sys.platform.startswith("linux"):
        from jarvis.platform.linux import LinuxAdapter

        return LinuxAdapter()
    raise RuntimeError(f"Unsupported platform: {sys.platform}. JARVIS supports Windows and Linux.")


def platform_name() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform
