"""Latest headlines from public RSS/Atom feeds (no API key).

Headlines are untrusted outside text: they are only shown and read aloud, never handed to the planner or
executed. Feeds are tried in order until one gives enough items; results are cached so the briefing and the
dashboard don't refetch on every request.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass
from html import unescape
from xml.etree import ElementTree as ET

from jarvis.actions.base import ActionError

log = logging.getLogger(__name__)

DEFAULT_FEEDS = (
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
)
MAX_FEED_BYTES = 3_000_000
FEED_TIMEOUT_S = 6
CACHE_TTL_S = 15 * 60
_ATOM = "{http://www.w3.org/2005/Atom}"
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Headline:
    title: str
    source: str
    url: str
    published: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _clean(text: str | None) -> str:
    return " ".join(unescape(_TAGS.sub(" ", text or "")).split())


def _safe_url(url: str) -> str:
    url = (url or "").strip()
    return url if url.startswith(("https://", "http://")) else ""


def _feed_name(url: str) -> str:
    host = re.sub(r"^https?://(?:www\.|feeds\.)?", "", url).split("/")[0]
    return {"news.google.com": "Google News"}.get(host, host.split(".")[0].capitalize())


def parse_feed(data: bytes, feed_url: str = "") -> list[Headline]:
    """RSS 2.0 or Atom. Refuses documents with entity declarations (entity-expansion attacks)."""
    head = data[:4096].lower()
    if b"<!entity" in head or b"<!doctype" in head:
        raise ValueError("feed declares entities")
    root = ET.fromstring(data)  # noqa: S314 - DTDs/entities refused above; expat also limits expansion
    out: list[Headline] = []
    if root.tag.endswith("rss") or root.find("channel") is not None:
        fallback = _clean(root.findtext("channel/title")) or _feed_name(feed_url)
        for item in root.iter("item"):
            title = _clean(item.findtext("title"))
            source = _clean(item.findtext("source")) or fallback
            # Google News titles end with " - Source"; keep the headline and the source apart.
            if source and title.endswith(f" - {source}"):
                title = title[: -len(source) - 3].rstrip()
            url = _safe_url(item.findtext("link") or "")
            if title and url:
                out.append(Headline(title, source, url, _clean(item.findtext("pubDate"))))
    elif root.tag == f"{_ATOM}feed":
        source = _clean(root.findtext(f"{_ATOM}title")) or _feed_name(feed_url)
        for entry in root.iter(f"{_ATOM}entry"):
            title = _clean(entry.findtext(f"{_ATOM}title"))
            link = entry.find(f"{_ATOM}link[@rel='alternate']") or entry.find(f"{_ATOM}link")
            url = _safe_url(link.get("href", "") if link is not None else "")
            published = _clean(entry.findtext(f"{_ATOM}published") or entry.findtext(f"{_ATOM}updated"))
            if title and url:
                out.append(Headline(title, source, url, published))
    return out


class NewsService:
    def __init__(self, feeds: tuple[str, ...] = DEFAULT_FEEDS, fetch=None) -> None:
        self.feeds = tuple(f for f in feeds if f.startswith("https://")) or DEFAULT_FEEDS
        self._fetch = fetch or self._http_get
        self._cache: tuple[float, list[Headline]] = (0.0, [])
        self._lock = threading.Lock()

    @staticmethod
    def _http_get(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JARVIS desktop assistant)"})
        with urllib.request.urlopen(req, timeout=FEED_TIMEOUT_S) as resp:  # noqa: S310 - https feeds only
            return resp.read(MAX_FEED_BYTES)

    def cached(self) -> list[Headline]:
        return list(self._cache[1])

    def headlines(self, count: int = 5, max_age_s: float = CACHE_TTL_S) -> list[Headline]:
        with self._lock:
            fetched_at, items = self._cache
            if items and time.time() - fetched_at < max_age_s:
                return items[:count]
            errors = []
            for url in self.feeds:
                try:
                    found = parse_feed(self._fetch(url), url)
                except Exception as exc:  # noqa: BLE001 - try the next feed
                    log.warning("News feed %s failed: %s", _feed_name(url), exc)
                    errors.append(str(exc))
                    continue
                if len(found) >= 3:
                    self._cache = (time.time(), found)
                    return found[:count]
            if items:  # stale but better than nothing
                return items[:count]
            raise ActionError("NEWS_UNAVAILABLE", "I couldn't reach any news source right now.")
