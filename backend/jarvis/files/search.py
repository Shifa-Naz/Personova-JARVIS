"""Indexed, ranked, root-confined local file search.

Replaces the old first-substring-match walk. Key guarantees:
- an empty/too-short query never matches everything;
- results never point outside the configured search roots;
- the index is built in the background and refreshed periodically.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

log = logging.getLogger(__name__)

KIND_EXTENSIONS: dict[str, frozenset[str]] = {
    "audio": frozenset({".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}),
    "video": frozenset({".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".m4v"}),
    "image": frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic"}),
    "pdf": frozenset({".pdf"}),
    "document": frozenset(
        {".pdf", ".doc", ".docx", ".odt", ".txt", ".md", ".rtf", ".ppt", ".pptx", ".xls", ".xlsx", ".csv"}
    ),
    "archive": frozenset({".zip", ".rar", ".7z", ".tar", ".gz"}),
}
KIND_EXTENSIONS["media"] = KIND_EXTENSIONS["audio"] | KIND_EXTENSIONS["video"]

SKIP_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        "venv",
        ".venv",
        "env",
        "site-packages",
        "dist",
        "build",
        ".git",
        ".cache",
        "$RECYCLE.BIN",
        "System Volume Information",
    }
)
KNOWN_FOLDERS = ("desktop", "downloads", "documents", "music", "pictures", "videos", "home")
MIN_QUERY_CHARS = 2
_SEP = re.compile(r"[\s_\-.()\[\]]+")


def normalize_name(text: str) -> str:
    return _SEP.sub(" ", text.lower()).strip()


@dataclass(frozen=True)
class FileEntry:
    path: str
    name: str
    norm: str  # normalized stem for matching
    ext: str
    mtime: float
    size: int
    is_dir: bool

    @property
    def folder(self) -> str:
        return Path(self.path).parent.name

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "folder": self.folder,
            "is_dir": self.is_dir,
            "modified": self.mtime,
            "size": self.size,
        }


class FileSearchService:
    def __init__(self, roots: Iterable[Path], max_entries: int = 250_000, refresh_s: float = 120.0) -> None:
        self.roots = tuple(Path(r).expanduser().resolve() for r in roots if Path(r).expanduser().is_dir())
        self.max_entries = max_entries
        self.refresh_s = refresh_s
        self._entries: list[FileEntry] = []
        self._built_at = 0.0
        self._lock = threading.Lock()
        self._building = threading.Lock()

    # ---- index ---------------------------------------------------------
    def build_index(self) -> int:
        with self._building:
            entries: list[FileEntry] = []
            for root in self.roots:
                self._walk(root, entries)
                if len(entries) >= self.max_entries:
                    log.warning("File index truncated at %d entries", self.max_entries)
                    break
            with self._lock:
                self._entries = entries
                self._built_at = time.time()
            log.info("File index built: %d entries across %d roots", len(entries), len(self.roots))
            return len(entries)

    def _walk(self, root: Path, out: list[FileEntry]) -> None:
        stack = [root]
        while stack and len(out) < self.max_entries:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                            continue
                        try:
                            is_dir = entry.is_dir(follow_symlinks=False)
                            if entry.is_symlink():
                                continue
                            st = entry.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        stem, ext = os.path.splitext(entry.name) if not is_dir else (entry.name, "")
                        out.append(
                            FileEntry(
                                entry.path,
                                entry.name,
                                normalize_name(stem),
                                ext.lower(),
                                st.st_mtime,
                                0 if is_dir else st.st_size,
                                is_dir,
                            )
                        )
                        if is_dir:
                            stack.append(Path(entry.path))
            except OSError:
                continue

    def start_background_indexing(self) -> None:
        def loop() -> None:
            while True:
                try:
                    self.build_index()
                except Exception:  # noqa: BLE001 - keep indexing alive
                    log.exception("File indexing failed")
                time.sleep(self.refresh_s)

        threading.Thread(target=loop, name="jarvis-file-index", daemon=True).start()

    def note_created(self, path: Path) -> None:
        """Add a just-created file/folder to the index so it can be found before the next rebuild."""
        try:
            st = path.stat()
        except OSError:
            return
        is_dir = path.is_dir()
        stem, ext = (path.name, "") if is_dir else (path.stem, path.suffix.lower())
        entry = FileEntry(
            str(path), path.name, normalize_name(stem), ext, st.st_mtime, 0 if is_dir else st.st_size, is_dir
        )
        with self._lock:
            self._entries = [e for e in self._entries if e.path != entry.path] + [entry]

    def _snapshot(self) -> list[FileEntry]:
        with self._lock:
            ready = self._built_at > 0
            entries = self._entries
        if not ready:
            self.build_index()
            with self._lock:
                entries = self._entries
        return entries

    # ---- queries -------------------------------------------------------
    def resolve_known_folder(self, name: str) -> Path | None:
        key = name.lower().strip()
        if key == "home":
            return Path.home()
        for root in self.roots:
            if root.name.lower() == key:
                return root
        candidate = Path.home() / key.capitalize()
        return candidate if candidate.is_dir() and self.is_within_roots(candidate) else None

    def is_within_roots(self, path: Path) -> bool:
        try:
            resolved = Path(path).expanduser().resolve()
        except OSError:
            return False
        return any(resolved == root or root in resolved.parents for root in self.roots)

    def search(
        self,
        query: str = "",
        *,
        kind: str | None = None,
        ext: str | None = None,
        dirs: bool = False,
        files: bool = True,
        modified_since: float | None = None,
        within: Path | None = None,
        sort: str = "relevance",
        limit: int = 10,
    ) -> list[FileEntry]:
        q = normalize_name(query)
        has_filter = bool(kind or ext or modified_since or within or sort == "latest")
        if len(q) < MIN_QUERY_CHARS and not has_filter:
            return []

        exts = set(KIND_EXTENSIONS.get(kind, ())) if kind else set()
        if ext:
            exts = {ext if ext.startswith(".") else f".{ext}"}
        within_s = str(within.resolve()) + os.sep if within else None

        scored: list[tuple[float, FileEntry]] = []
        for entry in self._snapshot():
            if entry.is_dir and not dirs:
                continue
            if not entry.is_dir and not files:
                continue
            if exts and entry.ext not in exts:
                continue
            if modified_since and entry.mtime < modified_since:
                continue
            if within_s and not entry.path.startswith(within_s):
                continue
            score = self._score(q, entry) if q else 1.0
            if score > 0:
                scored.append((score, entry))

        if sort == "latest":
            scored.sort(key=lambda s: (s[1].mtime, s[0]), reverse=True)
        else:
            scored.sort(key=lambda s: (s[0], s[1].mtime), reverse=True)
        return [e for _, e in scored[:limit]]

    @staticmethod
    def _score(q: str, entry: FileEntry) -> float:
        name = entry.norm
        if not name:
            return 0.0
        if name == q:
            return 100.0
        if name.startswith(q):
            return 85.0
        tokens = q.split()
        words = name.split()
        if all(t in words for t in tokens):
            return 75.0
        if all(t in name for t in tokens):
            return 65.0
        hits = sum(1 for t in tokens if len(t) >= 3 and t in name)
        if hits:
            return 40.0 * hits / len(tokens)
        ratio = SequenceMatcher(None, q, name).ratio()
        return 30.0 * ratio if ratio >= 0.75 else 0.0
