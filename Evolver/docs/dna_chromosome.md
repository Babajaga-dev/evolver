# DNA del Cromosoma — definizione formale (v1)

## Forma del cromosoma

Una strategia è un dizionario JSON con campi tipati e range vincolati.

```python
Chromosome = {
    "family": str,                  # categorica
    "entry_indicators": list,       # max 3
    "entry_logic": str,             # AND | OR
    "exit_indicators": list,        # max 2
    "stop_atr_mult": float,         # 1.0–4.0
    "tp_atr_mult": float,           # 1.5–6.0
    "position_size_pct": float,     # 0.5–5.0
    "news_sensitivity": float,      # 0.0–1.0
    "regime_filter": list[str],     # subset di [bull, range, bear]
}
```

## Famiglie di strategie supportate

| Family | Logica base | Indicatori tipici |
|--------|-------------|-------------------|
| `trend_follow` | Long su trend confermato, exit su reversal | EMA, ADX, MACD |
| `mean_reversion` | Long su oversold, short su overbought (in range) | RSI, Bollinger, Stochastic |
| `breakout` | Long su rottura resistenza con volume | Donchian, ATR, Volume |
| `volatility` | Trade compressione/espansione | ATR, BB Width, Keltner |

La famiglia condiziona quali indicatori sono ammessi nel cromosoma — vincolo soft, non hard, per permettere combinazioni creative ma evitare assurdità (es. RSI in `breakout` strategy).

## Indicatori ammessi

Pool di indicatori dal quale il GA pesca per `entry_indicators` ed `exit_indicators`:

```python
INDICATOR_POOL = {
    # Momentum
    "rsi":         {"period": (5, 30), "buy_below": (15, 40), "sell_above": (60, 85)},
    "stoch":       {"k": (5, 20), "d": (3, 10), "oversold": (10, 30), "overbought": (70, 90)},
    "macd":        {"fast": (8, 16), "slow": (20, 30), "signal": (7, 12)},
    "cci":         {"period": (10, 30), "level": (80, 200)},

    # Trend
    "ema":         {"period": (9, 200), "cross_with": (9, 200)},
    "sma":         {"period": (10, 200)},
    "adx":         {"period": (10, 25), "threshold": (15, 35)},
    "ichimoku":    {"tenkan": (7, 12), "kijun": (20, 30), "senkou": (50, 60)},

    # Volatility
    "bbands":      {"period": (10, 30), "std": (1.5, 3.0)},
    "atr":         {"period": (10, 25)},
    "keltner":     {"period": (10, 30), "mult": (1.5, 3.0)},

    # Volume
    "obv":         {},
    "volume_sma":  {"period": (10, 30), "mult_threshold": (1.2, 3.0)},
}
```

Il GA mutua i parametri con distribuzione gaussiana centrata sul valore corrente, clip ai range specificati.

## Constraints duri

- `entry_indicators` ≥ 1 e ≤ 3
- `exit_indicators` ≥ 0 e ≤ 2 (può uscire solo via stop/TP)
- `stop_atr_mult` < `tp_atr_mult` (R:R minimo 1:1)
- `regime_filter` non vuoto
- `position_size_pct` ≤ 5% (Kelly capped, no Kelly pieno)

Cromosomi che violano constraints vengono rigettati durante la generazione e ri-tentati. Mai hot-fixati silenziosamente — vogliamo che la popolazione sia pulita.

## Operatori GA

### Selection
**Tournament k=3**: pesco 3 individui random, vince quello con fitness più alta. Ripeti N volte per ottenere il pool dei genitori.

### Crossover (rate 0.7)
**Single-point per i campi categorici** (`family`, `entry_logic`, `regime_filter`).
**Arithmetic per i float** (`stop_atr_mult`, `tp_atr_mult`, `position_size_pct`, `news_sensitivity`):
```
child = α · parent_a + (1 - α) · parent_b   # α ~ U(0, 1)
```
**Subset crossover per gli indicator list**: il figlio eredita un subset random degli indicatori del genitore A più un subset del genitore B, capped a 3.

### Mutation (rate 0.2)
- Float: gaussiana con σ = 10% del range del gene, clip ai bounds
- Categorica: flip random con prob 0.3 condizionato su mutate
- Indicator params: scelto un indicatore random, mutato un suo parametro
- Add/remove indicator: con prob 0.1 aggiunge/rimuove un indicatore (rispettando i limiti)

### Elitism
Top 5 (5%) della popolazione passa alla generazione successiva senza modifiche.

## Inizializzazione (gen 0)

Popolazione di 100 strategie generata randomly entro i constraints, distribuita per famiglia:
- 30% trend_follow
- 30% mean_reversion
- 20% breakout
- 20% volatility

## Stopping criteria

Il GA si ferma quando:
1. Raggiunge 100 generazioni, OPPURE
2. Best fitness non migliora di > 1% per 15 generazioni consecutive (early stop), OPPURE
3. Diversità (std dei cromosomi) scende sotto threshold (population collapse — fai restart)

## Filogenesi

Ogni strategia ha `parent_ids: UUID[]`:
- `[]` → strategia random in gen 0
- `[id]` → mutazione asessuata di una strategia
- `[id_a, id_b]` → crossover

Permette di ricostruire l'albero genealogico per visualizzazione frontend (D3 dendrogram in Fase 5).
