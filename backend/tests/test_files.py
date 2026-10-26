from __future__ import annotations

import os
import time

from jarvis.files.search import FileSearchService


def svc(settings) -> FileSearchService:
    return FileSearchService(settings.search_roots)


def test_empty_or_tiny_query_matches_nothing(settings):
    s = svc(settings)
    assert s.search("") == []
    assert s.search("a") == []


def test_ranking_prefers_exact_then_prefix(settings):
    names = [e.name for e in svc(settings).search("believer")]
    assert names[0] == "Believer - Imagine Dragons.mp3"


def test_kind_filter(settings):
    names = {e.name for e in svc(settings).search("", kind="audio")}
    assert names == {"Believer - Imagine Dragons.mp3", "Thunder.mp3"}


def test_latest_sort_with_kind(settings):
    assert svc(settings).search("", kind="pdf", sort="latest")[0].name == "lecture notes.pdf"


def test_modified_since(settings):
    names = {e.name for e in svc(settings).search("", modified_since=time.time() - 3600)}
    assert names == {"lecture notes.pdf"}


def test_folders_search(settings):
    hits = svc(settings).search("react", dirs=True, files=False)
    assert hits and hits[0].name == "react-app"


def test_confinement(settings, tmp_path, home):
    s = svc(settings)
    assert s.is_within_roots(home / "Documents" / "Resume_2026.pdf")
    assert not s.is_within_roots(tmp_path / "data")
    assert not s.is_within_roots(home / "Documents" / ".." / ".." / "etc")


def test_symlinks_are_not_followed(settings, home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "zzqx-hidden.mp3").write_bytes(b"x")
    os.symlink(outside, home / "Music" / "link")
    names = [e.name for e in svc(settings).search("zzqx hidden")]
    assert names == []


def test_known_folder(settings, home):
    assert svc(settings).resolve_known_folder("downloads") == (home / "Downloads").resolve()
