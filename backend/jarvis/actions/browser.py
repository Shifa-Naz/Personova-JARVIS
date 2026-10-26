"""Browser actions: navigation and search by URL (no keystroke injection)."""

from __future__ import annotations

import logging
import re
import urllib.request
from urllib.parse import quote_plus, urlparse

from pydantic import Field, field_validator

from jarvis.actions.base import ActionError, ActionResult, ActionSpec, Offer, Params, PermissionLevel, PlanStep

log = logging.getLogger(__name__)

KNOWN_SITES = {
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "linkedin": "https://www.linkedin.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "wikipedia": "https://www.wikipedia.org",
    "reddit": "https://www.reddit.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "chatgpt": "https://chatgpt.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.in",
    "whatsapp": "https://web.whatsapp.com",
    "leetcode": "https://leetcode.com",
}
SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={}",
    "duckduckgo": "https://duckduckgo.com/?q={}",
    "bing": "https://www.bing.com/search?q={}",
}
_VIDEO_ID = re.compile(r'"videoId":"([\w-]{11})"')


def _browser(ctx, name: str | None):
    if not name:
        return None
    app = ctx.apps.resolve(name)
    if app is None or not app.is_browser:
        raise ActionError("APP_NOT_REGISTERED", f"{name} isn't a browser I know.")
    return app


class UrlParams(Params):
    url: str = Field(min_length=4, max_length=2000)
    browser: str | None = Field(default=None, max_length=40, description="Optional browser: chrome, firefox, edge")

    @field_validator("url")
    @classmethod
    def http_only(cls, value: str) -> str:
        scheme = re.match(r"^([a-z][a-z0-9+.-]*):(?!\d)", value, re.IGNORECASE)
        if scheme and scheme.group(1).lower() not in ("http", "https"):
            raise ValueError("only http(s) URLs are allowed")
        if "://" not in value:
            value = "https://" + value
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("only http(s) URLs are allowed")
        return value


def open_url(params: UrlParams, ctx, prepared) -> ActionResult:
    ctx.platform.open_url(params.url, _browser(ctx, params.browser))
    host = urlparse(params.url).netloc.removeprefix("www.")
    return ActionResult(True, f"Opening {host}.", data={"url": params.url})


class SearchParams(Params):
    query: str = Field(min_length=1, max_length=300)
    engine: str = Field(default="google", pattern="^(google|duckduckgo|bing)$")
    browser: str | None = Field(default=None, max_length=40)


def search_web(params: SearchParams, ctx, prepared) -> ActionResult:
    url = SEARCH_ENGINES[params.engine].format(quote_plus(params.query))
    ctx.platform.open_url(url, _browser(ctx, params.browser))
    ctx.session.last_search_query = params.query
    ctx.session.last_search_kind = "web"
    return ActionResult(True, f"Searching the web for {params.query}.", data={"url": url})


class YoutubeParams(Params):
    query: str = Field(min_length=1, max_length=300)
    browser: str | None = Field(default=None, max_length=40)


def search_youtube(params: YoutubeParams, ctx, prepared) -> ActionResult:
    url = f"https://www.youtube.com/results?search_query={quote_plus(params.query)}"
    ctx.platform.open_url(url, _browser(ctx, params.browser))
    ctx.session.last_search_query = params.query
    ctx.session.last_search_kind = "youtube"
    ctx.session.last_media_query = params.query
    return ActionResult(
        True,
        f"Here are YouTube results for {params.query}.",
        data={"url": url},
        offer=Offer(
            "Would you like me to play the first one?",
            [PlanStep(action="play_youtube", params={"query": params.query, "browser": params.browser})],
        ),
    )


def first_youtube_video(query: str, timeout: float = 8.0) -> str | None:
    """Return the first video id from YouTube's results page, or None."""
    req = urllib.request.Request(
        f"https://www.youtube.com/results?search_query={quote_plus(query)}",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
            html = resp.read(2_000_000).decode("utf-8", errors="replace")
    except OSError as exc:
        log.warning("YouTube lookup failed: %s", exc)
        return None
    match = _VIDEO_ID.search(html)
    return match.group(1) if match else None


def play_youtube(params: YoutubeParams, ctx, prepared) -> ActionResult:
    browser = _browser(ctx, params.browser)
    video = first_youtube_video(params.query)
    ctx.session.last_media_query = params.query
    if video is None:
        url = f"https://www.youtube.com/results?search_query={quote_plus(params.query)}"
        ctx.platform.open_url(url, browser)
        return ActionResult(
            True,
            f"I couldn't pick a video automatically, so I opened the results for {params.query}.",
            data={"url": url},
        )
    url = f"https://www.youtube.com/watch?v={video}"
    ctx.platform.open_url(url, browser)
    return ActionResult(True, f"Playing {params.query} on YouTube.", data={"url": url})


SPECS = [
    ActionSpec(
        "open_url",
        "Open a website (http/https only), optionally in a specific browser.",
        UrlParams,
        PermissionLevel.SAFE,
        open_url,
        online=True,
        examples=("open github", "go to youtube.com"),
    ),
    ActionSpec(
        "search_web",
        "Search the web and show results in the browser. Use for real-time information.",
        SearchParams,
        PermissionLevel.SAFE,
        search_web,
        online=True,
        examples=("search google for react hooks",),
    ),
    ActionSpec(
        "search_youtube",
        "Show YouTube search results.",
        YoutubeParams,
        PermissionLevel.SAFE,
        search_youtube,
        online=True,
        examples=("search youtube for imagine dragons",),
    ),
    ActionSpec(
        "play_youtube",
        "Play the top YouTube result for a query.",
        YoutubeParams,
        PermissionLevel.SAFE,
        play_youtube,
        online=True,
        timeout_s=20,
        examples=("play believer on youtube",),
    ),
]
