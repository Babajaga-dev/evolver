"""News pipeline — ingest da RSS + Claude Haiku scoring.

Pipeline:
    sources.py     fetch RSS feeds (CoinDesk, The Block, Decrypt, ecc.)
    ingester.py    dedup + bulk insert su news_raw
    scorer.py      Claude Haiku → ScoringResult (assets, event_type, sentiment, ...)
    repository.py  query helpers per news_raw / news_scored
    pipeline.py    orchestratore fetch+ingest+score (per scheduler/endpoint)
"""

from app.news.ingester import fetch_and_ingest, ingest_news
from app.news.pipeline import score_pending_news
from app.news.repository import (
    get_news_stats,
    get_unscored_news,
    list_recent_news,
    save_score,
)
from app.news.scorer import ScoringError, ScoringResult, score_news
from app.news.sources import (
    DEFAULT_RSS_FEEDS,
    RawNewsItem,
    fetch_all_rss,
    fetch_rss_feed,
)

__all__ = [
    "DEFAULT_RSS_FEEDS",
    "RawNewsItem",
    "ScoringError",
    "ScoringResult",
    "fetch_all_rss",
    "fetch_and_ingest",
    "fetch_rss_feed",
    "get_news_stats",
    "get_unscored_news",
    "ingest_news",
    "list_recent_news",
    "save_score",
    "score_news",
    "score_pending_news",
]
