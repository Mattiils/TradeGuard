# TradeGuard by Matti — Technical Analysis & Risk Management CLI

**Author:** Matti
**Contact:** mattiiqbal@proton.me | [LinkedIn](https://www.linkedin.com/in/m-mati-iqbal-azhar-631225295)

A Python command-line tool that helps traders make risk-managed decisions
by combining live market data, standard technical indicators, and
position-sizing math — with a running trade journal to track performance.

**This is a decision-support tool, not an auto-trading bot.** It never
places trades. It calculates numbers and shows its reasoning; the trader
always makes the final call.

## Why I built this

I'm interested in both markets and technology, and wanted a project that
combined real Python/data skills with something I'd actually use — proper
risk management (position sizing, stop-loss placement) is the part most
new traders skip, so I built a tool that makes it automatic.

## Features

- **Live market data** for stocks, ETFs, indices, and crypto pairs (via
  [yfinance](https://pypi.org/project/yfinance/) — free, no API key needed)
- **Technical indicators**: SMA, EMA, RSI, MACD, ATR (volatility)
- **Transparent bias summary** — every signal shows *why* it was generated,
  not just a black-box "buy/sell" label
- **Risk-based position sizing** — enter your account balance and risk %,
  get an exact position size, stop-loss, and take-profit based on current
  volatility (ATR), not guesswork
- **Trade journal** — log completed trades to CSV, auto-calculates P&L
  and running balance
- **Performance summary** — win rate, average win/loss, total P&L
- **Live MT5 integration** (`watch` command, and the dashboard) — reads your
  real account balance, open positions, and live price feed directly from
  a running MetaTrader 5 terminal
- **One-click trade execution** from the dashboard — places real MT5 orders
  with explicit confirmation, a session execution limit, and a full audit
  log (never runs on its own in Manual mode)
- **Auto-trading mode** — optionally lets the dashboard fire trades itself
  on a timer, but only ever on a confirmed demo account (hard-locked in
  code, not just convention), with a bias-strength threshold, a kill-switch
  drawdown limit, and a trade cap
- **Scalper mode** — a faster-timeframe analysis preset feeding the same
  manual-confirm execution flow, not a standalone auto-trading bot
- **Backtesting** (CLI and dashboard) — runs this exact strategy against
  historical data, bar by bar, without lookahead — real evidence of past
  behavior, never a promise about the future (see below)

## Live MT5 monitoring (`watch` command)

TradeGuard can also run **alongside a live MetaTrader 5 terminal**, reading
your real account balance, open positions, and live price feed directly —
so risk calculations are based on your actual current balance, not a number
you type in manually.

**This is read-only.** It never places, modifies, or closes a trade. It
connects to MT5 purely to display live numbers and reasoning; you place
trades yourself, inside MT5.

### Requirements
- Windows (the `MetaTrader5` Python package doesn't support macOS/Linux)
- MT5 desktop terminal installed and **already open and logged in** to
  your account (demo or live)

### Usage

```
python main.py watch EURUSD GBPUSD --risk-pct 1 --timeframe M15 --interval 30
```

This opens a live dashboard that refreshes every 30 seconds, showing:
- Your account balance, equity, and open positions
- A technical bias (bullish/bearish/neutral) with reasoning for each symbol
- A suggested risk-managed entry/stop/target and position size based on
  your **actual live account balance**

Press `Ctrl+C` to stop. Add `--once` to take a single snapshot instead of
looping continuously.

⚠️ Use a **demo account** while testing this, and double-check the exact
symbol names your broker uses in MT5's Market Watch (some brokers add
suffixes, e.g. `EURUSD.a`).

## One-click trade execution (real orders — read carefully)

The dashboard can also place real orders on your MT5 account directly
from a button — with deliberate friction built in, because this sends
real money into the market:

- **Nothing executes on its own, ever.** There is no timer, no loop, no
  background process that places trades. A trade only ever fires the
  instant *you* click a specific "Execute" button for that exact symbol
  and direction, right after seeing its analysis.
- **You must explicitly opt in** via a sidebar checkbox before any
  execute button appears at all.
- **On a LIVE account**, you must additionally type the word `EXECUTE`
  into a confirmation box before the button becomes clickable.
- **A session execution limit** (default 5, adjustable) stops runaway
  clicking from doing more damage than intended.
- **Every execution is logged** to `execution_log.csv` — a permanent,
  separate audit trail from the manual trade journal.

⚠️ **Strongly recommended: only enable execution on a demo account while
you're learning how this behaves.** Test thoroughly before ever pointing
it at a live account, and start with small position sizes even then.

### Backtesting — real evidence, not a promise

No trading system can be proven profitable in advance. What TradeGuard's
backtester gives you instead is honest: it runs the exact same bias
calculation and risk-based position sizing used live, against real
historical price data, one bar at a time — using only data available up
to that point (no lookahead/cheating). That produces real, checkable
numbers for how this specific rule-based approach has actually behaved.

**What a backtest tells you:** win rate, total return, max drawdown, and
profit factor over a chosen historical period, for a chosen symbol.

**What a backtest does NOT tell you:**
- Whether it will work going forward. Markets change ("regime change") —
  a strategy that performed well over the last 2 years can simply stop
  working, and no backtest rules that out.
- Real trading costs. Spread, commission, and slippage aren't modeled,
  so live results are typically somewhat worse than backtested ones.
- Anything reliable from a small number of trades. Under ~30 trades,
  treat the result as a rough sketch, not a statistic.

### CLI usage

```
python main.py backtest AAPL --period 2y --balance 1000 --risk-pct 1 --show-trades
```

### Dashboard usage

Open the **Backtest** tab, enter a symbol (Yahoo Finance tickers — e.g.
`AAPL`, `BTC-USD`, `EURUSD=X`, `GC=F` for gold futures), pick a history
period and parameters, and hit **Run backtest**. You'll get an equity
curve, full trade log, and the same stats as the CLI version.

## Technical indicators & the ADX trend-strength filter

Every bias calculation combines: SMA20/SMA50 structure, RSI(14), MACD
momentum, and **ADX(14)** — the Average Directional Index.

ADX measures trend *strength*, independent of direction. It exists to
solve a specific, real problem: a symbol can look "a bit bullish" by
moving averages and "a bit bearish" by momentum at the same time simply
because it isn't trending at all — it's chopping sideways. Averaging
those signals together produces a wishy-washy near-zero score that looks
like "mixed opinions" when it's really "there's no real trend to read
right now."

- **ADX < 20** — weak/no trend (likely choppy/ranging). The bias score is
  automatically dampened (×0.4), making it much harder for a genuinely
  directionless symbol to cross your auto-trade threshold.
- **ADX 20–25** — a trend may be emerging but isn't confirmed yet.
- **ADX > 25** — a real trend is confirmed, regardless of which direction.

This is a well-established technique in algorithmic trading (not
something invented for this project) — it's used specifically to reduce
false signals during range-bound conditions. It doesn't predict anything
either; it just tells you when the other indicators are worth trusting
more versus less.

## Two execution modes: Manual and Auto

**Manual mode** — click "Execute" under any symbol, exactly as described above.

**Auto mode** — the dashboard evaluates your watchlist on a timer and fires
trades itself when the bias is strong enough, without you clicking anything.
This is genuinely useful for testing strategy ideas quickly on a demo account.
Several things are true about it by design, not by convention:

- **It refuses to run on anything but a confirmed demo account.** The app
  checks MT5's own `account_info().trade_mode` — if it isn't demo, Auto mode
  is locked in the UI with no override. This isn't a setting you can just
  tick past; it's enforced in code.
- **A bias-strength threshold** (adjustable) — it only fires when the signal
  is clearly one-sided, not on marginal/mixed readings.
- **Won't double up** — it skips a symbol if there's already an open
  position on it.
- **A re-entry cooldown per symbol** (default 15 minutes, adjustable,
  can be set to 0 to disable) — after auto-trading a symbol, it waits
  before firing on that same symbol again. This stops rapid whipsaw
  re-entry right after a quick stop-out, without permanently blocking a
  symbol for the rest of the session once the cooldown has passed.
- **A kill-switch** — you set a max session drawdown % (default 5%); if
  equity falls that far from where it stood when you hit Start, auto-trading
  stops itself immediately.
- **A hard trade cap** per session (same limit Manual mode uses).
- **Every auto-fired trade is logged** to `execution_log.csv` with
  `trigger=auto`, so you can tell exactly which trades were automated
  versus manually clicked, after the fact.

Start it from the dashboard: switch execution mode to "Auto (demo accounts
only)", tick the confirmation checkbox, set your thresholds, and hit
**▶️ Start auto-trading**. Stop any time with **⏹️ Stop auto-trading**.

⚠️ This is still a real trading system placing real orders on your demo
account — treat it with the same care you'd want before ever considering
live money, and watch the kill-switch and trade counters while it runs.

## Scalper mode

A sidebar toggle in the dashboard that switches the default timeframe to
M1 and tightens the stop-loss distance and reward:risk ratio for faster
setups. It feeds into the exact same manual-confirm execution flow above
— it is **not** a standalone automated scalping bot, and it never fires
trades by itself. Scalping is a genuinely high-risk, fast-moving trading
style — treat this as a faster lens on the same numbers, not a shortcut
past risk management.

## Visual dashboard (recommended)

The easiest way to use TradeGuard is the browser-based dashboard —
no commands to type, just buttons, sliders, and live-updating cards.

```
streamlit run app.py
```

This opens in your browser at `http://localhost:8501` and gives you:
- A sidebar to pick data source (live MT5 account, or Yahoo Finance —
  no MT5 needed), symbols, risk %, and refresh settings
- A **Live Dashboard** tab: account balance/equity, open positions, and
  a bias + risk-managed trade plan card for every symbol you're watching
- A **Trade Journal** tab: a form to log completed trades with one click,
  a performance summary, and a balance-over-time chart
- An auto-refresh toggle so it updates on its own while you watch

Everything below documents the command-line version (`main.py`), which
still works exactly the same and shares the same underlying engine.

## Command-line usage



```
python3 main.py analyze BTC-USD --balance 1000 --risk-pct 2
```

```
--- BTC-USD technical snapshot (2026-07-21 12:12) ---
Last price: 83.3668
20-period SMA: 87.6879   50-period SMA: 92.8265
RSI(14): 15.1
ATR(14) [volatility]: 1.5786

Bias: BEARISH bias
Reasoning:
  - Price is below both the 20 and 50-period averages (downtrend structure).
  - RSI is 15.1 — conventionally read as oversold.
  - MACD histogram is negative (downward momentum).

--- Suggested risk-managed plan (if you chose to take a SHORT trade) ---
Entry:        83.3668
Stop-loss:    85.7347   (based on 1.5x ATR)
Take-profit:  78.631    (targets 2.0:1 reward:risk)
Position size: 8.446388 units
Amount at risk if stopped out: 20.0 (2.0% of balance)
Potential gain if target hit:  40.0
```

## Example: logging a trade and viewing performance

```
python3 main.py log BTC-USD LONG --entry 100 --stop 95 --target 110 --size 2 --exit-price 108 --balance 1000

python3 main.py summary
```

```
--- Trade Journal Summary ---
Total trades:   3
Wins / Losses:  2 / 1
Win rate:       66.7%
Total P&L:      25.0
Avg win:        15.5
Avg loss:       -6.0
Current balance: 1049.0
```

## Installation

```
pip install -r requirements.txt
python3 main.py analyze AAPL --balance 5000 --risk-pct 1
```

## How the risk math works

- **Stop-loss / take-profit**: derived from Average True Range (ATR), a
  standard volatility measure, rather than a fixed number of points —
  so the stop distance adapts to how volatile the asset currently is.
- **Position sizing**: fixed-fractional sizing — you choose what % of
  your account you're willing to risk on a single trade (1-2% is a
  common professional guideline), and the tool works backward from your
  stop-loss distance to tell you exactly how many units to trade.
- **Bias/signal**: a transparent combination of moving average structure,
  RSI, and MACD momentum — each shown with its reasoning so you can judge
  it yourself rather than trusting a black box.

## ⚠️ Important disclaimer

This tool is for educational and informational purposes only. It is
**not financial advice**, and nothing it outputs is a recommendation to
buy or sell any asset. Technical indicators describe historical price
action — they do not predict future results. Trading and investing carry
real risk of financial loss. Always do your own research, and consider
practicing with a demo/paper trading account before using real money.

## Tech stack

Python 3, pandas, numpy, yfinance

## Possible future improvements

- Web dashboard (Flask/React) instead of CLI
- Multi-timeframe analysis
- Backtesting mode against historical data
- Telegram/email alerts when a symbol's bias changes

---
© 2026 Matti. Built as a personal project to combine an interest
in markets with hands-on Python development. See [LICENSE](LICENSE).
