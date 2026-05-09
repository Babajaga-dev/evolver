"""Test smoke per il news pipeline.

Test focus:
    - Modulo si importa
    - RSS feeds dataclasses
    - Scorer JSON parsing & validation (no chiamate Anthropic reali)
    - Routes registered
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def test_news_package_imports() -> None:
    """Il package si importa senza errori."""
    import app.news as news

    assert news.DEFAULT_RSS_FEEDS
    assert news.fetch_all_rss
    assert news.score_news


def test_default_feeds_are_well_formed() -> None:
    from app.news import DEFAULT_RSS_FEEDS

    assert len(DEFAULT_RSS_FEEDS) >= 3
    for feed in DEFAULT_RSS_FEEDS:
        assert feed.source
        assert feed.url.startswith("http")
        assert feed.enabled is True


# ---------------------------------------------------------------------------
# Sources — entry parsing
# ---------------------------------------------------------------------------


def test_entry_to_raw_minimum_fields() -> None:
    """Una entry RSS minimale viene mappata correttamente."""
    from app.news.sources import _entry_to_raw

    entry = {
        "link": "https://example.com/news/1",
        "title": "BTC hits new ATH",
        "summary": "Bitcoin reached a new all-time high today.",
        "id": "guid-001",
        "published_parsed": (2026, 5, 8, 12, 0, 0, 0, 0, 0),
    }
    item = _entry_to_raw("test_source", entry)
    assert item is not None
    assert item.source == "test_source"
    assert item.url == "https://example.com/news/1"
    assert item.title == "BTC hits new ATH"
    assert item.body and "all-time high" in item.body
    assert item.external_id == "guid-001"
    assert isinstance(item.published_at, datetime)
    assert item.published_at.tzinfo is timezone.utc
    assert len(item.hash) == 64  # sha256 hex


def test_entry_to_raw_skips_invalid() -> None:
    """Entry senza title o link → None."""
    from app.news.sources import _entry_to_raw

    assert _entry_to_raw("x", {"title": "no link"}) is None
    assert _entry_to_raw("x", {"link": "https://x"}) is None


def test_entry_hash_is_deterministic() -> None:
    """Stesso URL+title → stesso hash (per cross-source dedup)."""
    from app.news.sources import _entry_to_raw

    entry = {
        "link": "https://example.com/foo",
        "title": "Hello",
        "id": "g1",
    }
    a = _entry_to_raw("src1", entry)
    b = _entry_to_raw("src2", entry)
    assert a is not None and b is not None
    assert a.hash == b.hash


# ---------------------------------------------------------------------------
# Scorer — JSON validation (no API call)
# ---------------------------------------------------------------------------


def test_scorer_validate_normalizes_known_assets() -> None:
    from app.news.scorer import _validate_and_normalize

    parsed = {
        "assets_mentioned": ["bitcoin", "BTC", "ETH", "FAKE_TOKEN"],
        "event_type": "regulation",
        "factual_impact": 0.8,
        "sentiment_score": -0.3,
        "confidence": 0.9,
        "ttl_hours": 48,
        "reasoning": "SEC filed lawsuit",
    }
    res = _validate_and_normalize(parsed, model="claude-haiku-test")
    # bitcoin non è canonical, FAKE_TOKEN sconosciuto → entrambi filtrati
    assert res.assets_mentioned == ["BTC", "ETH"]
    assert res.event_type == "regulation"
    assert res.factual_impact == 0.8
    assert res.sentiment_score == -0.3
    assert res.confidence == 0.9
    assert res.ttl_hours == 48


def test_scorer_clamps_out_of_range() -> None:
    from app.news.scorer import _validate_and_normalize

    parsed = {
        "assets_mentioned": ["BTC"],
        "event_type": "unknown_type",  # → "other"
        "factual_impact": 5.0,  # → 1.0
        "sentiment_score": -3.0,  # → -1.0
        "confidence": 2.0,  # → 1.0
        "ttl_hours": 9999,  # → 168
    }
    res = _validate_and_normalize(parsed, model="m")
    assert res.event_type == "other"
    assert res.factual_impact == 1.0
    assert res.sentiment_score == -1.0
    assert res.confidence == 1.0
    assert res.ttl_hours == 168


def test_scorer_strip_json_fences() -> None:
    """Claude a volte risponde con ```json ... ``` — il parser deve gestirlo."""
    from app.news.scorer import _strip_json_fences

    text = '```json\n{"foo": 1}\n```'
    assert _strip_json_fences(text).strip() == '{"foo": 1}'

    text2 = '{"foo": 1}'  # senza fence
    assert _strip_json_fences(text2) == '{"foo": 1}'


def test_scorer_strip_html() -> None:
    from app.news.scorer import _strip_html

    html = "<p>Hello <b>world</b></p>"
    assert _strip_html(html) == "Hello world"


def test_scorer_invalid_payload_raises() -> None:
    from app.news.scorer import ScoringError, _validate_and_normalize

    with pytest.raises(ScoringError):
        # assets_mentioned non è list
        _validate_and_normalize(
            {"assets_mentioned": "BTC", "event_type": "x"},
            model="m",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_news_routes_registered() -> None:
    """Tutti gli endpoint /api/v1/news/* sono registrati nell'app FastAPI."""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    expected = {
        "/api/v1/news",
        "/api/v1/news/stats",
        "/api/v1/news/refresh",
        "/api/v1/news/score",
    }
    missing = expected - paths
    assert not missing, f"Endpoint mancanti: {missing}. Tutti i path: {paths}"
