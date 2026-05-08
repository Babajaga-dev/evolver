# Deploy su Dokploy

Guida operativa per deploy di Evolver su VPS con Dokploy già installato.

## Prerequisiti verificati

- VPS con Dokploy installato e UI accessibile
- Anthropic API key con credito ($20+ raccomandati per v1)
- Repo Evolver pushato su GitHub (o GitLab/Gitea)
- Accesso al VPS via IP+porta (no dominio in v1 — useremo Dokploy default port o subdomain Dokploy)

## Step 1 — Creare il progetto in Dokploy

1. Login Dokploy UI → **Projects** → **Create Project**
2. Nome: `evolver`
3. Description: "Sistema di trading crypto evolutivo"

## Step 2 — Provisioning database managed

Dokploy crea Postgres e Redis come servizi managed separati dal codice applicativo.

### PostgreSQL + TimescaleDB

1. Project → **Database** → **Create Database** → **PostgreSQL**
2. Configurazione:
   - **Name**: `evolver-postgres`
   - **Image**: `timescale/timescaledb:latest-pg16` (override del default Postgres)
   - **Database name**: `evolver`
   - **Username**: `evolver`
   - **Password**: (genera password forte, salva in password manager)
   - **Port**: 5432 (default, accessibile solo network interno)
3. Salva — Dokploy crea il container e ti fornisce:
   - Internal DSN: `postgresql://evolver:PWD@evolver-postgres:5432/evolver`
   - External DSN (se esponi porta): `postgresql://evolver:PWD@VPS_IP:EXPOSED_PORT/evolver`

### Redis

1. Project → **Database** → **Create Database** → **Redis**
2. Configurazione:
   - **Name**: `evolver-redis`
   - **Image**: `redis:7-alpine`
   - Optional: password
3. Internal DSN: `redis://evolver-redis:6379/0`

## Step 3 — Application: backend FastAPI

1. Project → **Application** → **Create Application** → **Docker Compose**
2. **Source**:
   - Provider: GitHub (autorizza Dokploy → GitHub via OAuth)
   - Repository: `<your-username>/evolver`
   - Branch: `main`
   - Compose path: `infra/dokploy/compose.yml`
3. **Environment** tab — aggiungi le seguenti variabili:

```env
# Database (DSN forniti da Dokploy nello step 2)
DATABASE_URL=postgresql+asyncpg://evolver:PWD@evolver-postgres:5432/evolver
DATABASE_URL_SYNC=postgresql+psycopg://evolver:PWD@evolver-postgres:5432/evolver
REDIS_URL=redis://evolver-redis:6379/0

# Anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...
CLAUDE_MODEL_HAIKU=claude-haiku-4-5-20251001
CLAUDE_MODEL_OPUS=claude-opus-4-6

# CORS — adatta a IP+porta che esporrai per il frontend
API_CORS_ORIGINS=http://VPS_IP:3000

# Trading universe
SYMBOLS=BTC/USDT,ETH/USDT
TIMEFRAMES=15m,1h,4h,1d

# Optional
CRYPTOPANIC_API_KEY=
BINANCE_API_KEY=
BINANCE_API_SECRET=

# Image tag
IMAGE_TAG=latest
LOG_LEVEL=INFO
NEXT_PUBLIC_API_URL=http://backend:8000
```

4. **Domains/Ports** tab:
   - Backend: assegna porta esterna (es. 8000) o subdomain Dokploy (es. `evolver-api.dokploy.tld`)
   - Frontend: assegna porta esterna (es. 3000) o subdomain Dokploy (es. `evolver.dokploy.tld`)
   - Dokploy gestisce SSL via Let's Encrypt automatico se usi subdomain
5. **Deploy** → "Deploy Now"

## Step 4 — Migration DB (post-deploy)

Dopo il primo deploy del backend serve applicare le migration Alembic. Dokploy permette di eseguire comandi one-shot:

1. Application → **Backend** → **Terminal/Shell** (o "Run Command")
2. Esegui:
   ```bash
   cd /app && alembic upgrade head
   ```
3. Verifica:
   ```bash
   curl -s http://localhost:8000/health
   # {"status":"ok","database":true,"timescale":true,"redis":true}
   ```

## Step 5 — Backfill dati storici (one-shot)

Eseguire manualmente la prima volta — impiega ~30 minuti per 5 anni di BTC+ETH × 4 timeframe.

1. Application → Backend → Terminal:
   ```bash
   cd /app && python -m scripts.backfill --symbols BTC/USDT,ETH/USDT --years 5
   ```
2. Monitora i log (`Logs` tab nella UI Dokploy)
3. A fine backfill, verifica conta candele:
   ```bash
   psql $DATABASE_URL_SYNC -c "SELECT symbol, timeframe, COUNT(*) FROM ohlcv GROUP BY 1,2 ORDER BY 1,2;"
   ```

## Step 6 — CI/CD (push-to-deploy)

Dokploy supporta auto-deploy su push a branch:

1. Application → Settings → **Auto Deploy**
2. Toggle **on**, branch `main`
3. Dokploy crea webhook GitHub automaticamente
4. Da quel momento, ogni `git push origin main` triggera un rebuild + redeploy

## Step 7 — Backup

1. Project → Database → evolver-postgres → **Backups**
2. Configura schedule cronico: ogni 6 ore raccomandato
3. Storage backup: locale al VPS in `/etc/dokploy/backups/` (o S3/MinIO se configurato)
4. Test restore almeno una volta prima di andare live

## Monitoring & alerting (raccomandato)

Per la v1 paper trading non è blocking, ma per il live trading è obbligatorio:

- Dokploy include logs viewer e metrics base (CPU/RAM per container)
- Per alerting via Telegram/Discord: configurare webhook in `notifications` Dokploy
- In Fase 4+ aggiungeremo un Telegram bot custom dentro `backend/app/notifications/` per:
  - Errori critici durante decision loop
  - Drawdown > soglia
  - Kill switch attivato

## Troubleshooting

| Sintomo | Causa probabile | Soluzione |
|---------|-----------------|-----------|
| Backend logs: `extension "timescaledb" is not available` | Image Postgres standard, non Timescale | In Dokploy DB settings cambia image a `timescale/timescaledb:latest-pg16` |
| Healthcheck rosso, `database: false` | DSN errato o DB non raggiungibile | Verifica nome servizio in DSN (deve corrispondere al nome del DB Dokploy) |
| `ANTHROPIC_API_KEY missing` all'avvio | Env var non passata al container | Application → Environment → riverifica e redeploy |
| Backfill lentissimo | Rate limit Binance | Aumenta `sleep_between_chunks_s` in scripts/backfill.py |

## Sicurezza minima (v1 paper)

- Anthropic API key è il secret più sensibile — non committare mai, solo Dokploy env vars
- Postgres password forte, accessibile solo via network interno Docker
- Frontend e API esposti solo su porte specifiche, no `0.0.0.0:*`
- Aggiungere fail2ban / firewall (ufw) sul VPS se non già presente
- Backup automatici ogni 6 ore (stato DB)

Per il **live trading** aggiungeremo: 2FA su Dokploy UI, secrets in vault esterno, log audit trail, replica Postgres standby. Non in v1.
