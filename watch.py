"""
watch.py — live wallet monitor with Telegram alerts.

Polls a watchlist every N minutes. On a new BUY:
  1. scores the token (RugCheck / liquidity / holder concentration)
  2. sends a Telegram alert with the details

No API keys needed for the tracing. Telegram needs a bot token + chat id
(free, create with @BotFather in 30 seconds).

Usage:
  python watch.py                       # uses watchlist.txt, polls every 5 min
  python watch.py --interval 10 --json out.json
"""
import argparse
import json
import os
import time

import whale_trace as w

HERE = os.path.dirname(os.path.abspath(__file__))
WATCHLIST = os.path.join(HERE, "watchlist.txt")
STATE = os.path.join(HERE, "state.json")


# ------------------------------------------------------------------ config
def load_watchlist():
    if not os.path.exists(WATCHLIST):
        return []
    out = []
    for line in open(WATCHLIST, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        addr = parts[0]
        chain = parts[1] if len(parts) > 1 else "solana"
        out.append({"address": addr, "chain": chain})
    return out


def load_state():
    if not os.path.exists(STATE):
        return {}
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    tmp = STATE + ".tmp"
    json.dump(state, open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, STATE)


# ------------------------------------------------------------------ alerts
def send_telegram(bot_token, chat_id, text):
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        w._post(url, payload)
        return True
    except Exception:
        return False


def token_scorecard(mint, chain="solana"):
    """Quick safety check on a token the wallet just bought."""
    out = {"mint": mint}
    try:
        d = w._get(w.DEXSCREENER_TOKEN.format(addr=mint))
        pair = (d.get("pairs") or [{}])[0]
        out["symbol"] = (pair.get("baseToken") or {}).get("symbol", "?")
        out["market_cap"] = (pair.get("marketCap") or 0) / 1e6
        out["liquidity_usd"] = (pair.get("liquidity") or {}).get("usd", 0)
        out["created"] = pair.get("pairCreatedAt")
    except Exception:
        pass
    if chain == "solana":
        try:
            d = w._get(w.RUGCHECK.format(mint=mint))
            out["rugcheck_score"] = d.get("score")
            risks = d.get("risks") or []
            out["rugcheck_risks"] = [r.get("name", "") for r in risks][:3]
            out["holders"] = d.get("totalHolders")
            top = d.get("topHolders") or []
            out["top_holder_pct"] = sum(h.get("pct", 0) for h in top[:5])
        except Exception:
            pass
    return out


def build_alert(wallet, trade, card):
    sym = card.get("symbol") or trade.token_symbol or trade.token[:8]
    lines = [
        f"*NEW BUY* `{wallet[:6]}...{wallet[-4:]}`",
        f"Token: *{sym}*",
        f"Size: {trade.amount_token:,.2f} {sym}",
    ]
    if card.get("market_cap"):
        lines.append(f"Market cap: ${card['market_cap']:.2f}M")
    if card.get("liquidity_usd"):
        lines.append(f"Liquidity: ${card['liquidity_usd']:,.0f}")
    if card.get("holders"):
        lines.append(f"Holders: {card['holders']:,}")
    if card.get("top_holder_pct"):
        lines.append(f"Top-5 holders: {card['top_holder_pct']:.1f}%")
    if card.get("rugcheck_score") is not None:
        sc = card["rugcheck_score"]
        verdict = "OK" if sc < 500 else ("SUS" if sc < 1500 else "RISKY")
        lines.append(f"RugCheck: {sc} ({verdict})")
    if card.get("rugcheck_risks"):
        lines.append("Risks: " + ", ".join(card["rugcheck_risks"]))
    lines.append(f"https://solscan.io/tx/{trade.tx}")
    return "\n".join(lines)


# ------------------------------------------------------------------ poll loop
def check_wallet(entry, state, seed_only=False):
    """Return list of alert texts for new trades since last poll."""
    addr, chain = entry["address"], entry["chain"]
    key = f"{chain}:{addr}"
    seen = state.setdefault("seen", {}).setdefault(key, [])
    first_run = not seen
    alerts = []
    try:
        r = (w.trace_solana if chain == "solana" else w.trace_evm)(addr, limit=25)
    except Exception:
        return alerts
    for t in r["trades"]:
        if t.tx in seen:
            continue
        seen.append(t.tx)
        # first poll: just record history, don't alert on old trades
        if first_run or seed_only:
            continue
        if t.side != "BUY":
            continue
        # skip wrappers / stables — not a signal
        sym = (t.token_symbol or "").upper()
        if sym in ("SOL", "WSOL", "USDC", "USDT", "USDH", "JITOSOL", "BSOL"):
            continue
        card = token_scorecard(t.token, chain)
        alerts.append(build_alert(addr, t, card))
    # cap memory
    state["seen"][key] = seen[-200:]
    return alerts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    bot = os.environ.get("TG_BOT_TOKEN", "")
    chat = os.environ.get("TG_CHAT_ID", "")
    watch = load_watchlist()
    if not watch:
        print(f"no wallets in {WATCHLIST} — add one per line:  <address> [solana|eth]")
        return
    print(f"watching {len(watch)} wallet(s), interval {args.interval}s")
    if not bot:
        print("TG_BOT_TOKEN not set — printing alerts to console only")

    state = load_state()
    while True:
        for entry in watch:
            alerts = check_wallet(entry, state)
            for a in alerts:
                print("\n" + a + "\n")
                if bot:
                    send_telegram(bot, chat, a)
            save_state(state)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
