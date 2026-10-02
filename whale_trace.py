"""
whale_trace.py — core library
Zero-cost on-chain wallet tracing. No API keys.

Solana: public RPC api.mainnet-beta.solana.com
EVM:    Blockscout public instances
"""
import json
import time
import urllib.request
from dataclasses import dataclass, field

# ------------------------------------------------------------------ config

SOL_RPC = "https://api.mainnet-beta.solana.com"
WRAPPED_SOL = "So11111111111111111111111111111111111111112"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

# Blockscout instances (free, no key)
EVM_RPC = {
    "eth":    "https://eth.blockscout.com/api",
    "base":   "https://base.blockscout.com/api",
    "polygon": "https://polygon.blockscout.com/api",
    "gnosis": "https://gnosis.blockscout.com/api",
}

DEXSCREENER_TOKEN = "https://api.dexscreener.com/latest/dex/tokens/{addr}"
RUGCHECK = "https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
GECKO_TOKEN = "https://api.geckoterminal.com/api/v2/networks/{net}/tokens/{addr}"
GECKO_POOLS = "https://api.geckoterminal.com/api/v2/networks/{net}/tokens/{addr}/pools"
GECKO_OHLCV = "https://api.geckoterminal.com/api/v2/networks/{net}/pools/{pool}/ohlcv/day?limit={limit}"

GECKO_NET = {"solana": "solana", "eth": "eth", "base": "base", "polygon": "polygon"}


# ------------------------------------------------------------------ http

def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "whaletrace/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _post(url, payload, timeout=30):
    """POST with retry/backoff — public RPCs rate-limit aggressively."""
    import urllib.error
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json",
                         "User-Agent": "whaletrace/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except (urllib.error.HTTPError, OSError) as e:
            last = e
            if getattr(e, "code", None) == 429 or attempt < 4:
                time.sleep(min(2.0 * (attempt + 1), 8.0))
                continue
            raise
    raise last


# ------------------------------------------------------------------ models

@dataclass
class Trade:
    ts: int
    side: str               # "BUY" | "SELL" | "SWAP"
    token: str
    token_symbol: str
    amount_token: float
    amount_sol: float       # SOL in (+) / out (-), native units
    tx: str


@dataclass
class TokenPosition:
    mint: str
    symbol: str = ""
    buys: float = 0.0       # total SOL spent
    sells: float = 0.0      # total SOL received
    amount_bought: float = 0.0
    amount_sold: float = 0.0
    last_amount: float = 0.0
    last_ts: int = 0
    trades: list = field(default_factory=list)
    # USD-priced (via GeckoTerminal, no key)
    cost_usd: float = 0.0
    proceeds_usd: float = 0.0
    bag_usd: float = 0.0    # current value of remaining bag

    @property
    def realized_pnl(self) -> float:
        """Native-currency (SOL/ETH) profit on the closed part of the position.

        Only counts when the cost basis is known (bought, not airdropped in).
        This is the on-chain ground truth — USD figures rely on price history
        that is unreliable for low-cap tokens.
        """
        if self.amount_bought <= 0 or self.amount_sold <= 0:
            return 0.0
        avg_cost = self.buys / self.amount_bought if self.amount_bought else 0
        return self.sells - avg_cost * self.amount_sold

    @property
    def realized_pnl_usd(self) -> float:
        # only meaningful when we actually know the cost basis (bought, not airdropped in)
        if self.amount_bought <= 0:
            return 0.0
        return self.proceeds_usd - self.cost_usd

    @property
    def roi_pct(self) -> float:
        cost = self.avg_cost_per_token * self.amount_sold
        if cost <= 0:
            return 0.0
        return (self.sells - cost) / cost * 100.0

    @property
    def avg_cost_per_token(self) -> float:
        return self.buys / self.amount_bought if self.amount_bought else 0.0


# ------------------------------------------------------------------ solana

def _sig_before(arr, before):
    out, seen = [], set()
    for s in arr:
        if before and s["signature"] == before:
            break
        if s["signature"] in seen:
            continue
        seen.add(s["signature"])
        out.append(s)
    return out


def _price_today(mint: str, chain: str = "solana") -> float | None:
    """Current USD price via GeckoTerminal (no key)."""
    net = GECKO_NET.get(chain)
    if not net:
        return None
    try:
        d = _get(GECKO_TOKEN.format(net=net, addr=mint))
        return float(d.get("data", {}).get("attributes", {}).get("price_usd") or 0) or None
    except Exception:
        return None


def _daily_close(mint: str, day_ts: int, chain: str = "solana") -> float | None:
    """USD close price for a given day from OHLCV (free, no key).

    GeckoTerminal keeps a limited daily window, so older trades return None.
    """
    net = GECKO_NET.get(chain)
    if not net:
        return None
    try:
        d = _get(GECKO_POOLS.format(net=net, addr=mint))
        pools = d.get("data") or []
        if not pools:
            return None
        pool_id = pools[0].get("id", "")
        if "_" in pool_id:
            pool_id = pool_id.split("_", 1)[1]
    except Exception:
        return None
    # fetch the window that covers day_ts
    limit = 30
    try:
        d = _get(GECKO_OHLCV.format(net=net, pool=pool_id, limit=limit))
        rows = d.get("data", {}).get("attributes", {}).get("ohlcv_list") or []
    except Exception:
        return None
    for row in rows:
        # [ts, open, high, low, close, volume]
        if row and row[0] and day_ts - row[0] < 86400 and day_ts - row[0] >= 0:
            return float(row[4])
        if row and row[0] and row[0] - day_ts < 86400 and row[0] - day_ts >= 0:
            return float(row[4])
    if rows:
        return float(rows[-1][4])
    return None


def trace_solana(address: str, limit: int = 400, before: str | None = None,
                 verbose: bool = False) -> dict:
    """
    Pull tx history for a Solana wallet and reconstruct per-token trades.

    Returns {"trades": [...], "positions": {mint: TokenPosition}, "stats": {...}}
    """
    r = _post(SOL_RPC, {
        "jsonrpc": "2.0", "id": 1,
        "method": "getSignaturesForAddress",
        "params": [address, {"limit": min(limit, 1000)}],
    })
    sigs = [s for s in r.get("result", []) if s.get("err") is None]
    sigs = _sig_before(sigs, before)
    if verbose:
        print(f"[trace] {len(sigs)} signatures")

    positions: dict[str, TokenPosition] = {}
    trades: list[Trade] = []
    first_ts = None

    for i, s in enumerate(sigs):
        sig = s["signature"]
        try:
            t = _post(SOL_RPC, {
                "jsonrpc": "2.0", "id": 1,
                "method": "getTransaction",
                "params": [sig, {"maxSupportedTransactionVersion": 0}],
            })
        except Exception:
            continue
        res = t.get("result")
        if not res:
            continue
        if verbose and i % 25 == 0:
            print(f"[trace] {i}/{len(sigs)}")

        ts = res.get("blockTime") or 0
        if first_ts is None or ts < first_ts:
            first_ts = ts

        meta = res.get("meta", {})
        pre = {b["accountIndex"]: b for b in meta.get("preTokenBalances", [])}
        post = {b["accountIndex"]: b for b in meta.get("postTokenBalances", [])}
        keys = res["transaction"]["message"]["accountKeys"]
        if address not in keys:
            continue
        my_idx = keys.index(address)

        # deltas for token accounts OWNED by this wallet (ATA rows carry `owner`)
        mints_pre = {}
        mints_post = {}
        for b in meta.get("preTokenBalances", []):
            if (b.get("owner") or b.get("accountOwner")) == address or \
               (b.get("owner") is None and b.get("accountIndex") == my_idx):
                mints_pre[b["mint"]] = b["uiTokenAmount"]["uiAmount"] or 0.0
        for b in meta.get("postTokenBalances", []):
            if (b.get("owner") or b.get("accountOwner")) == address or \
               (b.get("owner") is None and b.get("accountIndex") == my_idx):
                mints_post[b["mint"]] = b["uiTokenAmount"]["uiAmount"] or 0.0

        all_mints = set(mints_pre) | set(mints_post)
        # SOL side of the trade: wSOL balance change is the value flow.
        # (Fallback: native SOL delta, though most wallets hold SOL and pay only fees.)
        try:
            native_pre = meta.get("preBalances", [])[my_idx] / 1e9
            native_post = meta.get("postBalances", [])[my_idx] / 1e9
        except Exception:
            native_pre = native_post = 0.0
        native_delta = native_post - native_pre
        try:
            fee = (meta.get("fee") or 0) / 1e9
        except Exception:
            fee = 0.0
        native_flow = native_delta + fee     # cancel tx fee
        wsol_delta = (mints_post.get(WRAPPED_SOL, 0.0)
                      - mints_pre.get(WRAPPED_SOL, 0.0))

        # pure token<->SOL trade if exactly one non-SOL mint moved and SOL moved opposite
        non_sol_mints = [m for m in all_mints if m != WRAPPED_SOL]
        moved = [m for m in non_sol_mints
                 if abs(mints_post.get(m, 0.0) - mints_pre.get(m, 0.0)) > 1e-9]

        for mint in non_sol_mints:
            pre_amt = mints_pre.get(mint, 0.0)
            post_amt = mints_post.get(mint, 0.0)
            delta = post_amt - pre_amt
            if abs(delta) < 1e-9:
                continue

            pos = positions.setdefault(mint, TokenPosition(mint=mint))
            pos.last_amount = post_amt
            pos.last_ts = ts

            side = "BUY" if delta > 0 else "SELL"
            # SOL side: prefer wSOL delta (DEX routes via wSOL); else native delta.
            # buy  = token in, SOL out (spend positive)
            # sell = token out, SOL in  (proceeds positive)
            sol_val = 0.0
            if delta > 0:
                flow = -wsol_delta if abs(wsol_delta) > 1e-9 else -native_flow
                spend = max(0.0, flow)
                pos.buys += spend
                pos.amount_bought += delta
                sol_val = -spend
            else:
                flow = wsol_delta if abs(wsol_delta) > 1e-9 else native_flow
                got = max(0.0, flow)
                pos.sells += got
                pos.amount_sold += -delta
                sol_val = got

            tr = Trade(ts=ts, side=side, token=mint, token_symbol="",
                       amount_token=abs(delta), amount_sol=sol_val, tx=sig)
            pos.trades.append(tr)
            trades.append(tr)

    # resolve symbols + USD pricing
    for mint, pos in positions.items():
        pos.symbol = _symbol(mint)
        for tr in pos.trades:
            tr.token_symbol = pos.symbol
        # USD pricing via GeckoTerminal (best-effort; skip on failure)
        try:
            if pos.amount_bought > 0:
                px_in = _daily_close(mint, pos.trades[0].ts if pos.trades else int(time.time()))
                if px_in:
                    pos.cost_usd = px_in * pos.amount_bought
            if pos.amount_sold > 0:
                sell_trades = [t for t in pos.trades if t.side == "SELL"]
                px_out = _daily_close(mint, sell_trades[0].ts) if sell_trades else None
                if px_out:
                    pos.proceeds_usd = px_out * pos.amount_sold
            if pos.last_amount > 0:
                px_now = _price_today(mint)
                if px_now:
                    pos.bag_usd = px_now * pos.last_amount
        except Exception:
            pass

    stats = _smart_stats(positions, trades, first_ts, address, unit_label="SOL")
    return {"trades": trades, "positions": positions, "stats": stats}


def _symbol(mint: str) -> str:
    """Best-effort symbol via DexScreener (no key)."""
    try:
        d = _get(DEXSCREENER_TOKEN.format(addr=mint))
        pairs = d.get("pairs") or []
        if pairs:
            return (pairs[0].get("baseToken") or {}).get("symbol") or mint[:6]
    except Exception:
        pass
    return mint[:6]


def _smart_stats(positions, trades, first_ts, address, unit_label: str = "SOL") -> dict:
    closed = [p for p in positions.values() if p.amount_sold > 0]
    # native PnL is ground truth; USD used only for display when available
    wins = [p for p in closed if p.realized_pnl > 0]
    total_realized = sum(p.realized_pnl for p in closed)
    priced_usd = any(p.proceeds_usd or p.cost_usd for p in closed)

    span_days = 0
    if first_ts:
        span_days = max(1, int((time.time() - first_ts) / 86400))

    winrate = len(wins) / len(closed) * 100 if closed else 0.0
    n_tokens = len([p for p in positions.values() if p.amount_bought > 0])
    n_trades = len(trades)
    score = 0.0
    score += min(40.0, winrate / 100 * 40)
    score += min(25.0, min(n_trades, 60) / 60 * 25)
    score += min(20.0, min(n_tokens, 12) / 12 * 20)
    score += min(15.0, min(span_days, 90) / 90 * 15)
    if total_realized < 0:
        score = max(0.0, score - 15)

    return {
        "address": address,
        "trades": n_trades,
        "tokens_traded": n_tokens,
        "closed_positions": len(closed),
        "winrate_pct": round(winrate, 1),
        "realized_pnl": round(total_realized, 2),
        "pnl_unit": "USD" if priced_usd else unit_label,
        "realized_pnl_native": round(total_realized, 3),
        "native_unit": unit_label,
        "span_days": span_days,
        "first_seen": time.strftime("%Y-%m-%d", time.gmtime(first_ts)) if first_ts else None,
        "smart_score": round(score, 1),
    }


# ------------------------------------------------------------------ evm

def trace_evm(address: str, chain: str = "eth", limit: int = 200,
              verbose: bool = False) -> dict:
    """Token transfer history via Blockscout (no key)."""
    base = EVM_RPC.get(chain)
    if not base:
        raise ValueError(f"unsupported chain: {chain}")
    addr = address.lower()

    d = _get(f"{base}?module=account&action=tokentx&address={addr}"
             f"&page=1&offset={min(limit, 500)}&sort=desc")
    rows = d.get("result", [])
    if not isinstance(rows, list):
        rows = []

    positions: dict[str, TokenPosition] = {}
    trades: list[Trade] = []
    first_ts = None

    for row in rows:
        ts = int(row.get("timeStamp") or 0)
        if first_ts is None or ts < first_ts:
            first_ts = ts
        token_addr = (row.get("contractAddress") or "").lower()
        if not token_addr:
            continue
        decimals = int(row.get("tokenDecimal") or 18)
        raw = row.get("value") or "0"
        try:
            amount = int(raw) / (10 ** decimals)
        except Exception:
            continue
        if abs(amount) < 1e-12:
            continue

        direction = "BUY" if (row.get("to") or "").lower() == addr else "SELL"
        pos = positions.setdefault(token_addr, TokenPosition(mint=token_addr,
                                                             symbol=row.get("tokenSymbol") or ""))
        if direction == "BUY":
            pos.buys += 1.0
            pos.amount_bought += amount
        else:
            pos.sells += 1.0
            pos.amount_sold += amount
        pos.last_amount = amount
        pos.last_ts = ts
        trades.append(Trade(ts=ts, side=direction, token=token_addr,
                            token_symbol=pos.symbol, amount_token=amount,
                            amount_sol=0.0, tx=row.get("hash") or ""))

    # EVM tokentx has no price; PnL needs price history — mark as unknown
    stats = _smart_stats(positions, trades, first_ts, address, unit_label="ETH")
    stats["note"] = ("EVM token transfers carry no price; realized PnL is SOL-less. "
                     "Use scan_wallet --price to fetch USD value at buy/sell time.")
    return {"trades": trades, "positions": positions, "stats": stats}


# ------------------------------------------------------------------ safety

def token_safety_solana(mint: str) -> dict:
    """RugCheck summary (no key)."""
    try:
        d = _get(RUGCHECK.format(mint=mint))
        risks = d.get("risks") or []
        return {
            "score": d.get("score_normalised", d.get("score")),
            "lp_locked_pct": d.get("lpLockedPct"),
            "risk_count": len(risks),
            "top_risks": [r.get("description", str(r))[:90] for r in risks[:4]],
            "mint_authority": d.get("mintAuthority"),
            "freeze_authority": d.get("freezeAuthority"),
        }
    except Exception as e:
        return {"error": str(e)[:120]}


def token_info(mint_or_addr: str, chain: str = "solana") -> dict:
    """DexScreener price/mcap/liquidity (no key)."""
    try:
        d = _get(DEXSCREENER_TOKEN.format(addr=mint_or_addr))
        pairs = d.get("pairs") or []
        if not pairs:
            return {"error": "no pairs found"}
        p = pairs[0]
        liq = p.get("liquidity") or {}
        return {
            "symbol": (p.get("baseToken") or {}).get("symbol"),
            "name": (p.get("baseToken") or {}).get("name"),
            "chain": p.get("chainId"),
            "dex": p.get("dexId"),
            "price_usd": p.get("priceUsd"),
            "market_cap": p.get("marketCap"),
            "liquidity_usd": liq.get("usd"),
            "volume_24h": (p.get("volume") or {}).get("h24"),
            "price_change_24h": (p.get("priceChange") or {}).get("h24"),
            "pair_created": p.get("pairCreatedAt"),
        }
    except Exception as e:
        return {"error": str(e)[:120]}
