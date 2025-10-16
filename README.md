
# Rubinot MultiWatcher v3 — Bot Token + 3 Canais (Discord)

Monitora **RubinOT** e envia para **três canais** no Discord (via **Bot Token**):
1) **Death List** — apenas mortes de membros da **guild `Invictus`** (configurável)
2) **Level List** — level up de membros da **guild `Invictus`**
3) **Transfer List** — transfers com **destino `Solarian`** (configurável via `DEST_WORLD`)

## 🧩 Variáveis de Ambiente (Railway)

**Obrigatórias (Discord - Bot Token):**
- `DISCORD_BOT_TOKEN` — token do seu bot (Developer Portal)
- `DEATHS_CHANNEL_ID` — ID do canal Death List
- `LEVELS_CHANNEL_ID` — ID do canal Level List
- `TRANSFERS_CHANNEL_ID` — ID do canal Transfer List

**Filtros e comportamento:**
- `WORLD` = `Solarian` (mundo monitorado)
- `GUILD_FILTER` = `Invictus` (nome da guild para deaths/levels)
- `DEST_WORLD` = `Solarian` (destino para filtrar transfers)
- `INTERVAL_MS` = `60000` (intervalo entre checks, recomendado 60s)
- `MAX_EMBEDS_PER_TICK` = `5` (limite total por ciclo — evita 429)
- `LEVEL_CHECKS_PER_TICK` = `10` (máx de membros checados p/ level/tick)
- `GUILD_REFRESH_MINUTES` = `10` (atualiza lista da guild a cada X min)

**Anti-bot (HTML fetch):**
- (opcional) `SCRAPERAPI_KEY` OU `SCRAPFLY_KEY` (recomendado para passar Cloudflare)
- (fallback) Playwright:
  - `RUBINOT_WAIT_MS` = `15000`
  - `RUBINOT_ATTEMPTS` = `4`
  - `HEADLESS` = `false` (headful pode ajudar)

## 🚀 Deploy no Railway
1. Crie um repositório com estes arquivos.
2. **Dockerfile** detectado automaticamente (ver abaixo).
3. Adicione as **variáveis** acima.
4. Deploy: os logs devem mostrar pings nos 3 canais e ticks.

## 🐳 Dockerfile sugerido
```Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && playwright install --with-deps chromium
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["python", "app.py"]
```

## 📦 requirements.txt
```
beautifulsoup4==4.12.3
requests==2.32.3
playwright==1.48.0
```

## 🔎 Notas
- O scraper tenta `ScraperAPI` → `Scrapfly` → `Playwright` (fallback).
- Se houver avalanche de eventos, o app **marca backlog** no primeiro tick e envia apenas os mais novos (até `MAX_EMBEDS_PER_TICK`), evitando **429**.
- Se o layout do RubinOT mudar, ajuste os seletores em `utils/scrape_rubinot.py`.
- O cache é em memória (reinícios perdem histórico leve). Para persistência forte, use Redis/DB.
