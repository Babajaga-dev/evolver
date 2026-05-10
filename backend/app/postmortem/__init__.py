"""Postmortem analyzer — Claude Opus weekly review.

Una volta a settimana (o on-demand) chiama Opus passando:
    - top strategies dal GA degli ultimi N giorni
    - news regime (sentiment aggregato BTC + ETH)
    - paper trading stats (P&L, win rate, drawdown)

Opus genera markdown con:
    1. Sintesi performance
    2. Pattern emergenti (cromosomi convergenti, regime shift)
    3. Red flags (low signal, drawdown anomalo)
    4. Suggerimenti per la settimana successiva

Costo stimato: ~$0.50-1.00 per postmortem (input ~30k token, output ~3k).
Triggerato manualmente dal pannello /control.
"""

from app.postmortem.analyzer import (
    PostmortemError,
    PostmortemReport,
    generate_postmortem,
)

__all__ = [
    "PostmortemError",
    "PostmortemReport",
    "generate_postmortem",
]
