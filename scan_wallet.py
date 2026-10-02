#!/usr/bin/env python
"""
scan_wallet.py — scan a wallet and print smart-money score + per-token PnL.

Usage:
  python scan_wallet.py <address> --chain solana
  python scan_wallet.py <address> --chain solana --limit 200
  python scan_wallet.py <address> --chain eth --limit 100
"""
import argparse
import time

import whale_trace as w

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELL = "\033[33m"
RESET = "\033[0m"

VERDICTS = [
    (75, "SMART MONEY — worth following"),
    (50, "possibly smart — verify manually"),
    (0, "NOT smart — do not follow"),
]


def verdict(score):
    for thr, label in VERDICTS:
        if score >= thr:
            return label
    return VERDICTS[-1][1]


def colorize(txt, cond):
    if cond is True:
        return f"{GREEN}{txt}{RESET}"
    if cond is False:
        return f"{RED}{txt}{RESET}"
    if cond is None:
        return f"{DIM}{txt}{RESET}"
    return txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("address")
    ap.add_argument("--chain", default="solana",
                    choices=["solana", "eth", "base", "polygon"])
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    print(f"Tracing {args.address[:10]}... on {args.chain} ({args.limit} tx)")
    t0 = time.time()
    if args.chain == "solana":
        r = w.trace_solana(args.address, limit=args.limit)
    else:
        r = w.trace_evm(args.address, limit=args.limit)
    stats = r["stats"]
    unit = stats.get("pnl_unit", "SOL")

    if args.json:
        import json
        out = {k: v for k, v in stats.items()}
        out["positions"] = {
            m: {"symbol": p.symbol, "cost_usd": round(p.cost_usd, 2),
                "proceeds_usd": round(p.proceeds_usd, 2),
                "bag_usd": round(p.bag_usd, 2),
                "realized_usd": round(p.realized_pnl_usd, 2),
                "state": ("CLOSED" if p.amount_sold and not p.last_amount
                          else "HELD" if p.last_amount else "CLOSED")}
            for m, p in r["positions"].items()}
        print(json.dumps(out, indent=2, default=str))
        return

    print()
    print("=" * 66)
    print(f"{BOLD}WALLET  {args.address}{RESET}")
    print("=" * 66)
    print(f"  trades            : {stats['trades']}")
    print(f"  tokens traded     : {stats['tokens_traded']}")
    print(f"  closed positions  : {stats['closed_positions']}")
    win_str = f"{stats['winrate_pct']}%"
    unit = stats.get("native_unit", "SOL")
    pnl_str0 = f"{stats['realized_pnl_native']} {unit}"
    print(f"  winrate           : {colorize(win_str, stats['winrate_pct'] >= 60 if stats['closed_positions'] else None)}")
    print(f"  realized PnL      : {colorize(pnl_str0, stats['realized_pnl_native'] > 0 if stats['closed_positions'] else None)}")
    print(f"  bag value (open)  : ${sum(p.bag_usd for p in r['positions'].values()):,.2f}")
    print(f"  active since      : {stats['first_seen']} ({stats['span_days']} days)")
    print()
    score = stats["smart_score"]
    print(f"  {BOLD}>>> SMART SCORE   : {score}/100  — {verdict(score)}{RESET}")
    print()

    # red flags
    flags = []
    if stats["span_days"] < 7:
        flags.append("short_span: activity spans < 7 days — too little history to judge")
    if stats["closed_positions"] < 3:
        flags.append("few_closes: fewer than 3 closed positions — sample too small")
    if stats["tokens_traded"] == 1:
        flags.append("single_token: only trades one token — insider/dev/bot, not skill")
    if stats["winrate_pct"] < 50 and stats["closed_positions"] >= 3:
        flags.append("losing: winrate below 50% on closed positions")
    if stats["realized_pnl_native"] < 0 and stats["closed_positions"] >= 3:
        flags.append("negative_pnl: losing money overall on closed trades")
    if flags:
        print("  RED FLAGS:")
        for f in flags:
            print(f"    {RED}- {f}{RESET}")
        print()

    print("-" * 66)
    print(f"{BOLD}TOKEN         BUY(SOL)  SELL(SOL)   REALIZED     ROI%    STATE{RESET}")
    print("-" * 66)

    def bag_state(p):
        if p.last_amount > 0:
            return "HELD"
        return "CLOSED"

    items = sorted(r["positions"].items(),
                   key=lambda kv: -(kv[1].bag_usd + kv[1].cost_usd))
    for mint, p in items[:10]:
        realized = p.realized_pnl_usd if p.proceeds_usd else p.realized_pnl
        roistr = f"{p.roi_pct:7.1f}" if p.amount_sold else f"{DIM}{'-':>7}{RESET}"
        pnl_str = f"{realized:>10,.2f}"
        if p.proceeds_usd or p.cost_usd:
            pnl_str = f"$ {p.realized_pnl_usd:>9,.2f}"
        print(f"{p.symbol[:12]:13} {p.buys:>9.2f}  {p.sells:>9.2f}   "
              f"{pnl_str}  {roistr}  {bag_state(p)}")

    if len(items) > 10:
        print(f"showing top 10 of {len(items)} positions")
    print()
    if flags:
        print("NOTE: red flags above seriously reduce copy-trading value.")


if __name__ == "__main__":
    main()
