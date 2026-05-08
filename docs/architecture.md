# Architettura — Evolver

## Filosofia

Quattro paradigmi che lavorano insieme, ognuno con un ruolo preciso e mai sovrapposto:

| Paradigma | Cosa fa | Cosa NON fa |
|-----------|---------|-------------|
| Algoritmi Genetici | Ottimizza parametri di strategie note | Non decide il singolo trade |
| Indicatori Tecnici | Generano segnali deterministici | Non vivono fuori da una strategia evoluta |
| Claude API (Haiku 4.5) | Classifica news strutturate | Non viene chiamato per decidere "compra/vendi" |
| Claude API (Opus 4.6) | Postmortem settimanale + reasoning | Non interviene sul singolo trade |

## I 7 layer

```
LAYER 1 — DATA INGEST
  Binance WS · Binance REST · News feeds (CryptoPanic + RSS) · On-chain
       └→ PostgreSQL + TimescaleDB hypertables (ohlcv, news_raw, equity_snapshots)

LAYER 2 — FEATURE & SENTIMENT
  Indicator engine (pandas-ta-classic): RSI, MACD, Bollinger, ATR, Ichimoku, ADX
  News scorer (Claude Haiku 4.5): {asset, event_type, sentiment, confidence}
       └→ feature_* + news_scored

LAYER 3 — EVOLUTION (GA loop)
  Population N=100 strategie · DEAP · Walk-forward 5 finestre
  Selection (tournament k=3) · Crossover · Mutation · Elitism (top 5)
  Fitness multi-obiettivo: w·Sharpe + w·Calmar - w·MaxDD - w·Complexity + w·Robustness
       └→ strategies + fitness_evaluations + generations

LAYER 4 — LIVE DECISION (loop 1h)
  1. Regime filter su 1d (bull/range/bear via EMA200 + ADX + struttura HH/HL)
  2. Filtra popolazione su regime_filter compatibile
  3. Top-k strategie generano segnali su 4h
  4. Voto pesato per fitness → segnale aggregato
  5. Timing su 15m (pull-back, retest)
  6. Modulazione con news_score corrente
  7. Send order → Paper Exchange

LAYER 5 — EXECUTION (paper trading)
  Paper Exchange Simulator:
    · book depth-aware slippage
    · fee maker/taker (Binance 0.10%/0.10%)
    · latency injection 50-200ms
    · position tracking, mark-to-market real-time
       └→ paper_trades + equity_snapshots

LAYER 6 — INTROSPECTION (cron settimanale)
  Claude Opus 4.6 con context strutturato (50K token):
    trade log, equity curve, news della settimana, fitness population
       └→ postmortem_reports → suggerimenti mutazione mirata

LAYER 7 — FRONTEND (Next.js 15)
  /live · /population · /postmortem · /backtest
```

## Multi-timeframe gerarchico

Le tre frequenze NON si fondono in un unico tensore. Vivono in tabelle separate (TimescaleDB hypertables) e collaborano gerarchicamente:

- **1d (regime filter)** → segnale ternario (bull/range/bear). Le strategie senza `regime_filter` compatibile vengono disabilitate.
- **4h (primary signal)** → la popolazione GA opera qui. È la frequenza di evoluzione e di decisione.
- **1h-15m (execution timing)** → quando il 4h dice "long", l'1h cerca un buon entry (pull-back, retest, OB confluence). Riduce slippage psicologico.

## Cromosoma vincolato (DNA)

Forma del cromosoma di una strategia in v1:

```python
{
    "family": "trend_follow" | "mean_reversion" | "breakout" | "volatility",
    "entry_indicators": [
        {"name": "rsi", "params": {"period": 14, "buy_below": 30}},
        # max 3
    ],
    "entry_logic": "AND" | "OR",
    "exit_indicators": [...],   # max 2
    "stop_atr_mult": 2.0,       # 1.0–4.0
    "tp_atr_mult": 3.5,         # 1.5–6.0
    "position_size_pct": 1.5,   # 0.5–5%
    "news_sensitivity": 0.6,    # 0–1
    "regime_filter": ["bull", "range"]
}
```

Gradi di libertà: ~10⁸ — gestibile con popolazione 100 e 50–100 generazioni.

## Fitness multi-obiettivo (mai puro return)

```
fitness = 0.40 · sharpe
        + 0.20 · calmar
        - 0.15 · max_drawdown
        - 0.10 · complexity_penalty
        + 0.15 · robustness_score
```

Dove `robustness_score` è la varianza inversa della performance valutata su 5 finestre walk-forward staggered. Una strategia che fa Sharpe 2 in 3 finestre e Sharpe -1 in 2 finestre vale meno di una che fa Sharpe 1.2 stabile.

## Walk-forward e holdout

Su un dataset 2020-2025:
- Training: 5 finestre rolling di 12 mesi, step 6 mesi
- Validation: 6 mesi successivi a ogni training window
- Holdout finale: ultimi 6 mesi mai visti durante GA

Una strategia accede al holdout solo se passa le 5 walk-forward. Se collassa sul holdout viene scartata anche se brillante in walk-forward.

## Trappole note

1. **Overfitting** → mitigato da DNA vincolato + multi-obiettivo + walk-forward + complexity penalty.
2. **Survivorship bias** → BTC + ETH solamente in v1, no rotation tra alts (eviteremo in v2).
3. **Lookahead leak** → ogni feature è calcolata con shift+1; backtest verifica che signal_t usi solo dati ≤ t-1.
4. **Regime change** → il GA continua a evolvere su dati nuovi (online), peso decrescente esponenziale sui dati vecchi nelle finestre walk-forward più recenti.
5. **Cost di trading sottostimato** → paper exchange include slippage book-aware + fee + latency. Backtest puro è solo upper bound.
