import os, time, json, urllib.request, urllib.error, sys
from utils import scrape_rubinot as rubi

# ===============================
# CONFIG
# ===============================
WORLD      = os.environ.get("WORLD", "Solarian")
INTERVAL   = int(os.environ.get("INTERVAL_MS", "60000")) / 1000.0

# limites
MAX_EMBEDS_PER_TICK    = int(os.environ.get("MAX_EMBEDS_PER_TICK", "6"))
MAX_EMBEDS_PER_REQUEST = int(os.environ.get("MAX_EMBEDS_PER_REQUEST", "10"))

# LEVEL UP: lista de personagens para acompanhar (opcional)
WATCH = [n.strip() for n in os.environ.get("WATCH_CHARS", "").split(",") if n.strip()]

# Webhooks (um por canal)
DEATHS_WEBHOOK_URL    = os.environ.get("DEATHS_WEBHOOK_URL")     # canal 1
LEVELS_WEBHOOK_URL    = os.environ.get("LEVELS_WEBHOOK_URL")     # canal 2
TRANSFERS_WEBHOOK_URL = os.environ.get("TRANSFERS_WEBHOOK_URL")  # canal 3

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

if not (DEATHS_WEBHOOK_URL and LEVELS_WEBHOOK_URL and TRANSFERS_WEBHOOK_URL):
    print("❌ Defina DEATHS_WEBHOOK_URL, LEVELS_WEBHOOK_URL e TRANSFERS_WEBHOOK_URL.", file=sys.stderr)
    raise SystemExit(1)

# ===============================
# DISCORD WEBHOOK SENDER (rate-limit aware + batching)
# ===============================
def _http_json(url, payload, headers, timeout=15):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(1000).decode("utf-8", "ignore") if getattr(resp, "length", None) else ""
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read(1200).decode("utf-8", "ignore")
        # reergue com body disponível em e.args[2]
        raise urllib.error.HTTPError(e.url, e.code, body, e.hdrs, e.fp)

def _send_webhook(webhook_url, embeds, content=None):
    url = webhook_url if webhook_url.endswith("?wait=true") else webhook_url + "?wait=true"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    payload = {"username": "Rubinot Watcher"}
    if embeds: payload["embeds"] = embeds
    if content: payload["content"] = content

    while True:
        try:
            status, body = _http_json(url, payload, headers)
            if status in (200, 204):
                return
            print("[discord] status:", status, "| body:", (body or "")[:250])
            return
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # respeita retry_after
                try:
                    parsed = json.loads(e.args[2])
                    retry_after = float(parsed.get("retry_after", 1.0))
                except Exception:
                    retry_after = 1.0
                sleep_for = max(0.5, retry_after) + 0.2
                print(f"[discord] 429 — aguardando {sleep_for:.2f}s...")
                time.sleep(sleep_for)
                continue
            print("[discord] HTTPError:", e.code, "|", e.args[2][:250] if len(e.args)>2 else "")
            return
        except Exception as ex:
            print("[discord] erro:", ex)
            return

def _post_batches(topic, embeds, content=None):
    if not embeds and not content:
        return
    webhook = {
        "deaths": DEATHS_WEBHOOK_URL,
        "levels": LEVELS_WEBHOOK_URL,
        "transfers": TRANSFERS_WEBHOOK_URL
    }[topic]
    step = max(1, min(MAX_EMBEDS_PER_REQUEST, 10))  # 10 embeds/req é o limite do Discord
    for i in range(0, len(embeds) or 1, step):
        batch = embeds[i:i+step] if embeds else []
        _send_webhook(webhook, batch, content)

# ===============================
# PING INICIAL NOS 3 CANAIS
# ===============================
try:
    _post_batches("deaths", [], content="🟢 Death List online.")
    _post_batches("levels", [], content="🟢 Level List online.")
    _post_batches("transfers", [], content="🟢 Transfer List online.")
    print("[debug] ping OK nos 3 canais.")
except Exception as e:
    print("[erro] ping falhou:", e)

# ===============================
# CACHES
# ===============================
seen_deaths    = set()
seen_transfers = set()
level_cache    = {}  # {"Name": last_level}
_bootstrapped  = False

# ===============================
# TICKS
# ===============================
def tick_deaths(limit_remaining):
    sent = 0
    # IMPORTANTE: passa o mundo ao scraper (ele usa &world=)
    deaths = rubi.latest_deaths(WORLD)
    print(f"[debug] deaths[{WORLD}] = {len(deaths)}")

    items = deaths
    # anti-spam inicial: marca backlog e envia só os últimos N
    if not _bootstrapped and len(items) > limit_remaining:
        for d in items[:-limit_remaining]:
            eid = f"death|{WORLD}|{d['time']}|{d['character']}|{d['level']}|{d['cause']}"
            seen_deaths.add(eid)
        items = items[-limit_remaining:]

    embeds = []
    for d in reversed(items):
        if sent >= limit_remaining:
            break
        eid = f"death|{WORLD}|{d['time']}|{d['character']}|{d['level']}|{d['cause']}"
        if eid in seen_deaths:
            continue
        embeds.append({
            "title": f"💀 Morte — {d['character']}",
            "description": f"{d['character']} (Lvl {d['level']}) morreu para **{d['cause']}**",
            "fields": [
                {"name": "Quando", "value": d['time'] or "-", "inline": True},
                {"name": "Mundo", "value": WORLD, "inline": True},
            ]
        })
        seen_deaths.add(eid)
        sent += 1

    if embeds:
        _post_batches("deaths", embeds)
    return sent

def tick_transfers(limit_remaining):
    sent = 0
    # lê TODAS as transfers e filtra por destino == WORLD (ex.: Solarian)
    transfers = rubi.transfers(None)
    print(f"[debug] transfers[ALL] = {len(transfers)}")
    filtered = [t for t in transfers if (t["toWorld"] or "").lower() == WORLD.lower()]

    items = filtered
    if not _bootstrapped and len(items) > limit_remaining:
        for t in items[:-limit_remaining]:
            tid = f"transfer|{WORLD}|{t['time']}|{t['character']}|{t['fromWorld']}|{t['toWorld']}|{t.get('level',0)}"
            seen_transfers.add(tid)
        items = items[-limit_remaining:]

    embeds = []
    for t in reversed(items):
        if sent >= limit_remaining:
            break
        tid = f"transfer|{WORLD}|{t['time']}|{t['character']}|{t['fromWorld']}|{t['toWorld']}|{t.get('level',0)}"
        if tid in seen_transfers:
            continue
        embeds.append({
            "title": f"🔁 Transfer — {t['character']} (Lvl {t.get('level', 0)})",
            "fields": [
                {"name": "Former World", "value": t['fromWorld'] or "-", "inline": True},
                {"name": "Destination World", "value": t['toWorld'] or "-", "inline": True},
                {"name": "Transfer Date", "value": t['time'] or "-", "inline": False},
            ]
        })
        seen_transfers.add(tid)
        sent += 1

    if embeds:
        _post_batches("transfers", embeds)
    return sent

def tick_levels(limit_remaining):
    # Level ups só para os nomes definidos em WATCH_CHARS
    if not WATCH or limit_remaining <= 0:
        return 0
    sent = 0
    embeds = []
    for name in WATCH:
        if sent >= limit_remaining:
            break
        try:
            info = rubi.character(name)
        except Exception as e:
            print(f"[warn] erro character({name}):", e)
            continue
        prev = level_cache.get(info["name"])
        if prev is not None and info["level"] > prev:
            embeds.append({
                "title": f"⬆️ {info['name']} subiu de nível!",
                "description": f"{prev} → **{info['level']}**",
                "fields": [{"name": "Mundo", "value": info.get('world') or WORLD, "inline": True}],
            })
            sent += 1
        level_cache[info["name"]] = info["level"]

    if embeds:
        _post_batches("levels", embeds)
    return sent

def run_once():
    global _bootstrapped
    remaining = MAX_EMBEDS_PER_TICK

    d = tick_deaths(remaining)
    remaining -= d

    l = 0
    if remaining > 0:
        l = tick_levels(remaining)
        remaining -= l

    t = 0
    if remaining > 0:
        t = tick_transfers(remaining)
        remaining -= t

    _bootstrapped = True
    print(f"[tick] enviados: deaths={d}, levels={l}, transfers={t} | remaining={remaining}")

# ===============================
# LOOP
# ===============================
if __name__ == "__main__":
    print(f"✅ Watcher (Webhooks) iniciado. Mundo={WORLD} Intervalo={int(INTERVAL)}s")
    if not WATCH:
        print("ℹ️ WATCH_CHARS vazio — levels serão ignorados até você definir nomes.")
    while True:
        try:
            run_once()
        except Exception as e:
            print("Erro no tick:", e)
        time.sleep(INTERVAL)
