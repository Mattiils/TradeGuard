"""
journal.py
A simple CSV-backed trade journal and running balance tracker.

Author: Matti

Logging every trade (not just the wins) is what actually improves a
trader over time — this module makes that nearly effortless.
"""

import csv
import os
from datetime import datetime

JOURNAL_FILE = "trade_journal.csv"
FIELDNAMES = [
    "timestamp", "symbol", "direction", "entry_price", "stop_loss",
    "take_profit", "position_size", "exit_price", "result", "pnl",
    "balance_after", "notes"
]


def ensure_journal_exists(path: str = JOURNAL_FILE):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_trade(symbol: str, direction: str, entry_price: float, stop_loss: float,
              take_profit: float, position_size: float, exit_price: float,
              balance_before: float, notes: str = "", path: str = JOURNAL_FILE) -> float:
    """
    Log a completed trade and return the new balance.
    PnL is calculated automatically from entry/exit/size/direction.
    """
    ensure_journal_exists(path)

    if direction == "LONG":
        pnl = (exit_price - entry_price) * position_size
    else:  # SHORT
        pnl = (entry_price - exit_price) * position_size

    pnl = round(pnl, 2)
    result = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")
    balance_after = round(balance_before + pnl, 2)

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_size": position_size,
            "exit_price": exit_price,
            "result": result,
            "pnl": pnl,
            "balance_after": balance_after,
            "notes": notes,
        })

    return balance_after


def summarize(path: str = JOURNAL_FILE) -> dict:
    """Return simple performance stats from the journal."""
    ensure_journal_exists(path)

    with open(path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return {"trades": 0}

    wins = [r for r in rows if r["result"] == "WIN"]
    losses = [r for r in rows if r["result"] == "LOSS"]
    total_pnl = sum(float(r["pnl"]) for r in rows)
    win_rate = (len(wins) / len(rows)) * 100 if rows else 0
    avg_win = (sum(float(r["pnl"]) for r in wins) / len(wins)) if wins else 0
    avg_loss = (sum(float(r["pnl"]) for r in losses) / len(losses)) if losses else 0
    current_balance = float(rows[-1]["balance_after"])

    return {
        "trades": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "current_balance": current_balance,
    }
