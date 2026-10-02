<div align="center">

# 🐋 WhaleTrace

**Trace smart money. Free. No API keys. Ever.**

Zero-cost on-chain wallet profiler. Find the wallets that actually profit, score them, and get pinged the moment they buy.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Zero API Keys](https://img.shields.io/badge/API%20keys-0-success.svg)](#-why-this-exists)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/ujanggantung/whale-trace?style=social)](https://github.com/ujanggantung/whale-trace/stargazers)
[![Last Commit](https://img.shields.io/github/last-commit/ujanggantung/whale-trace)](https://github.com/ujanggantung/whale-trace/commits/main)

</div>

---

## 🫠 The problem

Every on-chain wallet tool is either:

1. **Expensive** — Arkham, Nansen, Debank: $50–$400/month, paywalled behind enterprise tiers.
2. **Useless at the moment you need it** — DEXScreener shows prices, not traders. You can't type a wallet into DEXScreener.
3. **A black box** — "smart money" score from a proprietary algorithm. You can't see the formula, can't audit it, can't disagree.

So I wrote my own.

## ✨ What it does

**Three files of Python. Pure standard library. No API keys. No dependencies.**

| Tool | What it does |
| --- | --- |
| `scan_wallet.py` | Score any wallet 0–100 in seconds. Winrate, realized PnL, bag value, red flags. |
| `watch.py` | Live monitor. Poll a watchlist, get alerted when a wallet buys. |
| `whale_trace.py` | The engine. Drop-in library for your own bot/script/agent. |

## 🚀 Quick start

```bash
git clone https://github.com/ujanggantung/whale-trace.git
cd whale-trace
python scan_wallet.py 8Jkx8w2dDwwSdju4frFRCvHrMax2ZV2DvKYRZC6jAHEK --chain solana
```

That's the whole install. No `pip install`. No config file. No keys.

**The output is brutal:**

```
==================================================================
WALLET  8Jkx8w2dDwwSdju4frFRCvHrMax2ZV2DvKYRZC6jAHEK
==================================================================
  trades            : 58
  tokens traded     : 22
  closed positions  : 18
  winrate           : 44.4%
  realized PnL      : 2.683 SOL
  bag value (open)  : $195.48
  active since      : 2026-10-02 (1 days)

  >>> SMART SCORE   : 62.1/100  — possibly smart — verify manually

  RED FLAGS:
    - short_span: activity spans < 7 days — too little history to judge
    - losing: winrate below 50% on closed positions
```

**44% winrate. 1 day old. Don't follow.**

## 📊 The scoring formula (it's open)

No proprietary black box. The score is simple, auditable, and you can disagree with it:

| Factor | Max points | Why |
| --- | --- | --- |
| **Winrate** on closed trades | 40 | The obvious one. How often do they sell above cost? |
| **Trade volume** | 25 | Not skill alone, but 50+ trades is a track record, not a fluke. |
| **Breadth** — tokens traded | 20 | One-token wallets are devs/insiders, not traders. Skill generalizes. |
| **Age** — days active | 15 | A wallet needs 3+ months to prove it survives regimes. |
| **Losing money** | −15 | Penalize overall negative realized PnL. |

** ≥ 70 = smart. 50–70 = investigate. <50 = don't follow.**

The **red flags** matter as much as the number. Short span, one-token-only, negative PnL — each one is a way to lose money following someone else's luck.

## 🧠 Why on-chain PnL, not USD

Most tools price PnL in USD. That's wrong for low-cap memecoins — the daily price feeds are unreliable or straight-up missing.

So realized PnL is computed in **the gas/quote asset the wallet actually traded with** — SOL on Solana, ETH on EVM L1s. `amount received − amount spent`. That's ground truth, straight from the ledger, no oracle needed.

A wallet that spent 100 SOL and took back 150 SOL is up 50 SOL. USD is a display nicety. On-chain is the math.

## ⚠️ On "smart money"

A high score is not a buy signal. Read the red flags:

- **One token only** → probably the dev, or the dev's mom. Not skill.
- **1-day-old wallet** → no sample size. Anyone can win for a day.
- **Never sells** → unrealized gains are a fairy tale. Paper wealth is not money.
- **Huge bags on a 1-token wallet** → founder allocation, not conviction.

Smart wallets are also **not** always active. The best ones buy red candles, sell green ones, and go quiet for a month. WhaleTrace shows you *who* to watch, not *what* to buy. The watch script handles the "when".

## 🔔 Live monitor

Add wallets to `watchlist.txt`, one per line:

```
8Jkx8w2dDwwSdju4frFRCvHrMax2ZV2DvKYRZC6jAHEK solana
0xYOUR_TARGET_WALLET eth
0xANOTHER_ONE base
```

Then:

```bash
python watch.py                    # polls every 5 minutes
```

Or double-click `start_monitor.bat` on Windows.

First poll seeds history **silently**. On every subsequent poll, when a wallet buys something, you get the full picture before anyone else opens a chart:

```
*NEW BUY* `8Jkx8...AHEK`
Token: *DIT*
Size: 11,686,915.40 DIT
Market cap: $0.01M
Liquidity: $7,083
Holders: 123
Top-5 holders: 42.1%
RugCheck: 495 (OK)
Risks: Low Liquidity
https://solscan.io/tx/3oz1...
```

Market cap, liquidity, holder concentration, top-5 %, RugCheck score and its named risks — in one alert, before you even open Solscan.

### Telegram alerts (optional)

Create a free bot with [@BotFather](https://t.me/BotFather) (30 seconds), then:

```bash
export TG_BOT_TOKEN="123456:ABC-DEF..."
export TG_CHAT_ID="your-chat-id"
python watch.py
```

Without tokens, alerts print to the console. Either way, no data leaves your machine.

## 🧩 Data sources (all public, all free)

| Need | Source | Key? |
| --- | --- | --- |
| Solana transactions | Solana public RPC `api.mainnet-beta.solana.com` | No |
| EVM transactions | Blockscout public instances (ETH, Base, Polygon, Gnosis) | No |
| Token info / liquidity | DEXScreener | No |
| Price + pool data | GeckoTerminal | No |
| Token safety | RugCheck.xyz | No |

Nothing to sign up for. Nothing to lose if a key leaks. No rate-limit surprise bills.

> **Tip:** the public Solana RPC is shared, so it 429s on bursts. `whale_trace.py` already retries with backoff. For a dedicated endpoint, Helius or QuickNode (both have free tiers with keys) can drop in by changing `SOL_RPC` at the top of `whale_trace.py`.

## 🔧 As a library

```python
from whale_trace import trace_solana, trace_evm

r = trace_solana("8Jkx...", limit=100)
print(r["stats"]["smart_score"])   # -> 62.1
print(r["stats"]["winrate_pct"])   # -> 42.3

for pos in r["positions"].values():
    print(pos.symbol, pos.realized_pnl, pos.roi_pct)
```

Works the same for EVM: `trace_evm("0x...", chain="base")`.

## ✅ Roadmap

- [ ] EVM realized PnL in ETH (Blockscout traces)
- [ ] Cluster detection — flag wallets that only interact with each other
- [ ] Snapshot + diff mode — track how a wallet's positions change
- [ ] CSV/JSON export of trades and positions
- [ ] More chains (BSC, Arbitrum, Optimism)

Have an idea? Open an issue — I read them.

## 🤔 FAQ

**How is this free?**

Every source is a public endpoint. The code is standard library Python. There's nothing to meter.

**Is this financial advice?**

No. It reads public ledgers and does arithmetic. If you lose money following a wallet that was winning, that's on you. Markets do that.

**It 429'd me.**

Yeah, that's the shared RPC. The retry/backoff handles most of it. If it's a real problem, swap `SOL_RPC` for a free Helius/QuickNode key.

## ⭐ If this saved you a Nansen subscription

Star the repo. That's the only currency this project takes.

Star history:

[![Star History Chart](https://api.star-history.com/svg?repos=ujanggantung/whale-trace&type=Date)](https://star-history.com/#ujanggantung/whale-trace&Date)

<div align="center">

**Made with pure stdlib and questionable sleep schedules.**

</div>
