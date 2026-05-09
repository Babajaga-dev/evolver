# Evolver

Sistema di trading crypto **evolutivo** che combina algoritmi genetici, indicatori tecnici, news sentiment e LLM per analizzare serie temporali di criptovalute e generare decisioni di buy/sell ottimizzate.

> **Stato corrente:** Fase 0 (foundation). Paper trading only — non collegato a capitale reale.

---

## Filosofia

Quattro paradigmi che lavorano in sinergia, ognuno con il proprio compito:

| Paradigma | Cosa fa | Cosa NON fa |
|-----------|---------|-------------|
| **Algoritmi Genetici (GA)** | Ottimizza parametri di strategie note via evoluzione di una popolazione | Non decide il singolo trade in tempo reale |
| **Indicatori Tecnici** | Generano segnali deterministici (RSI, MACD, Bollinger, ATR, ecc.) | Non sono usati in isolamento, sempre dentro una strategia evoluta |
| **LLM (Claude API)** | Classifica news (Haiku 4.5) + scrive postmortem settimanali (Opus 4.6) | Non viene chiamato per decidere "compra/vendi" sui singoli trade |
| **News & Sentiment** | Modula esposizione tramite `news_sensitivity` come gene del cromosoma | Non sostituisce l'analisi tecnica, la integra |

Vincoli architetturali non negoziabili:

- **Multi-timeframe ibrido**: regime filter su 1d, primary signal su 4h, execution timing su 15m
- **DNA vincolato**: cromosoma = parametri di strategie note (no genetic programming pieno in v1)
- **Fitness multi-obiettivo**: Sharpe + Calmar + max drawdown + robustezza (mai puro return)
- **Walk-forward + holdout**: 5 finestre temporali, holdout finale obbligatorio
- **Paper trading minimo 60-90 giorni** prima di considerare live trading

---

## Stack tecnologico

**Backend**: Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · ccxt · DEAP · numpy/pandas · structlog · uv

**Database**: PostgreSQL 16 + TimescaleDB extension · Redis 7 (cache + pub/sub)

**Frontend**: Next.js 15 (App Router) · TypeScript · Tailwind CSS · shadcn/ui

**LLM**: Anthropic Claude API
- `claude-haiku-4-5-20251001` per news classification (alto volume)
- `claude-opus-4-6` per postmortem settimanale (low volume, high reasoning)

**Deploy**: Dokploy (self-hosted PaaS Docker-based) su VPS singolo

**Asset universe v1**: BTC/USDT, ETH/USDT (via Binance)

---

## Struttura del repo

```
evolver/                  # repo root (github.com/Babajaga-dev/evolver)
├── backend/              # Python: FastAPI + workers + ML/GA
│   ├── app/              # codice applicativo
│   │   ├── api/          # endpoint REST
│   │   ├── core/         # config, logging, db connection
│   │   ├── models/       # SQLAlchemy ORM
│   │   ├── exchanges/    # ccxt connectors
│   │   ├── indicators/   # libreria indicatori tecnici
│   │   ├── strategies/   # famiglie di strategie + cromosoma
│   │   ├── ga/           # genetic algorithm loop
│   │   ├── llm/          # Anthropic SDK wrappers
│   │   ├── paper/        # paper exchange simulator
│   │   └── workers/      # entrypoint worker (data, GA, decision, ecc.)
│   ├── alembic/          # migrazioni DB
│   ├── tests/            # pytest
│   └── pyproject.toml
├── frontend/             # Next.js dashboard
├── workers/              # Dockerfile dei worker (riusa codice backend/)
├── infra/                # docker-compose, Dokploy config, scripts deploy
├── docs/                 # architecture.md, deploy_dokploy.md, ecc.
├── notebooks/            # Jupyter per ricerca, validazione, esperimenti
└── scripts/              # utility CLI (backfill, eval, ecc.)
```

---

## Quick start (sviluppo locale)

Richiede: Docker Desktop, Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22+, pnpm.

```bash
# 1. Clone
git clone <repo-url> evolver && cd evolver

# 2. Variabili d'ambiente
cp .env.example .env
# Edita .env con la tua ANTHROPIC_API_KEY

# 3. Bring up infrastruttura (Postgres+Timescale, Redis)
docker compose up -d postgres redis

# 4. Backend Python
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 5. Verifica
curl http://localhost:8000/health
# {"status":"ok","timescale":true,"redis":true}

# 6. Backfill dati storici BTC + ETH (impiega ~30 min, scarica ~1.5GB)
uv run python -m scripts.backfill --symbols BTC/USDT,ETH/USDT --years 5

# 7. Frontend (in altro terminale)
cd frontend
pnpm install
pnpm dev
# Apri http://localhost:3000
```

---

## Documentazione

- [docs/architecture.md](docs/architecture.md) — Architettura a 7 layer, diagrammi, flusso dati
- [docs/dna_chromosome.md](docs/dna_chromosome.md) — Definizione del cromosoma e fitness function
- [docs/deploy_dokploy.md](docs/deploy_dokploy.md) — Deploy su VPS con Dokploy
- [docs/llm_strategy.md](docs/llm_strategy.md) — Uso di Claude API (Haiku news / Opus postmortem)

---

## Roadmap

| Fase | Descrizione | Stato |
|------|-------------|-------|
| 0 | Foundation: repo, DB, ccxt, Docker, FastAPI scaffold | 🟡 in corso |
| 1 | Backtest engine + indicator library | ⚪ |
| 2 | GA loop con DNA vincolato + walk-forward | ⚪ |
| 3 | News pipeline + sentiment via Claude Haiku | ⚪ |
| 4 | Live mode + paper exchange simulator + decision loop | ⚪ |
| 5 | Frontend completo + postmortem LLM (Claude Opus) | ⚪ |
| 6+ | Live trading (solo dopo 60-90gg paper validation) | ⚪ |

---

## Licenza

Proprietario / privato. Non distribuire senza autorizzazione.

