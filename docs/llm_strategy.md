# LLM Strategy — uso di Claude API

## Principio guida

> Non chiamare un LLM per dire ciò che un GA può scoprire da solo.

Gli LLM sono potenti ma costosi e non deterministici. Usarli dove davvero brillano:
1. Comprensione del linguaggio naturale (news classification)
2. Reasoning su contesti complessi e poco strutturati (postmortem)

Non usarli per:
- Decidere "compra/vendi" su singolo trade — il GA è migliore (deterministico, evolutivo)
- Calcolare indicatori tecnici — pandas-ta-classic è 1000x più veloce e preciso
- Predire prezzi — la letteratura è chiara: zero-shot LLM su time series è inferiore a modelli specializzati

## Split per task

| Task | Modello | ID API | Volume | Costo stimato/mese |
|------|---------|--------|--------|---------------------|
| News classification | Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | ~150/giorno | ~$3 |
| Postmortem settimanale | Claude Opus 4.6 | `claude-opus-4-6` | 1/settimana | ~$3-4 |
| Sanity check signal (opzionale, off di default) | Claude Sonnet 4.6 | `claude-sonnet-4-6` | ~5/giorno | ~$3 |

**Totale base v1**: ~$6-10/mese.

## Task 1 — News classification (Haiku)

### Input
Una news (titolo + body, max 2000 token effettivi):

```json
{
  "title": "Bitcoin breaks $100k as institutional inflows surge",
  "body": "BTC reached a new all-time high...",
  "published_at": "2026-05-08T14:23:00Z",
  "source": "cryptopanic"
}
```

### System prompt (template)

```
Sei un analista finanziario specializzato in crypto. Classifica le news che ricevi
con OUTPUT STRUTTURATO JSON. Non spiegare, non riassumere — solo JSON valido.

Schema output:
{
  "assets_mentioned": [...],   // sottoinsieme di ["BTC", "ETH", "SOL", ...]
  "event_type": "...",         // hack | regulation | partnership | adoption |
                               // technology | opinion | market | macro | other
  "factual_impact": -1.0 to 1.0,  // impatto reale stimato (hack=-0.9, ETF approval=+0.8)
  "sentiment_score": -1.0 to 1.0, // sentiment del wording
  "confidence": 0.0 to 1.0,       // quanto sei sicuro della classificazione
  "ttl_hours": int,               // dopo quante ore la news perde rilevanza
  "reasoning": "..."              // 1-2 frasi, max 200 chars
}
```

### Best practices

- **Use prompt caching** per il system prompt — è identico per ogni news, costa 90% in meno.
- **Structured outputs** via tool use o response_format JSON.
- **Retry con backoff esponenziale** su rate limit (`tenacity`).
- **Ignora news con confidence < 0.5** — meglio nessuno score che uno sbagliato.

## Task 2 — Postmortem settimanale (Opus)

### Input
Report strutturato di ~50K token aggregato dal worker `worker-postmortem`:

```
WEEKLY POSTMORTEM — week 18 (2026-04-27 → 2026-05-03)

[1] PERFORMANCE
  Equity start: $10,420
  Equity end:   $10,180  (-2.30%)
  Max drawdown: -3.8% (giorno 2026-04-30)
  Sharpe weekly: -1.1

[2] TOP 10 LOSING TRADES
  ...

[3] TOP 10 WINNING TRADES
  ...

[4] POPULATION FITNESS DISTRIBUTION
  Best aggregate fitness: 1.82 (strategy_id=...)
  Mean fitness: 0.34
  Std: 0.61

[5] ACTIVE STRATEGIES (top 5)
  ...

[6] NEWS DELLA SETTIMANA (con score)
  ...

[7] REGIME OBSERVATION
  Mon-Wed: bull (EMA200 above)
  Thu-Fri: range (ADX < 20)
  Weekend: chop
```

### System prompt

```
Sei un analista quant senior. Analizzi report settimanali di un sistema di trading
paper-mode con popolazione GA. Il tuo output è un MEMO scritto in italiano,
800-1200 parole, struttura:

  1. Executive summary (3-4 frasi, conclusione netta)
  2. Cosa è andato bene (con esempi specifici)
  3. Cosa è andato male (con causa root, non sintomo)
  4. Pattern nelle perdite (concentrazione temporale, regime, strategy family)
  5. Suggerimenti di mutazione mirata alla popolazione (es. "aumentare
     news_sensitivity di +0.2 su strategie trend_follow")
  6. Cosa monitorare la prossima settimana

Sii brutalmente onesto. Se la settimana è andata male, dillo. Se la popolazione
sta convergendo su un local optimum, segnalalo. Non sei un PR, sei un quant.
```

### Output

Markdown da salvare in tabella `postmortem_reports` (da creare in Fase 5).

## Anti-pattern da evitare

| ❌ Mai | ✅ Invece |
|--------|----------|
| `claude.predict("BTC price next hour?")` | Lascia che il GA + indicatori decidano |
| Chiamare Opus per ogni news | Haiku per news, Opus solo per postmortem |
| Dare all'LLM accesso al wallet | LLM mai esegue ordini — solo legge e suggerisce |
| Prompt senza JSON schema | Sempre output strutturato per parsing affidabile |
| No retry / no timeout | tenacity con max 3 retry, timeout 60s |
| Non monitorare costo cumulato | Track `claude_api_cost_usd` per call in DB |

## Cost monitoring

Tabella `llm_calls` (da aggiungere in Fase 3):

```sql
CREATE TABLE llm_calls (
    id UUID PRIMARY KEY,
    model VARCHAR(64),
    purpose VARCHAR(64),  -- news_classify, postmortem, sanity_check
    input_tokens INT,
    output_tokens INT,
    cached_tokens INT,    -- da prompt caching
    cost_usd NUMERIC(10, 6),
    latency_ms INT,
    success BOOLEAN,
    error_type VARCHAR(64),
    called_at TIMESTAMPTZ
);
```

Dashboard `/admin/costs` mostra costo cumulato giornaliero/mensile per modello.
