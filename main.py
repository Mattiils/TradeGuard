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
import time
import os
from datetime import datetime

__author__ = "Matti"

from data_fetch import fetch_price_data
from indicators import generate_bias, atr
from risk import build_trade_plan
from journal import log_trade, summarize
from backtest import run_backtest
import mt5_bridge

DISCLAIMER = (
    "\n"
    "==============================================================\n"
    " TradeGuard by Matti — informational tool only. NOT financial advice.\n"
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
    print(f"ADX(14) [trend strength]: {bias_info['adx']:.1f}")
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


def cmd_backtest(args):
    print(
        "\n=================================================================\n"
        " BACKTEST — historical simulation only. This shows how the\n"
        " strategy WOULD have performed on past data. It is NOT proof of\n"
        " future results. Markets change; small trade counts are noisy;\n"
        " spread/commission/slippage are not modeled here.\n"
        "=================================================================\n"
    )
    print(f"Fetching {args.period} of history for {args.symbol} ...")
    df = fetch_price_data(args.symbol, period=args.period, interval=args.interval)

    if len(df) < 80:
        print("[!] Not enough history for a meaningful backtest (need 80+ bars).")
        sys.exit(1)

    results = run_backtest(
        df, symbol=args.symbol, starting_balance=args.balance,
        risk_pct=args.risk_pct, atr_multiple=args.atr_multiple,
        reward_ratio=args.reward_ratio, bias_threshold=args.bias_threshold,
        max_holding_bars=args.max_holding_bars,
    )

    if results["trades"] == 0:
        print("No trades were triggered over this period at the current threshold.")
        print("Try a lower --bias-threshold, a longer --period, or a different symbol.")
        return

    print(f"--- Backtest results: {args.symbol} ({args.period}, {args.interval}) ---")
    print(f"Trades:          {results['trades']}  (wins: {results['wins']}, losses: {results['losses']})")
    print(f"Win rate:        {results['win_rate']}%")
    print(f"Starting balance: {results['starting_balance']}")
    print(f"Ending balance:   {results['ending_balance']}")
    print(f"Total return:     {results['total_return_pct']}%")
    print(f"Max drawdown:     {results['max_drawdown_pct']}%")
    print(f"Profit factor:    {results['profit_factor']}  (gross win / gross loss — above 1 means net profitable in this test)")
    print(f"Avg win:          {results['avg_win']}")
    print(f"Avg loss:         {results['avg_loss']}")

    if results["trades"] < 30:
        print(
            f"\n⚠️ Only {results['trades']} trades — treat these numbers as a rough sketch, "
            f"not a reliable statistic. Try a longer --period for more trades."
        )

    if args.show_trades:
        print("\n--- Trade log ---")
        for t in results["trade_log"]:
            print(f"{t.entry_date[:10]} -> {t.exit_date[:10]} | {t.direction} | "
                  f"entry {t.entry_price} exit {t.exit_price} | pnl {t.pnl} | exit: {t.exit_reason}")


def _print_watch_dashboard(symbols, args):
    account = mt5_bridge.get_account_info()
    positions = mt5_bridge.get_open_positions()

    print(DISCLAIMER)
    print(f"MT5 account #{account['login']} on {account['server']} "
          f"({'DEMO' if account['is_demo'] else 'LIVE'})")
    print(f"Balance: {account['balance']} {account['currency']}   "
          f"Equity: {account['equity']} {account['currency']}   "
          f"Free margin: {account['margin_free']}")

    if positions:
        print(f"\nOpen positions ({len(positions)}):")
        for p in positions:
            print(f"  {p['symbol']} {p['type']} {p['volume']} lots | "
                  f"open {p['price_open']} -> now {p['price_current']} | "
                  f"P&L: {p['profit']}")
    else:
        print("\nNo open positions.")

    for symbol in symbols:
        try:
            df = mt5_bridge.get_live_bars(symbol, timeframe=args.timeframe, count=200)
            if len(df) < 50:
                print(f"\n{symbol}: not enough history yet on this timeframe.")
                continue

            bias_info = generate_bias(df)
            atr_value = atr(df).iloc[-1]
            last_price = bias_info["last_price"]
            direction = "LONG" if bias_info["score"] >= 0 else "SHORT"

            plan = build_trade_plan(
                symbol=symbol,
                direction=direction,
                account_balance=account["balance"],
                risk_pct=args.risk_pct,
                entry_price=last_price,
                atr_value=atr_value,
                atr_multiple=args.atr_multiple,
                reward_ratio=args.reward_ratio,
            )

            print(f"\n--- {symbol} ({args.timeframe}) ---")
            print(f"Price: {last_price:.5f}   RSI: {bias_info['rsi']:.1f}   Bias: {bias_info['bias']}")
            for reason in bias_info["reasons"]:
                print(f"  - {reason}")
            print(f"  If {direction}: entry {plan.entry_price} | stop {plan.stop_loss} | "
                  f"target {plan.take_profit} | size {plan.position_size} | "
                  f"risking {plan.risk_amount} {account['currency']}")

        except Exception as e:
            print(f"\n{symbol}: could not analyze ({e})")

    print(f"\nLast updated: {datetime.now():%Y-%m-%d %H:%M:%S} — Ctrl+C to stop.")


def cmd_watch(args):
    if not mt5_bridge.connect():
        sys.exit(1)

    try:
        symbols = args.symbols
        while True:
            if not args.no_clear:
                os.system("cls" if os.name == "nt" else "clear")
            _print_watch_dashboard(symbols, args)

            if args.once:
                break
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n\nStopped. No trades were placed — this tool never places trades automatically.")
    finally:
        mt5_bridge.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description="TradeGuard by Matti — technical analysis + risk management assistant (not financial advice)."
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

    p_watch = sub.add_parser(
        "watch",
        help="Live-monitor symbols using your real MT5 account balance & positions (read-only)."
    )
    p_watch.add_argument("symbols", nargs="+", help="e.g. EURUSD GBPUSD XAUUSD (exact MT5 symbol names)")
    p_watch.add_argument("--risk-pct", type=float, default=1.0, dest="risk_pct")
    p_watch.add_argument("--atr-multiple", type=float, default=1.5, dest="atr_multiple")
    p_watch.add_argument("--reward-ratio", type=float, default=2.0, dest="reward_ratio")
    p_watch.add_argument("--timeframe", default="M15", help="M1,M5,M15,M30,H1,H4,D1 (default M15)")
    p_watch.add_argument("--interval", type=int, default=30, help="Refresh interval in seconds (default 30)")
    p_watch.add_argument("--once", action="store_true", help="Run a single snapshot instead of looping")
    p_watch.add_argument("--no-clear", action="store_true", help="Don't clear the screen between refreshes")
    p_watch.set_defaults(func=cmd_watch)

    p_backtest = sub.add_parser(
        "backtest",
        help="Test this exact strategy against historical data (not proof of future results)."
    )
    p_backtest.add_argument("symbol", help="e.g. AAPL, BTC-USD, EURUSD=X")
    p_backtest.add_argument("--balance", type=float, default=1000.0)
    p_backtest.add_argument("--risk-pct", type=float, default=1.0, dest="risk_pct")
    p_backtest.add_argument("--atr-multiple", type=float, default=1.5, dest="atr_multiple")
    p_backtest.add_argument("--reward-ratio", type=float, default=2.0, dest="reward_ratio")
    p_backtest.add_argument("--bias-threshold", type=float, default=1.0, dest="bias_threshold")
    p_backtest.add_argument("--period", default="2y", help="e.g. 6mo, 1y, 2y, 5y (default 2y)")
    p_backtest.add_argument("--interval", default="1d", help="e.g. 1d, 1h (default 1d)")
    p_backtest.add_argument("--max-holding-bars", type=int, default=20, dest="max_holding_bars")
    p_backtest.add_argument("--show-trades", action="store_true", dest="show_trades")
    p_backtest.set_defaults(func=cmd_backtest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
