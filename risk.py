"""
risk.py
Position sizing and risk/reward math.

Author: Matti

This module never decides WHETHER to trade. It only answers:
"IF I trade this, with this stop-loss, how much should I risk to keep
my account safe?" That decision belongs to the trader, always.
"""

from dataclasses import dataclass


@dataclass
class TradePlan:
    symbol: str
    direction: str          # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float     # units/shares
    risk_amount: float       # cash at risk
    reward_amount: float     # cash if target hit
    risk_reward_ratio: float
    account_balance: float
    risk_pct: float


def calculate_stop_and_target(entry_price: float, atr_value: float,
                               direction: str, atr_multiple: float = 1.5,
                               reward_ratio: float = 2.0):
    """
    Derive a stop-loss and take-profit from current volatility (ATR)
    rather than an arbitrary fixed number of points/pips.
    """
    stop_distance = atr_value * atr_multiple

    if direction == "LONG":
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + (stop_distance * reward_ratio)
    else:  # SHORT
        stop_loss = entry_price + stop_distance
        take_profit = entry_price - (stop_distance * reward_ratio)

    return round(stop_loss, 4), round(take_profit, 4)


def position_size_for_risk(account_balance: float, risk_pct: float,
                            entry_price: float, stop_loss: float) -> float:
    """
    Classic fixed-fractional position sizing:
    Only ever risk a fixed % of the account on a single trade,
    regardless of conviction. This is the single most important
    piece of trading risk management there is.
    """
    risk_amount = account_balance * (risk_pct / 100)
    stop_distance = abs(entry_price - stop_loss)
    if stop_distance == 0:
        return 0.0
    size = risk_amount / stop_distance
    return round(size, 6)


def build_trade_plan(symbol: str, direction: str, account_balance: float,
                      risk_pct: float, entry_price: float, atr_value: float,
                      atr_multiple: float = 1.5, reward_ratio: float = 2.0) -> TradePlan:

    stop_loss, take_profit = calculate_stop_and_target(
        entry_price, atr_value, direction, atr_multiple, reward_ratio
    )
    size = position_size_for_risk(account_balance, risk_pct, entry_price, stop_loss)
    risk_amount = account_balance * (risk_pct / 100)
    reward_amount = risk_amount * reward_ratio

    return TradePlan(
        symbol=symbol,
        direction=direction,
        entry_price=round(entry_price, 4),
        stop_loss=stop_loss,
        take_profit=take_profit,
        position_size=size,
        risk_amount=round(risk_amount, 2),
        reward_amount=round(reward_amount, 2),
        risk_reward_ratio=reward_ratio,
        account_balance=account_balance,
        risk_pct=risk_pct,
    )
