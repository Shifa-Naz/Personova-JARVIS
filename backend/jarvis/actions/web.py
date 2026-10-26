"""Current-information retrieval, separate from the conversation model.

``web_answer`` fetches search results (DuckDuckGo's HTML endpoint, no API key), then the
local model summarizes them with sources. Retrieved text is treated as data: it is
quoted to the model as search results, never executed or turned into actions.
"""

from __future__ import annotations

import html
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from pydantic import Field

from jarvis.actions.base import ActionError, ActionResult, ActionSpec, Offer, Params, PermissionLevel, PlanStep
from jarvis.ai.provider import AiUnavailable

log = logging.getLogger(__name__)

SEARCH_URL = "https://html.duckduckgo.com/html/?q={}"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
_TITLE = re.compile(r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.DOTALL)
_SNIPPET = re.compile(r'class="result__snippet"[^>]*>(?P<snippet>.*?)</(?:a|td|div)>', re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


def _clean(fragment: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub("", fragment or ""))).strip()


def _real_url(href: str) -> str | None:
    href = html.unescape(href)
    for _ in range(2):  # results are wrapped in a duckduckgo.com/l/?uddg=<target> redirect
        if href.startswith("//"):
            href = "https:" + href
        parsed = urllib.parse.urlparse(href)
        if not parsed.netloc.endswith("duckduckgo.com"):
            break
        if "/y.js" in parsed.path or "ad_domain" in parsed.query:  # sponsored result
            return None
        href = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
    return href if href.startswith(("http://", "https://")) else None


def parse_results(page: str, limit: int = 5) -> list[SearchResult]:
    results: list[SearchResult] = []
    anchors = list(_TITLE.finditer(page))
    for i, m in enumerate(anchors):
        url = _real_url(m.group("href"))
        title = _clean(m.group("title"))
        if not url or not title or any(r.url == url for r in results):
            continue
        block_end = anchors[i + 1].start() if i + 1 < len(anchors) else len(page)
        snip = _SNIPPET.search(page, m.end(), block_end)
        results.append(SearchResult(title, url, _clean(snip.group("snippet")) if snip else ""))
        if len(results) >= limit:
            break
    return results


def search(query: str, limit: int = 5, timeout: float = 10.0) -> list[SearchResult]:
    req = urllib.request.Request(
        SEARCH_URL.format(urllib.parse.quote_plus(query)),
        headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
            page = resp.read(1_500_000).decode("utf-8", errors="replace")
    except OSError as exc:
        log.warning("Web search failed: %s", exc)
        raise ActionError("SEARCH_FAILED", "I couldn't reach the search service.") from exc
    return parse_results(page, limit)


class WebParams(Params):
    query: str = Field(min_length=2, max_length=300)


def web_answer(params: WebParams, ctx, prepared) -> ActionResult:
    ctx.session.last_search_query = params.query
    ctx.session.last_search_kind = "web"
    results = search(params.query)
    if not results:
        return ActionResult.fail(
            "NO_RESULTS",
            "I couldn't find anything useful for that.",
            offer=Offer(
                "Shall I open a web search instead?", [PlanStep(action="search_web", params={"query": params.query})]
            ),
        )
    data = {"results": [r.to_dict() for r in results]}
    sources = "\n".join(f"- [{r.title}]({r.url})" for r in results[:3])
    try:
        answer = ctx.ai.answer_from_sources(params.query, [r.to_dict() for r in results])
        data["source"] = "llm"
    except AiUnavailable:
        top = results[0]
        answer = f"According to {top.title}: {top.snippet}" if top.snippet else f"The top result is {top.title}."
        data["source"] = "snippet"
    data["speech"] = answer
    return ActionResult(True, f"{answer}\n\n**Sources**\n{sources}", data=data)


def open_first_result(params: WebParams, ctx, prepared) -> ActionResult:
    results = search(params.query, limit=1)
    if not results:
        return ActionResult.fail("NO_RESULTS", f"I couldn't find a result for {params.query}.")
    top = results[0]
    ctx.platform.open_url(top.url, None)
    host = urllib.parse.urlparse(top.url).netloc.removeprefix("www.")
    return ActionResult(
        True, f"Opening the first result: {top.title}, on {host}.", data={"url": top.url, "title": top.title}
    )


SPECS = [
    ActionSpec(
        "web_answer",
        "Look up current or factual information on the web and answer with sources.",
        WebParams,
        PermissionLevel.READ_ONLY,
        web_answer,
        online=True,
        timeout_s=120,
        examples=("what's the weather in Belgaum today", "who won the match yesterday"),
    ),
    ActionSpec(
        "open_first_result",
        "Search the web and open the first result in the browser.",
        WebParams,
        PermissionLevel.SAFE,
        open_first_result,
        online=True,
        timeout_s=20,
        examples=("search python tutorials and open the first result",),
    ),
]
