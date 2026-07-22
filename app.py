"""
app.py
TradeGuard — visual dashboard (Streamlit).

Author: Matti

Run with:
    streamlit run app.py

This is a visual front-end over the same engine as main.py (identical
indicators, risk math, and journal). It never places trades — it only
displays live data and calculations for you to act on yourself.
"""

import time
from datetime import datetime

import streamlit as st
import pandas as pd

from data_fetch import fetch_price_data
from indicators import generate_bias, atr
from risk import build_trade_plan
from journal import log_trade, summarize, ensure_journal_exists, log_execution, JOURNAL_FILE
from backtest import run_backtest
import mt5_bridge

st.set_page_config(page_title="TradeGuard by Matti", page_icon="📈", layout="wide")

# ----------------------------------------------------------------------
# Session state defaults
# ----------------------------------------------------------------------
if "mt5_connected" not in st.session_state:
    st.session_state.mt5_connected = False
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None
if "trades_this_session" not in st.session_state:
    st.session_state.trades_this_session = 0
if "auto_trading_active" not in st.session_state:
    st.session_state.auto_trading_active = False
if "auto_session_start_equity" not in st.session_state:
    st.session_state.auto_session_start_equity = None
if "auto_traded_symbols" not in st.session_state:
    st.session_state.auto_traded_symbols = {}  # symbol -> datetime of last auto-trade
if "session_start_balance" not in st.session_state:
    st.session_state.session_start_balance = None


def render_disclaimer():
    st.warning(
        "**Not financial advice.** TradeGuard shows technical indicators and "
        "risk calculations based on past price action — it never predicts the "
        "future and never places trades. You always decide.",
        icon="⚠️",
    )


def render_bias_card(symbol, bias_info, atr_value, plan, direction, currency="$",
                      allow_execution=False, account_mode=None, max_trades=5):
    bias = bias_info["bias"]
    color = "green" if "BULLISH" in bias else ("red" if "BEARISH" in bias else "gray")

    with st.container(border=True):
        col1, col2 = st.columns([2, 3])
        with col1:
            st.subheader(symbol)
            st.markdown(f":{color}[**{bias}**]  (score: {bias_info['score']:+.2f})")
            st.metric("Price", f"{bias_info['last_price']:.4f}")
            st.metric("RSI(14)", f"{bias_info['rsi']:.1f}")
            adx_label = "weak" if bias_info["adx"] < 20 else ("emerging" if bias_info["adx"] < 25 else "confirmed")
            st.metric("ADX (trend strength)", f"{bias_info['adx']:.1f} ({adx_label})")

        with col2:
            st.markdown("**Reasoning:**")
            for r in bias_info["reasons"]:
                st.markdown(f"- {r}")

            st.markdown(f"**If {direction}:**")
            c1, c2, c3 = st.columns(3)
            c1.metric("Entry", f"{plan.entry_price}")
            c2.metric("Stop-loss", f"{plan.stop_loss}")
            c3.metric("Take-profit", f"{plan.take_profit}")
            c4, c5 = st.columns(2)
            c4.metric("Position size", f"{plan.position_size}")
            c5.metric("Risking", f"{currency}{plan.risk_amount}")

        if allow_execution:
            st.divider()
            if st.session_state.trades_this_session >= max_trades:
                st.warning(f"Session limit of {max_trades} executions reached. Restart the app to reset.")
            else:
                if account_mode == "LIVE":
                    st.error("🔴 This is a LIVE account. Real money.", icon="🔴")
                    confirm_text = st.text_input(
                        f"Type EXECUTE to confirm this {direction} {symbol} trade on your LIVE account:",
                        key=f"confirm_{symbol}"
                    )
                    can_execute = confirm_text.strip().upper() == "EXECUTE"
                else:
                    can_execute = True

                if st.button(f"🚀 Execute {direction} {symbol} now", key=f"exec_{symbol}",
                              disabled=not can_execute, type="primary"):
                    try:
                        result = mt5_bridge.place_order(
                            symbol=symbol, direction=direction,
                            volume=round(plan.position_size, 2),
                            stop_loss=plan.stop_loss, take_profit=plan.take_profit,
                        )
                        log_execution(
                            symbol=symbol, direction=direction, volume=result["volume"],
                            fill_price=result["fill_price"], stop_loss=plan.stop_loss,
                            take_profit=plan.take_profit, ticket=result["ticket"],
                            account_mode=account_mode, trigger="manual",
                        )
                        st.session_state.trades_this_session += 1
                        st.success(f"✅ Order placed. Ticket #{result['ticket']} filled at {result['fill_price']}")
                    except Exception as e:
                        st.error(f"Order failed: {e}")


# ----------------------------------------------------------------------
# Sidebar controls
# ----------------------------------------------------------------------
st.sidebar.title("📈 TradeGuard by Matti")
data_source = st.sidebar.radio("Data source", ["MT5 (live account)", "Yahoo Finance (no MT5 needed)"])

scalper_mode = False
if data_source == "MT5 (live account)":
    scalper_mode = st.sidebar.checkbox("⚡ Scalper mode (M1, tighter stops)")

risk_pct = st.sidebar.slider("Risk % per trade", 0.1, 5.0, 1.0, 0.1)
atr_multiple = st.sidebar.slider("Stop-loss ATR multiple", 0.5, 4.0, 0.8 if scalper_mode else 1.5, 0.1)
reward_ratio = st.sidebar.slider("Reward:Risk ratio", 1.0, 5.0, 1.5 if scalper_mode else 2.0, 0.5)

if data_source == "MT5 (live account)":
    symbols_input = st.sidebar.text_input("Symbols (comma-separated)", "EURUSD, GBPUSD")
    default_tf_index = 0 if scalper_mode else 2
    timeframe = st.sidebar.selectbox(
        "Timeframe", ["M1", "M5", "M15", "M30", "H1", "H4", "D1"], index=default_tf_index
    )
else:
    symbols_input = st.sidebar.text_input("Symbols (comma-separated)", "AAPL, BTC-USD")
    manual_balance = st.sidebar.number_input("Account balance", min_value=1.0, value=1000.0, step=100.0)

auto_refresh = st.sidebar.checkbox("Auto-refresh")
refresh_seconds = st.sidebar.slider("Refresh every (seconds)", 10, 120, 15 if scalper_mode else 30) if auto_refresh else None

refresh_clicked = st.sidebar.button("🔄 Refresh now", use_container_width=True)

st.sidebar.divider()
st.sidebar.markdown("### ⚠️ Trade execution")
execution_mode = st.sidebar.radio("Mode", ["Manual (click to execute)", "Auto (demo accounts only)"])
execution_enabled = st.sidebar.checkbox(
    "I understand execution places REAL orders on my MT5 account and is irreversible."
)
max_trades_session = st.sidebar.number_input(
    "Max executions this session", min_value=1, max_value=50, value=5,
    help="A hard limit to stop runaway clicking/auto-trading — resets if you restart the app."
)

auto_mode_selected = execution_mode.startswith("Auto")
if auto_mode_selected:
    bias_threshold = st.sidebar.slider(
        "Auto-trade bias strength threshold", 1.0, 2.5, 1.5, 0.25,
        help="Only auto-fires when the bias score's absolute value meets this bar — higher = stricter."
    )
    max_daily_loss_pct = st.sidebar.slider(
        "Kill-switch: max session drawdown %", 1.0, 20.0, 5.0, 0.5,
        help="Auto-trading stops itself if equity drops this much from where it started this session."
    )
    reentry_cooldown_minutes = st.sidebar.slider(
        "Re-entry cooldown per symbol (minutes)", 0, 240, 15, 5,
        help="After auto-trading a symbol, wait this long before it's allowed to fire on that "
             "same symbol again — stops rapid re-entry right after a quick stop-out, without "
             "blocking it for the rest of the session. Set to 0 to disable the cooldown entirely."
    )

symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

# ----------------------------------------------------------------------
# Tabs
# ----------------------------------------------------------------------
tab_dashboard, tab_journal, tab_backtest = st.tabs(["Live Dashboard", "Trade Journal", "Backtest"])

with tab_dashboard:
    render_disclaimer()

    if data_source == "MT5 (live account)":
        if st.button("🔌 Connect to MT5"):
            st.session_state.mt5_connected = mt5_bridge.connect()

        if not st.session_state.mt5_connected:
            st.info("Click **Connect to MT5** above. Make sure the MT5 desktop terminal is open and logged in.")
        else:
            try:
                account = mt5_bridge.get_account_info()
                positions = mt5_bridge.get_open_positions()

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Balance", f"{account['balance']} {account['currency']}")
                c2.metric("Equity", f"{account['equity']} {account['currency']}")
                c3.metric("Free margin", f"{account['margin_free']}")
                c4.metric("Mode", "DEMO" if account["is_demo"] else "LIVE")

                if st.session_state.session_start_balance is None:
                    st.session_state.session_start_balance = account["balance"]

                floating_pnl = sum(p["profit"] for p in positions)
                try:
                    closed_pnl_today = mt5_bridge.get_today_closed_pnl()
                except Exception:
                    closed_pnl_today = None

                start_balance = st.session_state.session_start_balance
                session_pnl = account["equity"] - start_balance
                session_pnl_pct = (session_pnl / start_balance * 100) if start_balance else 0

                st.markdown("### 💰 P&L Summary")
                pc1, pc2, pc3, pc4 = st.columns(4)
                pc1.metric(
                    "Since you connected",
                    f"{session_pnl:+.2f} {account['currency']}",
                    f"{session_pnl_pct:+.2f}%",
                )
                pc2.metric("Open positions (floating)", f"{floating_pnl:+.2f} {account['currency']}")
                if closed_pnl_today is not None:
                    pc3.metric("Closed today (realized)", f"{closed_pnl_today:+.2f} {account['currency']}")
                    pc4.metric("Total today", f"{(closed_pnl_today + floating_pnl):+.2f} {account['currency']}")
                else:
                    pc3.metric("Closed today (realized)", "N/A")

                if st.button("↺ Reset 'since you connected' baseline"):
                    st.session_state.session_start_balance = account["balance"]
                    st.rerun()

                if positions:
                    st.markdown("### Open positions (most recent first)")
                    positions_df = pd.DataFrame(positions)
                    column_order = ["symbol", "type", "age", "opened_at", "volume",
                                    "price_open", "price_current", "profit", "sl", "tp", "ticket"]
                    positions_df = positions_df[[c for c in column_order if c in positions_df.columns]]
                    st.dataframe(positions_df, use_container_width=True)
                else:
                    st.markdown("*No open positions.*")

                # ------------------------------------------------------
                # Auto-trading control panel (demo accounts only — hard lock)
                # ------------------------------------------------------
                auto_trade_now = False
                if auto_mode_selected:
                    st.divider()
                    if not account["is_demo"]:
                        st.error(
                            "🔒 Auto-trading is locked on LIVE accounts. This isn't adjustable from "
                            "the UI — the app checks MT5's own account type and refuses to auto-fire "
                            "on anything but a confirmed demo account. Switch execution mode to Manual, "
                            "or log into a demo account in MT5 to use Auto mode.",
                        )
                    elif not execution_enabled:
                        st.info("Tick the execution checkbox in the sidebar to enable auto-trading controls.")
                    else:
                        st.markdown("### 🤖 Auto-trading (DEMO account confirmed)")
                        auto_interval = st.slider("Check every (seconds)", 10, 120, 20)
                        st.session_state.auto_interval = auto_interval

                        col_a, col_b, col_c = st.columns([1, 1, 2])
                        if col_a.button("▶️ Start auto-trading", disabled=st.session_state.auto_trading_active):
                            st.session_state.auto_trading_active = True
                            st.session_state.auto_session_start_equity = account["equity"]
                            st.session_state.auto_traded_symbols = {}
                            st.rerun()
                        if col_b.button("⏹️ Stop auto-trading", disabled=not st.session_state.auto_trading_active):
                            st.session_state.auto_trading_active = False
                            st.rerun()

                        if st.session_state.auto_trading_active:
                            start_equity = st.session_state.auto_session_start_equity
                            drawdown_pct = ((start_equity - account["equity"]) / start_equity) * 100 if start_equity else 0

                            if drawdown_pct >= max_daily_loss_pct:
                                st.session_state.auto_trading_active = False
                                st.error(
                                    f"🛑 Kill-switch triggered: session equity dropped {drawdown_pct:.1f}%, "
                                    f"past your {max_daily_loss_pct}% limit. Auto-trading stopped."
                                )
                            else:
                                col_c.success(
                                    f"🟢 ACTIVE — {st.session_state.trades_this_session}/{max_trades_session} trades used | "
                                    f"session drawdown: {drawdown_pct:.1f}% / {max_daily_loss_pct}% limit"
                                )
                                auto_trade_now = True
                        else:
                            col_c.info("⚪ Stopped")

                        with st.expander("🧪 Force a test trade (bypasses bias/threshold — for verifying the pipeline works)"):
                            st.caption(
                                "Fires immediately regardless of current bias — purely to confirm execution, "
                                "lot-sizing, and logging all work correctly. Still demo-only, still counts "
                                "toward your session trade cap."
                            )
                            tcol1, tcol2, tcol3 = st.columns([2, 1, 1])
                            test_symbol = tcol1.selectbox("Symbol", symbols, key="test_symbol")
                            test_direction = tcol2.selectbox("Direction", ["LONG", "SHORT"], key="test_direction")

                            if tcol3.button("🚀 Fire test trade"):
                                if st.session_state.trades_this_session >= max_trades_session:
                                    st.warning(f"Session limit of {max_trades_session} executions reached.")
                                else:
                                    try:
                                        test_df = mt5_bridge.get_live_bars(test_symbol, timeframe=timeframe, count=200)
                                        test_bias = generate_bias(test_df)
                                        test_atr = atr(test_df).iloc[-1]
                                        test_plan = build_trade_plan(
                                            symbol=test_symbol, direction=test_direction,
                                            account_balance=account["balance"], risk_pct=risk_pct,
                                            entry_price=test_bias["last_price"], atr_value=test_atr,
                                            atr_multiple=atr_multiple, reward_ratio=reward_ratio,
                                        )
                                        test_lots = mt5_bridge.raw_size_to_lots(test_plan.position_size, test_symbol)

                                        result = mt5_bridge.place_order(
                                            symbol=test_symbol, direction=test_direction,
                                            volume=test_lots, stop_loss=test_plan.stop_loss,
                                            take_profit=test_plan.take_profit, comment="TradeGuard-test",
                                        )
                                        log_execution(
                                            symbol=test_symbol, direction=test_direction, volume=result["volume"],
                                            fill_price=result["fill_price"], stop_loss=test_plan.stop_loss,
                                            take_profit=test_plan.take_profit, ticket=result["ticket"],
                                            account_mode="DEMO", trigger="test",
                                        )
                                        st.session_state.trades_this_session += 1
                                        st.success(
                                            f"✅ Test trade fired: {test_direction} {test_symbol}, "
                                            f"{result['volume']} lots @ {result['fill_price']} — ticket #{result['ticket']}"
                                        )
                                    except Exception as e:
                                        st.error(f"Test trade failed: {e}")

                st.markdown("### Watchlist analysis")
                open_symbols = {p["symbol"] for p in positions}

                for symbol in symbols:
                    try:
                        df = mt5_bridge.get_live_bars(symbol, timeframe=timeframe, count=200)
                        if len(df) < 50:
                            st.warning(f"{symbol}: not enough history on this timeframe.")
                            continue
                        bias_info = generate_bias(df)
                        atr_value = atr(df).iloc[-1]
                        direction = "LONG" if bias_info["score"] >= 0 else "SHORT"
                        plan = build_trade_plan(
                            symbol=symbol, direction=direction,
                            account_balance=account["balance"], risk_pct=risk_pct,
                            entry_price=bias_info["last_price"], atr_value=atr_value,
                            atr_multiple=atr_multiple, reward_ratio=reward_ratio,
                        )

                        # Convert the generic risk-based size into a real,
                        # broker-valid lot size for THIS symbol (contract
                        # size varies a lot between metals/forex/indices).
                        try:
                            real_lots = mt5_bridge.raw_size_to_lots(plan.position_size, symbol)
                            plan.position_size = real_lots
                        except Exception as e:
                            st.warning(f"{symbol}: couldn't read lot specs ({e}) — showing unconverted size.")

                        render_bias_card(
                            symbol, bias_info, atr_value, plan, direction,
                            currency=f"{account['currency']} ",
                            allow_execution=execution_enabled and not auto_mode_selected,
                            account_mode="DEMO" if account["is_demo"] else "LIVE",
                            max_trades=max_trades_session,
                        )

                        # --------------------------------------------------
                        # Auto-fire diagnostic — makes the exact reason a
                        # symbol did or didn't fire visible, instead of it
                        # being a silent mystery.
                        # --------------------------------------------------
                        if auto_mode_selected:
                            already_open = symbol in open_symbols
                            last_traded_at = st.session_state.auto_traded_symbols.get(symbol)
                            cooldown_remaining = 0
                            if last_traded_at is not None:
                                elapsed_min = (datetime.now() - last_traded_at).total_seconds() / 60
                                cooldown_remaining = max(0, reentry_cooldown_minutes - elapsed_min)
                            in_cooldown = cooldown_remaining > 0
                            strong_enough = abs(bias_info["score"]) >= bias_threshold
                            cap_ok = st.session_state.trades_this_session < max_trades_session
                            would_fire = (auto_trade_now and not already_open and not in_cooldown
                                          and strong_enough and cap_ok)

                            with st.expander(f"🔍 Why did {symbol} {'FIRE' if would_fire else 'NOT fire'} this cycle?"):
                                st.markdown(f"- Auto-trading active & kill-switch OK: "
                                            f"{'✅' if auto_trade_now else '❌ auto-trading is not currently active'}")
                                st.markdown(f"- Score {bias_info['score']:+.2f} vs threshold {bias_threshold}: "
                                            f"{'✅ strong enough' if strong_enough else '❌ too weak/neutral'}")
                                st.markdown(f"- Already has an open position: "
                                            f"{'❌ yes — skipped to avoid duplicating' if already_open else '✅ no'}")
                                st.markdown(f"- Re-entry cooldown: "
                                            f"{f'❌ {cooldown_remaining:.1f} min remaining' if in_cooldown else '✅ clear'}")
                                st.markdown(f"- Session trade cap ({st.session_state.trades_this_session}/{max_trades_session}): "
                                            f"{'✅ room left' if cap_ok else '❌ cap reached'}")

                        # --------------------------------------------------
                        # Auto-fire: only reached if account is DEMO, auto mode
                        # is active, kill-switch hasn't tripped, the symbol
                        # doesn't already have an open position, its re-entry
                        # cooldown (if any) has elapsed, the bias is strong
                        # enough, and the session trade cap isn't hit.
                        # --------------------------------------------------
                        last_traded_at = st.session_state.auto_traded_symbols.get(symbol)
                        in_cooldown = False
                        if last_traded_at is not None:
                            elapsed_min = (datetime.now() - last_traded_at).total_seconds() / 60
                            in_cooldown = elapsed_min < reentry_cooldown_minutes

                        if (auto_trade_now
                                and symbol not in open_symbols
                                and not in_cooldown
                                and abs(bias_info["score"]) >= bias_threshold
                                and st.session_state.trades_this_session < max_trades_session):
                            try:
                                result = mt5_bridge.place_order(
                                    symbol=symbol, direction=direction,
                                    volume=round(plan.position_size, 2),
                                    stop_loss=plan.stop_loss, take_profit=plan.take_profit,
                                    comment="TradeGuard-auto",
                                )
                                log_execution(
                                    symbol=symbol, direction=direction, volume=result["volume"],
                                    fill_price=result["fill_price"], stop_loss=plan.stop_loss,
                                    take_profit=plan.take_profit, ticket=result["ticket"],
                                    account_mode="DEMO", trigger="auto",
                                )
                                st.session_state.trades_this_session += 1
                                st.session_state.auto_traded_symbols[symbol] = datetime.now()
                                st.toast(f"🤖 Auto-executed {direction} {symbol} — ticket #{result['ticket']}")
                            except Exception as e:
                                st.error(f"Auto-execution failed for {symbol}: {e}")

                    except Exception as e:
                        st.error(f"{symbol}: {e}")

            except Exception as e:
                st.error(f"MT5 error: {e}")
                st.session_state.mt5_connected = False

    else:
        st.markdown("### Watchlist analysis (Yahoo Finance)")
        for symbol in symbols:
            try:
                df = fetch_price_data(symbol, period="3mo")
                if len(df) < 50:
                    st.warning(f"{symbol}: not enough history.")
                    continue
                bias_info = generate_bias(df)
                atr_value = atr(df).iloc[-1]
                direction = "LONG" if bias_info["score"] >= 0 else "SHORT"
                plan = build_trade_plan(
                    symbol=symbol, direction=direction,
                    account_balance=manual_balance, risk_pct=risk_pct,
                    entry_price=bias_info["last_price"], atr_value=atr_value,
                    atr_multiple=atr_multiple, reward_ratio=reward_ratio,
                )
                render_bias_card(symbol, bias_info, atr_value, plan, direction)
            except Exception as e:
                st.error(f"{symbol}: {e}")

    st.caption(f"Last updated: {datetime.now():%Y-%m-%d %H:%M:%S}")

with tab_journal:
    st.subheader("Log a completed trade")
    with st.form("log_trade_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        j_symbol = c1.text_input("Symbol")
        j_direction = c2.selectbox("Direction", ["LONG", "SHORT"])
        j_balance_before = c3.number_input("Balance before trade", min_value=0.0, step=10.0)

        c4, c5, c6 = st.columns(3)
        j_entry = c4.number_input("Entry price", step=0.01, format="%.4f")
        j_stop = c5.number_input("Stop-loss", step=0.01, format="%.4f")
        j_target = c6.number_input("Take-profit", step=0.01, format="%.4f")

        c7, c8 = st.columns(2)
        j_size = c7.number_input("Position size", step=0.01)
        j_exit = c8.number_input("Exit price", step=0.01, format="%.4f")

        j_notes = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("✅ Log trade")

        if submitted and j_symbol:
            new_balance = log_trade(
                symbol=j_symbol, direction=j_direction, entry_price=j_entry,
                stop_loss=j_stop, take_profit=j_target, position_size=j_size,
                exit_price=j_exit, balance_before=j_balance_before, notes=j_notes,
            )
            st.success(f"Trade logged. New balance: {new_balance}")
            st.rerun()

    st.divider()
    st.subheader("Performance summary")
    stats = summarize()

    if stats["trades"] == 0:
        st.info("No trades logged yet.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total trades", stats["trades"])
        c2.metric("Win rate", f"{stats['win_rate']}%")
        c3.metric("Total P&L", stats["total_pnl"])
        c4.metric("Current balance", stats["current_balance"])

        ensure_journal_exists()
        journal_df = pd.read_csv(JOURNAL_FILE)
        if not journal_df.empty:
            st.markdown("**Balance over time**")
            st.line_chart(journal_df.set_index("timestamp")["balance_after"])
            st.markdown("**Full journal**")
            st.dataframe(journal_df, use_container_width=True)

with tab_backtest:
    st.warning(
        "**Historical simulation only — not proof of future results.** This runs the "
        "exact same bias/risk logic against past price data, without lookahead. It's "
        "real, checkable evidence of how this approach behaved historically — markets "
        "change, and no backtest can guarantee anything going forward. Spread, "
        "commission, and slippage aren't modeled, so live results will typically be "
        "somewhat worse than what's shown here.",
        icon="⚠️",
    )

    bt_col1, bt_col2, bt_col3 = st.columns(3)
    bt_symbol = bt_col1.text_input(
        "Symbol", "AAPL", key="bt_symbol",
        help="Yahoo Finance ticker — e.g. AAPL, BTC-USD, EURUSD=X, GC=F (gold futures)"
    )
    bt_period = bt_col2.selectbox("History period", ["6mo", "1y", "2y", "5y", "10y"], index=2)
    bt_balance = bt_col3.number_input("Starting balance", min_value=1.0, value=1000.0, step=100.0)

    bt_col4, bt_col5, bt_col6, bt_col7 = st.columns(4)
    bt_risk_pct = bt_col4.slider("Risk % per trade", 0.1, 5.0, 1.0, 0.1, key="bt_risk")
    bt_threshold = bt_col5.slider("Bias threshold", 0.5, 2.5, 1.0, 0.25, key="bt_threshold")
    bt_atr_mult = bt_col6.slider("Stop ATR multiple", 0.5, 4.0, 1.5, 0.1, key="bt_atr")
    bt_reward = bt_col7.slider("Reward:Risk", 1.0, 5.0, 2.0, 0.5, key="bt_reward")

    if st.button("▶️ Run backtest", type="primary"):
        with st.spinner("Fetching history and simulating trades..."):
            try:
                df = fetch_price_data(bt_symbol, period=bt_period)
                if len(df) < 80:
                    st.error("Not enough history returned for a meaningful backtest.")
                else:
                    results = run_backtest(
                        df, symbol=bt_symbol, starting_balance=bt_balance,
                        risk_pct=bt_risk_pct, atr_multiple=bt_atr_mult,
                        reward_ratio=bt_reward, bias_threshold=bt_threshold,
                    )
                    st.session_state.last_backtest = results
            except Exception as e:
                st.error(f"Backtest failed: {e}")

    if "last_backtest" in st.session_state:
        results = st.session_state.last_backtest

        if results["trades"] == 0:
            st.info("No trades triggered over this period at this threshold. Try a lower threshold or longer period.")
        else:
            st.markdown("### Results")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Trades", f"{results['trades']} ({results['wins']}W / {results['losses']}L)")
            r2.metric("Win rate", f"{results['win_rate']}%")
            r3.metric("Total return", f"{results['total_return_pct']:+.2f}%")
            r4.metric("Max drawdown", f"{results['max_drawdown_pct']:.2f}%")

            r5, r6, r7 = st.columns(3)
            r5.metric("Profit factor", results["profit_factor"])
            r6.metric("Avg win", results["avg_win"])
            r7.metric("Avg loss", results["avg_loss"])

            if results["trades"] < 30:
                st.warning(
                    f"Only {results['trades']} trades — treat these numbers as a rough "
                    f"sketch, not a reliable statistic. A longer period gives more trades "
                    f"and a more trustworthy (though still not guaranteed) picture."
                )

            equity_df = pd.DataFrame(results["equity_curve"], columns=["date", "balance"]).set_index("date")
            st.markdown("**Equity curve**")
            st.line_chart(equity_df["balance"])

            st.markdown("**Trade log**")
            trade_rows = [{
                "entry_date": t.entry_date[:10], "exit_date": t.exit_date[:10],
                "direction": t.direction, "entry": t.entry_price, "exit": t.exit_price,
                "pnl": t.pnl, "exit_reason": t.exit_reason,
            } for t in results["trade_log"]]
            st.dataframe(pd.DataFrame(trade_rows), use_container_width=True)

# ----------------------------------------------------------------------
# Auto-refresh (manual toggle, or forced while auto-trading is active)
# ----------------------------------------------------------------------
if st.session_state.auto_trading_active:
    time.sleep(st.session_state.get("auto_interval", 20))
    st.rerun()
elif auto_refresh:
    time.sleep(refresh_seconds)
    st.rerun()
