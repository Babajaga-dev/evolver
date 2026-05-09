"""Fetcher RSS feeds per news crypto.

Usiamo solo RSS pubblici (no auth) per la slice 3.0a. CryptoPanic API
richiede token e verrà aggiunta in slice successiva.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class RssFeed:
    """Definizione di un feed RSS."""

    source: str  # nome breve (coindesk, theblock, ...)
    url: str
    enabled: bool = True


@dataclass
class RawNewsItem:
    """Una news fetchata, prima del save su DB."""

    source: str  # nome del feed (es. "coindesk")
    external_id: str  # GUID dal feed (univoco per dedup intra-source)
    url: str
    title: str
    body: str | None
    published_at: datetime
    hash: str  # sha256(url+title) per dedup cross-source


# RSS feeds gratuiti — focus su crypto news ad alta qualità
DEFAULT_RSS_FEEDS: list[RssFeed] = [
    RssFeed(source="coindesk", url="https://www.coindesk.com/arc/outboundfeeds/rss/"),
    RssFeed(source="cointelegraph", url="https://cointelegraph.com/rss"),
    RssFeed(source="theblock", url="https://www.theblock.co/rss.xml"),
    RssFeed(source="decrypt", url="https://decrypt.co/feed"),
    RssFeed(source="bitcoinist", url="https://bitcoinist.com/feed/"),
]


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------


async def fetch_rss_feed(
    feed: RssFeed,
    *,
    timeout_s: float = 15.0,
) -> list[RawNewsItem]:
    """Fetch un singolo RSS feed e ritorna lista di news parsate.

    Robust to errors: ritorna lista vuota su qualunque problema (DNS,
    timeout, parse). Logga warning ma non solleva.
    """
    if not feed.enabled:
        return []
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            resp = await client.get(
                feed.url,
                headers={"User-Agent": "Evolver/0.1 (+https://github.com/evolver)"},
            )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning(
            "news.rss.fetch_failed",
            source=feed.source,
            url=feed.url,
            error=str(exc),
        )
        return []

    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        log.warning(
            "news.rss.parse_failed",
            source=feed.source,
            error=str(parsed.bozo_exception) if parsed.bozo_exception else "unknown",
        )
        return []

    items: list[RawNewsItem] = []
    for entry in parsed.entries:
        try:
            item = _entry_to_raw(feed.source, entry)
            if item is not None:
                items.append(item)
        except Exception as exc:  # pragma: no cover
            log.warning(
                "news.rss.entry_skipped",
                source=feed.source,
                error=str(exc),
            )

    log.info("news.rss.fetched", source=feed.source, count=len(items))
    return items


async def fetch_all_rss(
    feeds: list[RssFeed] | None = None,
    *,
    concurrency: int = 5,
) -> list[RawNewsItem]:
    """Fetch tutti i feed in parallelo (limitato a ``concurrency``).

    Returns:
        Lista flat di tutte le news, già deduplicate per (source,
        external_id) intra-source. Cross-source dedup viene fatta dal
        layer ``ingester`` via hash.
    """
    feeds = feeds or DEFAULT_RSS_FEEDS

    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(f: RssFeed) -> list[RawNewsItem]:
        async with semaphore:
            return await fetch_rss_feed(f)

    results = await asyncio.gather(*[_bounded(f) for f in feeds])
    flat: list[RawNewsItem] = []
    for chunk in results:
        flat.extend(chunk)

    # Dedup per (source, external_id) — alcuni feed hanno duplicati interni
    seen: set[tuple[str, str]] = set()
    unique: list[RawNewsItem] = []
    for item in flat:
        key = (item.source, item.external_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    log.info(
        "news.rss.fetched_total",
        feeds=len(feeds),
        raw=len(flat),
        unique=len(unique),
    )
    return unique


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _entry_to_raw(source: str, entry: dict) -> RawNewsItem | None:
    """Mappa entry feedparser → RawNewsItem, oppure None se invalida."""
    url = entry.get("link") or entry.get("id")
    title = entry.get("title")
    if not url or not title:
        return None

    # external_id: usiamo guid se presente, altrimenti l'URL stesso
    external_id = (
        entry.get("id")
        or entry.get("guid")
        or url
    )[:256]  # tronchiamo a 256 (DB constraint)

    # Body può essere in summary, description, content[0].value
    body = entry.get("summary") or entry.get("description")
    if not body and entry.get("content"):
        try:
            body = entry["content"][0].get("value")
        except (IndexError, AttributeError):
            body = None

    # published_at: feedparser lo parsa in published_parsed (struct_time)
    published_at = _parse_published(entry)

    # Hash per dedup cross-source
    hash_input = f"{url}|{title}".encode("utf-8")
    hash_str = hashlib.sha256(hash_input).hexdigest()

    return RawNewsItem(
        source=source,
        external_id=str(external_id),
        url=url,
        title=title.strip()[:1000],  # safety cap
        body=body,
        published_at=published_at,
        hash=hash_str,
    )


def _parse_published(entry: dict) -> datetime:
    """Parse il timestamp dalla entry RSS, fallback a now() UTC."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            # struct_time in UTC
            ts = datetime(*parsed[:6], tzinfo=timezone.utc)
            return ts
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)
