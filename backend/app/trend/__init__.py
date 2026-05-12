"""Motore TREND — Donchian ensemble multi-lookback su universe rolling top-20.

Ref: AdaptiveTrend (arXiv 2602.11708, Feb 2026) → Sharpe 2.41 OOS 2022-2024.

Componenti:
- Donchian breakout multi-lookback (5,10,20,30,60,90,150,250)
- Volatility-targeting position sizing
- Dynamic trailing stop calibrato su ATR
- Rolling Sharpe asset selection (top-N monthly)
- 70/30 long-short asymmetric
"""
