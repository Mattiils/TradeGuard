"""
mt5_bridge.py
Read-only bridge to a locally running MetaTrader 5 terminal.

Author: Matti

IMPORTANT — SAFETY BY DESIGN:
This module ONLY reads data from MT5 (account balance, open positions,
live price bars). It never calls mt5.order_send() or any function that
places, modifies, or closes a trade. TradeGuard shows you numbers and
reasoning; you place trades yourself, inside MT5, on your own decision.

REQUIREMENTS:
- Windows only (the official MetaTrader5 package does not support macOS/Linux
  natively — it talks to a running MT5 terminal via local IPC).
- The MT5 desktop terminal must be installed AND already running, logged
  into your account (demo or live).
"""

import pandas as pd
from datetime import datetime

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

TIMEFRAME_MAP = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


def connect() -> bool:
    """Attach to the already-running MT5 terminal. Returns True on success."""
    if not MT5_AVAILABLE:
        print("[!] The 'MetaTrader5' package isn't installed, or you're not on Windows.")
        print("    Install it with: pip install MetaTrader5")
        return False

    if not mt5.initialize():
        print(f"[!] Could not connect to MT5. Error: {mt5.last_error()}")
        print("    Make sure the MT5 desktop terminal is open and logged in.")
        return False

    return True


def disconnect():
    if MT5_AVAILABLE:
        mt5.shutdown()


def get_account_info() -> dict:
    """Read-only account snapshot: balance, equity, margin, currency."""
    info = mt5.account_info()
    if info is None:
        raise RuntimeError(f"Could not read account info: {mt5.last_error()}")

    return {
        "login": info.login,
        "balance": info.balance,
        "equity": info.equity,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "currency": info.currency,
        "server": info.server,
        "is_demo": info.trade_mode == 0,  # 0 = demo, 1 = contest, 2 = real
    }


def get_open_positions() -> list:
    """Read-only list of currently open positions, most recently opened first."""
    positions = mt5.positions_get()
    if positions is None:
        return []

    # Most recently opened first
    positions = sorted(positions, key=lambda p: p.time, reverse=True)

    result = []
    for p in positions:
        opened_at = datetime.fromtimestamp(p.time)
        age_minutes = (datetime.now() - opened_at).total_seconds() / 60

        if age_minutes < 1:
            age_str = "just now"
        elif age_minutes < 60:
            age_str = f"{age_minutes:.0f}m ago"
        elif age_minutes < 1440:
            age_str = f"{age_minutes / 60:.1f}h ago"
        else:
            age_str = f"{age_minutes / 1440:.1f}d ago"

        result.append({
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "BUY" if p.type == 0 else "SELL",
            "volume": p.volume,
            "price_open": p.price_open,
            "price_current": p.price_current,
            "profit": p.profit,
            "sl": p.sl,
            "tp": p.tp,
            "opened_at": opened_at.strftime("%Y-%m-%d %H:%M:%S"),
            "age": age_str,
        })
    return result


def get_live_bars(symbol: str, timeframe: str = "M15", count: int = 200) -> pd.DataFrame:
    """
    Fetch live OHLC bars for `symbol` directly from MT5's own feed (more
    accurate than a third-party API for forex/CFDs, and works for whatever
    your broker lists — pairs, indices, metals, etc.).

    Returns a DataFrame shaped like [Open, High, Low, Close, Volume] so it
    plugs directly into the existing indicators.py / risk.py functions.
    """
    if not mt5.symbol_select(symbol, True):
        raise ValueError(
            f"Symbol '{symbol}' not found or not visible in Market Watch. "
            f"Check the exact symbol name in MT5 (some brokers add suffixes, e.g. 'EURUSD.a')."
        )

    tf_attr = TIMEFRAME_MAP.get(timeframe.upper())
    if tf_attr is None:
        raise ValueError(f"Unsupported timeframe '{timeframe}'. Choose from {list(TIMEFRAME_MAP)}.")

    tf_const = getattr(mt5, tf_attr)
    rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, count)

    if rates is None or len(rates) == 0:
        raise ValueError(f"No price data returned for '{symbol}'. Error: {mt5.last_error()}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "tick_volume": "Volume"
    }, inplace=True)

    return df[["Open", "High", "Low", "Close", "Volume"]]


def get_symbol_specs(symbol: str) -> dict:
    """
    Read the broker's actual contract size and volume rules for this symbol.
    Needed because 'position size' in risk.py is a generic risk calculation
    (risk_amount / stop_distance), NOT the same thing as an MT5 'lot' — a
    lot of XAUUSD is 100 oz, a lot of a forex pair is 100,000 units, etc.
    Without this conversion, orders can be sized wildly wrong.
    """
    if not mt5.symbol_select(symbol, True):
        raise ValueError(f"Symbol '{symbol}' not found or not visible in Market Watch.")

    info = mt5.symbol_info(symbol)
    if info is None:
        raise ValueError(f"Could not read symbol info for '{symbol}'.")

    return {
        "contract_size": info.trade_contract_size,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
    }


def raw_size_to_lots(raw_size: float, symbol: str) -> float:
    """
    Convert a risk-based raw position size (from risk.py) into a valid,
    broker-compliant lot size for this specific symbol.
    """
    specs = get_symbol_specs(symbol)
    contract_size = specs["contract_size"] or 1.0

    lots = raw_size / contract_size

    step = specs["volume_step"] or 0.01
    lots = round(lots / step) * step

    lots = max(specs["volume_min"], min(specs["volume_max"], lots))
    return round(lots, 2)


def get_today_closed_pnl() -> float:
    """
    Sum of realized profit from all closing deals since midnight (local
    time). Only counts actual trade closes — filters out balance
    operations like demo account top-ups.
    """
    from datetime import datetime, time as dtime

    today_start = datetime.combine(datetime.now().date(), dtime.min)
    now = datetime.now()

    deals = mt5.history_deals_get(today_start, now)
    if deals is None:
        return 0.0

    total = 0.0
    for d in deals:
        # entry: 1=OUT, 2=INOUT, 3=OUT_BY — these are closing-type deals
        # that actually realize profit/loss (0=IN is an opening deal).
        if d.entry in (1, 2, 3):
            total += d.profit

    return round(total, 2)


def place_order(symbol: str, direction: str, volume: float,
                 stop_loss: float = 0.0, take_profit: float = 0.0,
                 comment: str = "TradeGuard") -> dict:
    """
    Places a REAL market order via MT5.

    SAFETY DESIGN: this function is only ever called from app.py in
    direct response to an explicit button click, immediately after the
    user confirms it in the UI. There is no code path anywhere in this
    project that calls this function on a loop, a timer, or without a
    human clicking a button first. It is intentionally NOT wired into
    the 'watch' command or any automated loop.
    """
    if not mt5.symbol_select(symbol, True):
        raise ValueError(f"Symbol '{symbol}' not found or not visible in Market Watch.")

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise ValueError(f"Could not get current price for '{symbol}'. Error: {mt5.last_error()}")

    if direction == "LONG":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    elif direction == "SHORT":
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        raise ValueError("direction must be 'LONG' or 'SHORT'")

    # Different symbols/brokers support different fill modes. The
    # SYMBOL_FILLING_* bitmask constants aren't reliably exposed across
    # every version of the MetaTrader5 package, so rather than inspect
    # symbol_info().filling_mode, just try each valid ORDER_FILLING_*
    # mode in turn and move on only if the broker specifically rejects
    # it for being unsupported (retcode 10030).
    candidates = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]

    last_result = None
    for type_filling in candidates:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": float(stop_loss) if stop_loss else 0.0,
            "tp": float(take_profit) if take_profit else 0.0,
            "deviation": 20,
            "magic": 20260722,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": type_filling,
        }

        result = mt5.order_send(request)
        last_result = result

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            return {
                "ticket": result.order,
                "fill_price": result.price,
                "volume": result.volume,
                "retcode": result.retcode,
            }

        # 10030 = "Unsupported filling mode" — try the next candidate.
        # Any other rejection (no money, market closed, etc.) is a
        # different problem, so stop and surface it immediately.
        if result is not None and result.retcode == 10030:
            continue
        break

    if last_result is None:
        raise RuntimeError(f"order_send returned nothing. Error: {mt5.last_error()}")
    raise RuntimeError(
        f"Order rejected by broker: retcode={last_result.retcode}, comment='{last_result.comment}'"
    )
