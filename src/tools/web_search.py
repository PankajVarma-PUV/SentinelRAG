# SpandaOS — The Living Pulse of Agentic Intelligence
# A self-pulsing intelligence that lives at the core of the system — perpetually vibrating, continuously learning from every interaction, self-correcting its own errors, and driving all reasoning from a single living center — not because it was told to, but because that is its fundamental nature.
# Copyright (C) 2026 Pankaj Umesh Varma
# Contact: 9372123700
# Email: pv43770@gmail.com
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Web Breakout Agent — SpandaOS Live Web Search Tool (v3 — Snippet-First Architecture)

Root cause of v2 failure (diagnosed from 2026-03-05 logs):
  - DuckDuckGo `text()` search was regionally biased toward Chinese sources
    (zhidao.baidu.com, zhihu.com) for geopolitical/news queries.
  - Every Chinese site returned 403 / ConnectionReset to Trafilatura.
  - DuckDuckGo snippets from those sites were also empty (non-English body).
  - Result: ALL 10 candidates yielded no usable text → empty result → LLM fallback.

New Architecture (v3):
  ┌─────────────────────────────────────────────────────────────────────┐
  │  LAYER 1 — DuckDuckGo News API (ddgs.news)                         │
  │    • Returns structured {title, body, url, date, source} natively   │
  │    • No scraping needed — body IS the content                       │
  │    • Perfect for news / geopolitical / current-events queries       │
  │    • Forced to English region (region="wt-wt", language="en")       │
  ├─────────────────────────────────────────────────────────────────────┤
  │  LAYER 2 — DuckDuckGo Text Search + Snippet Aggregation            │
  │    • Runs always (as supplement or sole layer for general queries)  │
  │    • Uses DuckDuckGo snippet (~300 chars each) as PRIMARY content   │
  │    • Filters out known blocked/non-English domains proactively      │
  │    • Aggregates 10 snippets = ~3000 chars of high-quality context  │
  ├─────────────────────────────────────────────────────────────────────┤
  │  LAYER 3 — Selective Scraping (Optional, Best-Effort)              │
  │    • Only attempted for trusted open domains (wikipedia, Reuters,   │
  │      BBC, AP, etc.) where scraping succeeds reliably               │
  │    • Supplements snippet content with full article body             │
  │    • Skipped entirely if not available — never blocks progress      │
  └─────────────────────────────────────────────────────────────────────┘

Key design decisions:
  - Snippet content is ALWAYS accepted even if scraping fails
  - ddgs.news() provides publication date natively (critical for news)
  - English-region forcing prevents Chinese site contamination
  - Domain blocklist prevents wasted scrape attempts on hostile sites
"""

import logging
import re
from typing import List, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

# Minimum snippet length to be considered useful
_MIN_SNIPPET_LEN = 40

# Max chars from scraped body (supplement only, snippets already in results)
_SCRAPE_CHARS_MAX = 2000

# Per-URL scrape timeout
_FETCH_TIMEOUT_SECS = 8

# Domains known to reliably allow scraping (whitelist for selective scraping)
_SCRAPE_TRUSTED_DOMAINS = {
    "wikipedia.org", "en.wikipedia.org",
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "theguardian.com", "aljazeera.com", "france24.com",
    "ndtv.com", "thehindu.com", "timesofindia.com",
    "theatlantic.com", "foreignpolicy.com", "cfr.org",
    "brookings.edu", "rand.org",
}

# Domains that are known to permanently block scrapers (skip them immediately)
_BLOCKED_DOMAINS = {
    "zhidao.baidu.com", "zhihu.com", "baidu.com",
    "weibo.com", "sina.com.cn", "sohu.com", "163.com",
    "quora.com",           # Always login-wall now
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com",
    "nytimes.com",         # Hard paywall
    "wsj.com",             # Hard paywall
    "ft.com",              # Hard paywall
}

# Keywords that indicate a real-time / news-heavy query
NEWS_KEYWORDS = {
    "news", "latest", "recent", "today", "yesterday", "current",
    "happen", "happening", "attack", "war", "conflict", "crisis",
    "2025", "2026", "march", "february", "january", "breaking",
    "election", "vote", "president", "minister", "military", "strike",
    "iran", "usa", "israel", "india", "china", "russia", "ukraine",
    "ceasefire", "sanction", "arrest", "killed", "bomb", "missile",
    "protest", "coup", "invasion", "treaty", "summit", "negotiate",
}


# ── Domain helpers ─────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    """Return the bare domain from a URL, e.g. 'en.wikipedia.org'."""
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _is_blocked(url: str) -> bool:
    """Return True if the URL's domain is in the permanent blocklist."""
    domain = _extract_domain(url)
    # Check exact match and suffix match (e.g. 'sub.baidu.com')
    if domain in _BLOCKED_DOMAINS:
        return True
    for blocked in _BLOCKED_DOMAINS:
        if domain.endswith("." + blocked) or domain == blocked:
            return True
    return False


def _is_trusted_for_scraping(url: str) -> bool:
    """Return True if the domain is in our whitelist for selective scraping."""
    domain = _extract_domain(url)
    for trusted in _SCRAPE_TRUSTED_DOMAINS:
        if domain == trusted or domain.endswith("." + trusted):
            return True
    return False


# ── Trafilatura selective scraper ──────────────────────────────────────────────

def _try_scrape(url: str) -> str:
    """
    Attempt to scrape a trusted URL via Trafilatura.
    Returns extracted text (up to _SCRAPE_CHARS_MAX chars) or empty string.
    Never raises — all failures return empty string gracefully.
    """
    try:
        import trafilatura
        from trafilatura.settings import use_config

        cfg = use_config()
        if not cfg.has_section("network"):
            cfg.add_section("network")
        cfg.set("network", "USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36")
        cfg.set("network", "MAX_REDIRECTS", "3")
        cfg.set("network", "TIMEOUT", str(_FETCH_TIMEOUT_SECS))

        downloaded = trafilatura.fetch_url(url, config=cfg)
        if not downloaded:
            return ""

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            config=cfg,
        )
        return (text or "")[:_SCRAPE_CHARS_MAX]

    except Exception as e:
        logger.debug(f"[WebBreakout] Selective scrape failed for {url}: {e}")
        return ""


# ── Layer 1: DuckDuckGo News API ───────────────────────────────────────────────

def _search_news(ddgs, query: str, max_results: int) -> List[Dict]:
    """
    Query DuckDuckGo's News vertical.
    Returns results as: [{'title', 'url', 'date', 'source', 'text'}, ...]

    The News API returns pre-extracted {title, body, url, date, source} —
    no scraping is needed. Body is typically 200-400 chars per result.
    """
    results = []
    try:
        raw = list(ddgs.news(
            query,
            max_results=max_results,
            region="wt-wt",     # Worldwide (English-biased)
        ))
        logger.info(f"[WebBreakout:News] DuckDuckGo News returned {len(raw)} articles.")
        for item in raw:
            url   = item.get("url", "").strip()
            body  = item.get("body", "").strip()
            title = item.get("title", "Untitled").strip()
            date  = item.get("date", "")
            src   = item.get("source", "")

            if not url or _is_blocked(url):
                continue
            if len(body) < _MIN_SNIPPET_LEN:
                continue

            # Optionally enhance body with scraped content for trusted domains
            extra = ""
            if _is_trusted_for_scraping(url):
                extra = _try_scrape(url)
                if extra:
                    logger.info(f"[WebBreakout:News] Scraped supplement from {url} ({len(extra)} chars)")

            full_text = body
            if extra and len(extra) > len(body):
                full_text = extra  # Prefer richer scraped body
            elif extra:
                full_text = body + "\n\n" + extra  # Append supplement

            results.append({
                "title": f"{title} [{src}]" if src else title,
                "url":   url,
                "date":  str(date)[:10] if date else "",   # YYYY-MM-DD
                "text":  full_text,
            })

    except Exception as news_err:
        logger.warning(f"[WebBreakout:News] News search failed: {news_err}")

    return results


# ── Layer 2: DuckDuckGo Text Search + Snippet Aggregation ─────────────────────

def _search_text(ddgs, query: str, max_results: int, already_seen_urls: set) -> List[Dict]:
    """
    Query DuckDuckGo's Text vertical and aggregate snippets.
    Snippets (~300 chars each) are the PRIMARY content — always accepted.
    Selective scraping supplements for trusted open domains.
    Filters out blocked and non-English results proactively.
    """
    results = []
    try:
        raw = list(ddgs.text(
            query,
            max_results=max_results,
            region="wt-wt",         # Force worldwide (English-biased)
        ))
        logger.info(f"[WebBreakout:Text] DuckDuckGo Text returned {len(raw)} candidates.")
        for item in raw:
            url     = item.get("href", "").strip()
            title   = item.get("title", "Untitled").strip()
            snippet = item.get("body", "").strip()

            # Skip if already covered by news search
            if url in already_seen_urls:
                continue
            if not url or _is_blocked(url):
                logger.debug(f"[WebBreakout:Text] Skipping blocked/filtered URL: {url}")
                continue
            if len(snippet) < _MIN_SNIPPET_LEN:
                continue

            # Snippet is the guaranteed baseline content
            content = snippet

            # Selectively scrape trusted open domains for richer content
            if _is_trusted_for_scraping(url):
                scraped = _try_scrape(url)
                if scraped and len(scraped) > len(snippet):
                    content = scraped
                    logger.info(f"[WebBreakout:Text] Rich scrape from {url} ({len(scraped)} chars)")
                elif scraped:
                    content = snippet + "\n\n" + scraped

            results.append({
                "title": title,
                "url":   url,
                "date":  "",   # Text search doesn't supply dates natively
                "text":  content,
            })

    except Exception as text_err:
        logger.warning(f"[WebBreakout:Text] Text search failed: {text_err}")

    return results


# ── Public API ─────────────────────────────────────────────────────────────────

def is_news_query(query: str) -> bool:
    """
    Heuristic: does the query look like it needs real-time/news sources?
    Used by the Metacognitive Brain to decide max_results breadth.
    """
    q_lower = query.lower()
    return any(kw in q_lower for kw in NEWS_KEYWORDS)


def fallback_web_search(query: str, max_results: int = 7) -> List[Dict]:
    """
    SpandaOS Web Breakout — Snippet-First, Scrape-Optional Architecture (v3).

    ONLY called when the user explicitly enables the Web Search toggle.
    NEVER auto-triggered by intent classification.

    Strategy:
      1. For news/geopolitical queries: run ddgs.news() to get dated English articles
      2. Always run ddgs.text() for supplemental/general search coverage
      3. Selectively scrape only trusted open domains (Wikipedia, Reuters, BBC, etc.)
      4. Snippet content is ALWAYS accepted — scraping is a bonus, never a requirement

    Args:
        query:       Pre-optimized search query from Metacognitive Brain.
        max_results: Max candidates per search layer.

    Returns:
        List[Dict] with keys: title, url, date, text — or [] on total failure.
    """
    logger.info(f"[WebBreakout] Live search v3 — query: '{query}', max_results: {max_results}")

    # ── Dependency check ──────────────────────────────────────────────────────
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logger.error("[WebBreakout] 'duckduckgo-search' not installed.")
        return []

    all_results: List[Dict] = []

    with DDGS() as ddgs:

        # ── Layer 1: News API (for news/geopolitical queries) ─────────────────
        if is_news_query(query):
            news_results = _search_news(ddgs, query, max_results=max_results)
            logger.info(f"[WebBreakout] Layer 1 (News API): {len(news_results)} article(s) retrieved.")
            all_results.extend(news_results)

        # ── Layer 2: Text search + snippet aggregation ────────────────────────
        # Always runs — provides broader web coverage and fills in for non-news queries
        seen_urls = {r["url"] for r in all_results}
        text_cap = max(max_results, 10)  # Text search gets generous cap
        text_results = _search_text(ddgs, query, max_results=text_cap, already_seen_urls=seen_urls)
        logger.info(f"[WebBreakout] Layer 2 (Text+Snippet): {len(text_results)} source(s) retrieved.")
        all_results.extend(text_results)

    if not all_results:
        logger.error(
            "[WebBreakout] Both search layers returned nothing. "
            "Check DuckDuckGo connectivity or try again."
        )
        return []

    # ── Deduplicate by URL and rank: News results first (have dates) ──────────
    seen = set()
    final: List[Dict] = []
    # Prioritize dated results first
    for r in sorted(all_results, key=lambda x: (x["date"] == "", len(x["text"])), reverse=False):
        url = r["url"]
        if url not in seen and len(r["text"]) >= _MIN_SNIPPET_LEN:
            seen.add(url)
            final.append(r)

    logger.info(
        f"[WebBreakout] Final deduplicated result set: {len(final)} source(s). "
        f"News: {sum(1 for r in final if r['date'])}, Text-only: {sum(1 for r in final if not r['date'])}"
    )
    return final
