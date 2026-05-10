"""Postmortem analyzer — Claude Opus weekly review.

Aggregator: raccoglie GA top strategies + news sentiment + paper stats
e li passa a Opus 4.6 con un prompt strutturato per generare un report
markdown ad alto valore qualitativo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import Message

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ga import state as ga_state

log = get_logger(__name__)


SYSTEM_PROMPT = """You are a senior quantitative trading strategist reviewing a
weekly postmortem for an algorithmic trading lab named Evolver.

You have access to:
- GA top strategies (Sharpe, MaxDD, n_trades, chromosome params)
- News sentiment aggregates per asset (weighted_signal, event_type mix)
- Paper trading P&L and statistics
- Time period covered

Generate a markdown report with EXACTLY these 5 sections:

# Weekly Postmortem · {date_range}

## 1. Performance Summary
A 3-paragraph overview: equity change, key wins, key losses, regime context.

## 2. Strategy Patterns
What's converging in the GA? Are top strategies clustered around specific
parameter ranges? Any sign of overfitting or regime change?

## 3. Risk Flags
Low-signal strategies (n_trades < 20), unusual drawdowns, news event
clusters that may have skewed performance, parameter saturation
at boundaries.

## 4. News × Strategy Interaction
Where did news regime align with strategy direction? Where did it diverge?
Note specific events (hacks, regulations, macro) that mattered.

## 5. Next Week Recommendations
3-5 concrete actions: parameter range adjustments, strategy families to
explore, news event types to watch, paper trading limits to set.

Tone: precise, no fluff, no marketing language. Use tables where useful.
Bullet lists OK but prefer prose.

Word budget: ~800-1200 words total."""


@dataclass
class PostmortemReport:
    """Output del postmortem analyzer."""

    period_start: datetime
    period_end: datetime
    markdown: str
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd_estimate: float
    raw_input: dict[str, Any] = field(repr=False, default_factory=dict)


class PostmortemError(Exception):
    """Sollevato quando l'analyzer fallisce in modo non recuperabile."""


async def generate_postmortem(
    *,
    session: Any,  # AsyncSession (typed any per evitare circular import)
    days: int = 7,
    client: AsyncAnthropic | None = None,
) -> PostmortemReport:
    """Esegue il postmortem completo: aggregator + Opus call.

    Args:
        session: AsyncSession SQLAlchemy.
        days: finestra temporale del review (default 7).
        client: Anthropic client riusabile (opzionale).
    """
    settings = get_settings()
    cli = client or AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.claude_timeout_s * 4,  # postmortem più lungo
        max_retries=settings.claude_max_retries,
    )

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    # 1. Aggregato dati
    payload = await _build_input_payload(session, start=start, end=end, days=days)

    # 2. Costruisci user prompt
    user_content = _format_user_prompt(payload)

    # 3. Chiama Opus
    try:
        msg: Message = await cli.messages.create(
            model=settings.claude_model_opus,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:
        log.warning("postmortem.opus_failed", error=str(exc))
        raise PostmortemError(f"Opus call failed: {exc}") from exc

    # 4. Estrai testo
    text_parts = []
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)  # type: ignore[union-attr]
    markdown = "".join(text_parts).strip()

    if not markdown:
        raise PostmortemError("empty response from Opus")

    # 5. Cost estimate (Opus 4.6: $15/Mtok input, $75/Mtok output)
    tokens_in = msg.usage.input_tokens
    tokens_out = msg.usage.output_tokens
    cost = (tokens_in * 15.0 / 1_000_000) + (tokens_out * 75.0 / 1_000_000)

    log.info(
        "postmortem.generated",
        days=days,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost,
    )

    return PostmortemReport(
        period_start=start,
        period_end=end,
        markdown=markdown,
        model=settings.claude_model_opus,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        cost_usd_estimate=cost,
        raw_input=payload,
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


async def _build_input_payload(
    session: Any,
    *,
    start: datetime,
    end: datetime,
    days: int,
) -> dict[str, Any]:
    """Raccoglie tutti i dati di input per il postmortem."""
    from app.news import get_asset_sentiment
    from app.paper import get_paper_state, list_paper_trades

    # GA: top strategies da Redis (ultimo run completato)
    ga_runs = await ga_state.list_states(limit=20)
    completed = [r for r in ga_runs if r.status == "completed"]
    last_ga = completed[-1] if completed else None

    ga_top: list[dict[str, Any]] = []
    if last_ga:
        sorted_strats = sorted(
            last_ga.strategies,
            key=lambda s: s.sharpe_robust,
            reverse=True,
        )[:10]
        ga_top = [
            {
                "rank": i + 1,
                "sharpe_robust": float(s.sharpe_robust),
                "max_drawdown_abs": float(s.max_drawdown_abs),
                "n_trades": int(s.n_trades),
                "n_windows_winning": int(s.n_windows_winning),
                "generation": int(s.generation),
                "chromosome": _native_dict(s.chromosome),
            }
            for i, s in enumerate(sorted_strats)
        ]

    # News: sentiment per BTC + ETH
    btc_sentiment = await get_asset_sentiment(session, asset="BTC", hours=days * 24)
    eth_sentiment = await get_asset_sentiment(session, asset="ETH", hours=days * 24)

    # Paper trading state + recent trades
    paper_state = await get_paper_state(session)
    trades = await list_paper_trades(session, limit=50)
    paper_trades_summary = [
        {
            "symbol": t.symbol,
            "side": t.side,
            "status": t.status,
            "entry_time": t.entry_time.isoformat(),
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "pnl": float(t.pnl) if t.pnl is not None else None,
            "pnl_pct": t.pnl_pct,
        }
        for t in trades
    ]

    return {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": days,
        },
        "ga": {
            "last_run_id": last_ga.population_id if last_ga else None,
            "last_run_strategy": last_ga.config.strategy_id if last_ga else None,
            "last_run_symbol": last_ga.config.symbol if last_ga else None,
            "last_run_timeframe": last_ga.config.timeframe if last_ga else None,
            "top_strategies": ga_top,
        },
        "news": {
            "BTC": btc_sentiment,
            "ETH": eth_sentiment,
        },
        "paper": {
            "state": paper_state,
            "recent_trades": paper_trades_summary,
        },
    }


def _format_user_prompt(payload: dict[str, Any]) -> str:
    """Trasforma il payload in un prompt strutturato per Opus."""
    import json

    period = payload["period"]
    return f"""Generate the weekly postmortem for the period
{period["start"]} → {period["end"]} ({period["days"]} days).

Below is the full data dump in JSON. Read it carefully, then write the
markdown report following the 5-section structure from the system prompt.

```json
{json.dumps(payload, indent=2, default=str)}
```
"""


def _native_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Cast numpy/decimal types to Python native for JSON serialization."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if hasattr(v, "item"):  # numpy scalar
            out[k] = v.item()
        elif hasattr(v, "__float__") and not isinstance(v, (int, float, bool, str)):
            out[k] = float(v)
        else:
            out[k] = v
    return out
