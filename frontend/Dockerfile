# =============================================================================
#  Evolver frontend — Next.js 15 standalone build
# =============================================================================

FROM node:22-alpine AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

FROM node:22-alpine AS builder
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Healthcheck rimosso intenzionalmente:
#   - busybox wget e nc su node:22-alpine hanno entrambi comportamenti
#     inconsistenti (exit code 1 anche con server up).
#   - Senza HEALTHCHECK Docker classifica il container come "no health
#     check" anziché "unhealthy" — Traefik instrada normalmente.
#   - Il monitoring vivo è già coperto da Traefik (HTTP probing) e
#     da Dokploy (status running del container).

CMD ["node", "server.js"]
