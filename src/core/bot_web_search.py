"""
bot_web_search.py — Web search provider for KB autoresearch fallback (§23.4).

Implements a pluggable web search that augments the local KB when retrieval
confidence is below KB_WEB_SEARCH_THRESHOLD.

Providers (tried in order):
  1. Google Custom Search JSON API  — requires GOOGLE_CSE_ID + GOOGLE_API_KEY
  2. SearXNG self-hosted instance   — requires SEARXNG_URL
  3. DuckDuckGo Instant Answers API — free, no key, limited results

Public API:
    search_web(query, num_results, timeout) → list[{title, snippet, url}]

Returns an empty list on any error or when no provider is configured.
Callers (bot_remote_kb._do_search) guard with KB_WEB_SEARCH_ENABLED.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

# ─── Provider implementations ────────────────────────────────────────────────


def _search_google(query: str, cse_id: str, api_key: str,
                   num: int, timeout: int) -> list[dict[str, str]]:
    """Google Custom Search JSON API — 100 free queries/day."""
    params = urllib.parse.urlencode({
        "q": query,
        "key": api_key,
        "cx": cse_id,
        "num": min(num, 10),
    })
    url = f"https://www.googleapis.com/customsearch/v1?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "taris-kb/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data: dict[str, Any] = json.loads(resp.read().decode())
        items = data.get("items") or []
        results = [
            {
                "title":   item.get("title", ""),
                "snippet": item.get("snippet", "").replace("\n", " "),
                "url":     item.get("link", ""),
            }
            for item in items
        ]
        log.info("[web_search] Google CSE: %d results for %r", len(results), query[:50])
        return results
    except Exception as exc:
        log.warning("[web_search] Google CSE failed: %s", exc)
        return []


def _search_searxng(query: str, base_url: str,
                    num: int, timeout: int) -> list[dict[str, str]]:
    """SearXNG self-hosted instance — vendor-neutral, no API key."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "language": "ru-RU",
    })
    url = base_url.rstrip("/") + f"/search?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "taris-kb/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data: dict[str, Any] = json.loads(resp.read().decode())
        results = [
            {
                "title":   r.get("title", ""),
                "snippet": r.get("content", "").replace("\n", " "),
                "url":     r.get("url", ""),
            }
            for r in (data.get("results") or [])[:num]
        ]
        log.info("[web_search] SearXNG: %d results for %r", len(results), query[:50])
        return results
    except Exception as exc:
        log.warning("[web_search] SearXNG failed (%s): %s", base_url, exc)
        return []


def _search_duckduckgo(query: str,
                       num: int, timeout: int) -> list[dict[str, str]]:
    """DuckDuckGo Instant Answer API — free, no key, limited depth."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1,
    })
    url = f"https://api.duckduckgo.com/?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "taris-kb/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data: dict[str, Any] = json.loads(resp.read().decode())
        results: list[dict[str, str]] = []
        # Abstract result
        if data.get("AbstractText"):
            results.append({
                "title":   data.get("Heading", ""),
                "snippet": data["AbstractText"],
                "url":     data.get("AbstractURL", ""),
            })
        # Related topics
        for topic in (data.get("RelatedTopics") or [])[:num]:
            text = topic.get("Text", "")
            url_ = topic.get("FirstURL", "")
            if text:
                results.append({"title": "", "snippet": text, "url": url_})
            if len(results) >= num:
                break
        log.info("[web_search] DDG: %d results for %r", len(results), query[:50])
        return results
    except Exception as exc:
        log.warning("[web_search] DuckDuckGo failed: %s", exc)
        return []


# ─── Public API ───────────────────────────────────────────────────────────────

def search_web(
    query: str,
    num_results: int = 5,
    timeout: int = 10,
) -> list[dict[str, str]]:
    """Search the web using the configured provider.

    Provider priority:
      1. Google Custom Search (GOOGLE_CSE_ID + GOOGLE_API_KEY set)
      2. SearXNG self-hosted  (SEARXNG_URL set)
      3. DuckDuckGo Instant   (free fallback, limited)

    Returns a list of result dicts: [{title, snippet, url}, ...].
    Returns [] silently when no provider is configured or on any error.
    """
    from core.bot_config import GOOGLE_CSE_ID, GOOGLE_API_KEY, SEARXNG_URL

    if GOOGLE_CSE_ID and GOOGLE_API_KEY:
        results = _search_google(query, GOOGLE_CSE_ID, GOOGLE_API_KEY, num_results, timeout)
        if results:
            return results

    if SEARXNG_URL:
        results = _search_searxng(query, SEARXNG_URL, num_results, timeout)
        if results:
            return results

    # DuckDuckGo as last-resort free fallback
    return _search_duckduckgo(query, num_results, timeout)
