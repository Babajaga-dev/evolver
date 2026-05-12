"""Risk Allocator multi-motore.

Combina segnali da:
- TREND (Donchian ensemble) — direzionale long-short
- STAT-ARB (cointegration) — market-neutral
- CARRY (funding rate) — market-neutral funding harvest

Overlays:
- GATE 1d regime detector (blocca TREND in bear/transition)
- F&G EMA-24w macro overlay (extreme zones modulano TREND)

Pesi dinamici: inverso variance dei 3 motori su rolling Sharpe 30d.
"""
