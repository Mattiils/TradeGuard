# TradeGuard — Technical Analysis & Risk Management CLI

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

## Example: analyzing a symbol

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
