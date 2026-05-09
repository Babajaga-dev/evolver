"""Claude Haiku scorer per news crypto.

Input: NewsRaw row (title + body + url)
Output: NewsScored row con campi strutturati:
    - assets_mentioned: list[str] (es. ["BTC", "ETH", "SOL"])
    - event_type: str (hack | regulation | partnership | adoption |
                       technology | opinion | market | macro | other)
    - factual_impact: float in [-1, 1] — quanto la notizia è
                       fattuale/oggettiva vs speculativa
    - sentiment_score: float in [-1, 1] — bullish vs bearish per le
                       crypto menzionate
    - confidence: float in [0, 1] — confidenza del modello
    - ttl_hours: int — quanto la notizia resta rilevante
    - reasoning: str | None — breve spiegazione del modello

Usiamo ``response_format`` JSON per output deterministico parseabile.

Costo stimato: ~$0.00025/news con Haiku 4.5 → ~$3/mese a 400 news/giorno.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from anthropic.types import Message

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


# Set di asset noti — l'LLM è istruito a mappare a questi simboli canonici
KNOWN_ASSETS = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT",
    "MATIC", "LINK", "UNI", "LTC", "ATOM", "NEAR", "APT", "ARB", "OP",
    "PEPE", "SHIB", "TRX", "TON", "SUI", "INJ", "FIL", "ICP", "STX",
    "USDT", "USDC", "DAI",
}

EVENT_TYPES = {
    "hack",
    "regulation",
    "partnership",
    "adoption",
    "technology",
    "opinion",
    "market",
    "macro",
    "other",
}


SYSTEM_PROMPT = """You are a crypto news classifier for a trading system.
Analyze the news and return ONLY a JSON object with these EXACT fields:

{
  "assets_mentioned": ["BTC", "ETH", ...],   // canonical tickers, max 8
  "event_type": "hack|regulation|partnership|adoption|technology|opinion|market|macro|other",
  "factual_impact": 0.0,                      // -1..1, how factual/concrete vs speculative
  "sentiment_score": 0.0,                     // -1..1, bullish (+) vs bearish (-) for mentioned assets
  "confidence": 0.0,                          // 0..1, your confidence
  "ttl_hours": 24,                            // 1..168, how long this stays relevant
  "reasoning": "one sentence"                 // brief justification, max 140 chars
}

Rules:
- assets_mentioned: ONLY canonical tickers (BTC not Bitcoin). Empty list if none.
- event_type: pick the SINGLE best match.
- factual_impact > 0.5 → confirmed event with verifiable details.
- factual_impact < 0   → opinion / speculation / rumor.
- sentiment_score: from the perspective of long holders of mentioned assets.
- ttl_hours: 1-6 for intraday noise, 24-72 for normal news, 168 for major macro/regulation.
- Output ONLY the JSON. No markdown, no preamble, no explanation."""


@dataclass
class ScoringResult:
    """Output strutturato dello scorer Claude."""

    assets_mentioned: list[str]
    event_type: str
    factual_impact: float
    sentiment_score: float
    confidence: float
    ttl_hours: int
    reasoning: str | None
    model: str
    raw_response: dict  # full Claude response per audit/debug


class ScoringError(Exception):
    """Sollevato quando lo scorer fallisce in modo non recuperabile."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def score_news(
    *,
    title: str,
    body: str | None,
    url: str | None = None,
    client: AsyncAnthropic | None = None,
) -> ScoringResult:
    """Scora una singola news via Claude Haiku.

    Args:
        title: titolo news.
        body: corpo (può essere None o HTML — passiamo i primi 2000 char).
        url: opzionale, solo per debug log.
        client: client Anthropic riusabile. Se None ne creiamo uno.

    Raises:
        ScoringError: se il modello fallisce o l'output non è parseabile.
    """
    settings = get_settings()
    cli = client or AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.claude_timeout_s,
        max_retries=settings.claude_max_retries,
    )

    user_content = _build_user_content(title=title, body=body)

    try:
        msg: Message = await cli.messages.create(
            model=settings.claude_model_haiku,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:  # anthropic.APIError, network, ecc.
        log.warning(
            "news.scorer.api_failed",
            url=url,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise ScoringError(f"Anthropic API failed: {exc}") from exc

    # Estrai il testo dalla risposta
    text = _extract_text(msg)
    if not text:
        raise ScoringError("empty response from Claude")

    # Parse JSON
    try:
        parsed = json.loads(_strip_json_fences(text))
    except json.JSONDecodeError as exc:
        log.warning(
            "news.scorer.parse_failed",
            url=url,
            text=text[:200],
            error=str(exc),
        )
        raise ScoringError(f"invalid JSON from Claude: {text[:120]!r}") from exc

    # Valida e normalizza
    result = _validate_and_normalize(parsed, model=settings.claude_model_haiku)

    log.info(
        "news.scorer.scored",
        url=url,
        event_type=result.event_type,
        assets=result.assets_mentioned,
        sentiment=result.sentiment_score,
        confidence=result.confidence,
    )
    return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_user_content(*, title: str, body: str | None) -> str:
    """Compone il prompt utente. Tronchiamo il body per controllare i token."""
    parts = [f"TITLE: {title.strip()}"]
    if body:
        # Strip HTML markup primitivamente per ridurre token
        clean_body = _strip_html(body)[:2000]
        if clean_body:
            parts.append(f"BODY: {clean_body}")
    return "\n\n".join(parts)


def _strip_html(text: str) -> str:
    """Rimuove tag HTML in modo primitivo. Per dedup/scoring va bene."""
    import re

    no_tags = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", no_tags).strip()


def _extract_text(msg: Message) -> str:
    """Estrae testo dal Message Anthropic (concat di tutti i text blocks)."""
    out = []
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            out.append(block.text)  # type: ignore[union-attr]
    return "".join(out).strip()


def _strip_json_fences(text: str) -> str:
    """Rimuove ```json ... ``` se presente (Claude a volte li aggiunge)."""
    t = text.strip()
    if t.startswith("```"):
        # Rimuovi prima riga ```json o ```
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return t


def _validate_and_normalize(parsed: dict, *, model: str) -> ScoringResult:
    """Valida i campi richiesti e normalizza i valori entro i range."""
    try:
        assets_raw = parsed.get("assets_mentioned") or []
        if not isinstance(assets_raw, list):
            raise ScoringError("assets_mentioned must be list")

        # Normalizza: uppercase + filtro a known assets (max 8)
        assets = []
        for a in assets_raw[:8]:
            if not isinstance(a, str):
                continue
            sym = a.strip().upper()
            if sym in KNOWN_ASSETS:
                assets.append(sym)

        event_type = str(parsed.get("event_type", "other")).lower().strip()
        if event_type not in EVENT_TYPES:
            event_type = "other"

        factual_impact = _clamp(float(parsed.get("factual_impact", 0.0)), -1.0, 1.0)
        sentiment_score = _clamp(float(parsed.get("sentiment_score", 0.0)), -1.0, 1.0)
        confidence = _clamp(float(parsed.get("confidence", 0.5)), 0.0, 1.0)
        ttl_hours = int(_clamp(float(parsed.get("ttl_hours", 24)), 1, 168))

        reasoning = parsed.get("reasoning")
        if reasoning is not None:
            reasoning = str(reasoning)[:500]

        return ScoringResult(
            assets_mentioned=assets,
            event_type=event_type,
            factual_impact=factual_impact,
            sentiment_score=sentiment_score,
            confidence=confidence,
            ttl_hours=ttl_hours,
            reasoning=reasoning,
            model=model,
            raw_response=parsed,
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise ScoringError(f"invalid scoring payload: {exc}") from exc


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
