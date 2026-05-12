"""STAT-ARB — pairs trade BTC/ETH cointegrazione market-neutral.

Ref: IJSRA 2026-0283 (BTC-ETH Statistical Arbitrage) → Sharpe 1.58-2.45 OOS,
beta 0.09-0.18, market-neutral REALE in bull e bear.

Approccio:
1. Engle-Granger cointegration test (rolling ADF su residual spread)
2. Z-score normalizzato della residual con rolling mean+std
3. Entry: |Z| > 2.0
4. Exit: |Z| < 0.5
5. Stop-loss: |Z| > 3.5 (cointegrazione potenzialmente persa)
6. Half-life di mean reversion come filtro (skip se > 30d)
"""
