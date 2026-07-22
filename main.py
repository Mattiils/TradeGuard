#!/usr/bin/env python3
"""
TradeGuard — a technical-analysis risk & position-sizing assistant.

Author: Matti
GitHub:  https://github.com/<your-github-username>/tradeguard

WHAT THIS IS:
  A decision-SUPPORT tool. It reads current price data, applies standard
  technical indicators, and calculates a risk-managed entry/stop/target
  and position size based on YOUR account balance and risk tolerance.

WHAT THIS IS NOT:
  - Not financial advice. Not a prediction of future price movement.
  - Not an auto-trading bot. It never places trades. You decide, always.
  - Technical indicators describe the past, not the future. Use judgement.

Trading involves real risk of loss. Never risk money you can't afford
to lose, and consider practicing on a demo/paper account first.
"""

import argparse
import sys
from datetime import datetime

__author__ = "Matti"

from data_fetch import fetch_price_data
from indicators import generate_bias, atr
from risk import build_trade_plan
from journal import log_trade, summarize

DISCLAIMER = (
    "\n"
    "==============================================================\n"
    " TradeGuard — informational tool only. NOT financial advice.\n"
    " Indicators reflect past price action, not guaranteed outcomes.\n"
    " You are always the one who decides whether to place a trade.\n"
    "==============================================================\n"
)


def cmd_analyze(args):
    print(DISCLAIMER)
    print(f"Fetching data for {args.symbol} ...")
    df = fetch_price_data(args.symbol, period=args.period)

    if len(df) < 50:
        print("[!] Not enough price history to calculate reliable indicators (need 50+ bars).")
        sys.exit(1)

    bias_info = generate_bias(df)
    atr_value = atr(df).iloc[-1]
    last_price = bias_info["last_price"]

    print(f"\n--- {args.symbol} technical snapshot ({datetime.now():%Y-%m-%d %H:%M}) ---")
    print(f"Last price: {last_price:.4f}")
    print(f"20-period SMA: {bias_info['sma20']:.4f}   50-period SMA: {bias_info['sma50']:.4f}")
    print(f"RSI(14): {bias_info['rsi']:.1f}")
    print(f"ATR(14) [volatility]: {atr_value:.4f}")
    print(f"\nBias: {bias_info['bias']}")
    print("Reasoning:")
    for reason in bias_info["reasons"]:
        print(f"  - {reason}")

    direction = "LONG" if bias_info["score"] >= 0 else "SHORT"

    plan = build_trade_plan(
        symbol=args.symbol,
        direction=direction,
        account_balance=args.balance,
        risk_pct=args.risk_pct,
        entry_price=last_price,
        atr_value=atr_value,
        atr_multiple=args.atr_multiple,
        reward_ratio=args.reward_ratio,
    )

    print(f"\n--- Suggested risk-managed plan (if you chose to take a {direction} trade) ---")
    print(f"Entry:        {plan.entry_price}")
    print(f"Stop-loss:    {plan.stop_loss}   (based on {args.atr_multiple}x ATR)")
    print(f"Take-profit:  {plan.take_profit}   (targets {args.reward_ratio}:1 reward:risk)")
    print(f"Position size: {plan.position_size} units")
    print(f"Amount at risk if stopped out: {plan.risk_amount} ({args.risk_pct}% of balance)")
    print(f"Potential gain if target hit:  {plan.reward_amount}")
    print(
        "\nThis is a calculation based on your inputs and current volatility — "
        "not a signal to enter. Decide based on your own analysis and comfort with risk."
    )


def cmd_log(args):
    balance_after = log_trade(
        symbol=args.symbol,
        direction=args.direction,
        entry_price=args.entry,
        stop_loss=args.stop,
        take_profit=args.target,
        position_size=args.size,
        exit_price=args.exit_price,
        balance_before=args.balance,
        notes=args.notes or "",
    )
    print(f"Trade logged. New balance: {balance_after}")


def cmd_summary(args):
    stats = summarize()
    if stats["trades"] == 0:
        print("No trades logged yet. Use 'log' to add your first trade.")
        return

    print("\n--- Trade Journal Summary ---")
    print(f"Total trades:   {stats['trades']}")
    print(f"Wins / Losses:  {stats['wins']} / {stats['losses']}")
    print(f"Win rate:       {stats['win_rate']}%")
    print(f"Total P&L:      {stats['total_pnl']}")
    print(f"Avg win:        {stats['avg_win']}")
    print(f"Avg loss:       {stats['avg_loss']}")
    print(f"Current balance: {stats['current_balance']}")


def main():
    parser = argparse.ArgumentParser(
        description="TradeGuard — technical analysis + risk management assistant (not financial advice)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="Analyze a symbol and get a risk-managed trade plan.")
    p_analyze.add_argument("symbol", help="e.g. AAPL, TSLA, BTC-USD, ETH-USD")
    p_analyze.add_argument("--balance", type=float, required=True, help="Your current account balance")
    p_analyze.add_argument("--risk-pct", type=float, default=1.0, dest="risk_pct",
                            help="Percent of balance to risk per trade (default 1.0)")
    p_analyze.add_argument("--atr-multiple", type=float, default=1.5, dest="atr_multiple",
                            help="Stop-loss distance as a multiple of ATR (default 1.5)")
    p_analyze.add_argument("--reward-ratio", type=float, default=2.0, dest="reward_ratio",
                            help="Reward:risk ratio for take-profit (default 2.0)")
    p_analyze.add_argument("--period", default="3mo", help="History window: 1mo,3mo,6mo,1y (default 3mo)")
    p_analyze.set_defaults(func=cmd_analyze)

    p_log = sub.add_parser("log", help="Log a completed trade to your journal.")
    p_log.add_argument("symbol")
    p_log.add_argument("direction", choices=["LONG", "SHORT"])
    p_log.add_argument("--entry", type=float, required=True)
    p_log.add_argument("--stop", type=float, required=True)
    p_log.add_argument("--target", type=float, required=True)
    p_log.add_argument("--size", type=float, required=True)
    p_log.add_argument("--exit-price", type=float, required=True, dest="exit_price")
    p_log.add_argument("--balance", type=float, required=True, help="Balance BEFORE this trade")
    p_log.add_argument("--notes", default="")
    p_log.set_defaults(func=cmd_log)

    p_summary = sub.add_parser("summary", help="Show journal performance stats.")
    p_summary.set_defaults(func=cmd_summary)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
