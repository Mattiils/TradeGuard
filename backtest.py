"""
backtest.py
A historical backtesting engine for TradeGuard's exact strategy logic —
the same bias calculation and risk-based position sizing used live — run
against past price data to see how it WOULD have performed.

Author: Matti

IMPORTANT — WHAT THIS DOES AND DOESN'T PROVE:
- It shows how this specific rule-based approach performed on specific
  historical data. That's real, checkable evidence, not a guess.
- It is NOT proof of future profitability. Markets change over time
  (this is often called "regime change"). A strategy that performed
  well on the last 2 years of data can simply stop working, and no
  backtest can rule that out in advance.
- It does NOT model spread, commission, slippage, or requotes — real
  trading costs that make live results worse than backtested ones,
  sometimes significantly so.
- Small trade counts produce unreliable statistics. Treat a backtest
  with fewer than ~30 trades as a rough sketch, not a verdict.
- At every decision point, only price data up to and including that
  point is used (no lookahead) — this is what makes the simulation
  honest rather than accidentally "cheating" with future information.
"""

from dataclasses import dataclass
import pandas as pd

from indicators import generate_bias, atr
from risk import build_trade_plan


@dataclass
class BacktestTrade:
    entry_date: str
    exit_date: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    pnl: float
    exit_reason: str  # "stop", "target", or "time" (max holding period reached)


def run_backtest(df: pd.DataFrame, symbol: str, starting_balance: float = 1000.0,
                  risk_pct: float = 1.0, atr_multiple: float = 1.5,
                  reward_ratio: float = 2.0, bias_threshold: float = 1.0,
                  max_holding_bars: int = 20, min_history_bars: int = 60) -> dict:
    """
    Walk through df bar by bar. At each point, only data up to and including
    that bar is used to decide whether to enter a trade — no lookahead.
    Simulates one open position at a time (keeps the simulation simple and
    directly comparable to how a careful single-position trader would act).
    """
    balance = starting_balance
    equity_curve = [(df.index[min_history_bars], balance)]
    trades = []

    i = min_history_bars
    n = len(df)

    while i < n - 1:
        window = df.iloc[:i + 1]
        try:
            bias_info = generate_bias(window)
            atr_value = atr(window).iloc[-1]
        except Exception:
            i += 1
            continue

        score = bias_info["score"]

        if abs(score) >= bias_threshold:
            direction = "LONG" if score > 0 else "SHORT"
            entry_price = bias_info["last_price"]
            plan = build_trade_plan(
                symbol=symbol, direction=direction, account_balance=balance,
                risk_pct=risk_pct, entry_price=entry_price, atr_value=atr_value,
                atr_multiple=atr_multiple, reward_ratio=reward_ratio,
            )

            exit_price = None
            exit_reason = "time"
            exit_idx = min(i + max_holding_bars, n - 1)

            for j in range(i + 1, exit_idx + 1):
                bar = df.iloc[j]
                if direction == "LONG":
                    hit_stop = bar["Low"] <= plan.stop_loss
                    hit_target = bar["High"] >= plan.take_profit
                else:
                    hit_stop = bar["High"] >= plan.stop_loss
                    hit_target = bar["Low"] <= plan.take_profit

                # If both could have been hit in the same bar, assume the
                # worse outcome (stop first) — a standard conservative
                # convention since we can't know the true intra-bar order.
                if hit_stop:
                    exit_price = plan.stop_loss
                    exit_reason = "stop"
                    exit_idx = j
                    break
                elif hit_target:
                    exit_price = plan.take_profit
                    exit_reason = "target"
                    exit_idx = j
                    break

            if exit_price is None:
                exit_price = df.iloc[exit_idx]["Close"]
                exit_reason = "time"

            if direction == "LONG":
                pnl = (exit_price - entry_price) * plan.position_size
            else:
                pnl = (entry_price - exit_price) * plan.position_size

            balance += pnl
            trades.append(BacktestTrade(
                entry_date=str(df.index[i]), exit_date=str(df.index[exit_idx]),
                direction=direction, entry_price=round(entry_price, 5),
                exit_price=round(exit_price, 5), stop_loss=plan.stop_loss,
                take_profit=plan.take_profit, position_size=plan.position_size,
                pnl=round(pnl, 2), exit_reason=exit_reason,
            ))
            equity_curve.append((df.index[exit_idx], round(balance, 2)))
            i = exit_idx + 1
        else:
            i += 1

    return _summarize(trades, starting_balance, balance, equity_curve)


def _summarize(trades, starting_balance, ending_balance, equity_curve) -> dict:
    if not trades:
        return {
            "trades": 0, "starting_balance": starting_balance,
            "ending_balance": starting_balance, "total_return_pct": 0.0,
            "win_rate": 0, "max_drawdown_pct": 0, "profit_factor": 0,
            "avg_win": 0, "avg_loss": 0, "trade_log": [], "equity_curve": equity_curve,
        }

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]

    peak = starting_balance
    max_dd = 0.0
    for _, bal in equity_curve:
        peak = max(peak, bal)
        dd = (peak - bal) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)

    total_return_pct = (ending_balance - starting_balance) / starting_balance * 100
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "starting_balance": starting_balance,
        "ending_balance": round(ending_balance, 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else "∞ (no losing trades)",
        "avg_win": round(gross_win / len(wins), 2) if wins else 0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0,
        "trade_log": trades,
        "equity_curve": equity_curve,
    }
