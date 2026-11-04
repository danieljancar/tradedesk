# tradedesk

A small crypto desk that runs on your own machine. Claude Code agents read the market every day and argue about it, a risk engine written in plain Python decides what's allowed and how big, and Binance holds the stop for every position. A local dashboard shows the whole thing as it happens.

![The trading floor during a run](docs/floor.webp)

## How a day works

`/daily` in Claude Code runs one pass:

1. `desk scan` looks at every Binance spot pair in the quote currency and picks the strongest movers by 7 day move against BTC, volume against its weekly average and ATR. Those join the watchlist and gold (PAXG) as today's assets. `desk snapshot` pulls 4h, daily and weekly candles from Binance and turns them into a short text file per asset: EMAs, RSI, MACD, ATR, swing levels, funding, open interest and the long/short ratio, plus the fear and greed index. `desk news` collects the last 36 hours of headlines from CoinDesk, Cointelegraph, Decrypt and The Block and sorts them by asset. `desk book` writes down equity, open positions, recent results and the lessons from past reviews.
2. Two analysts run in parallel. The technical analyst reads only the snapshot and the list of today's assets. The news analyst reads the headlines and checks the macro calendar with at most three web searches.
3. A bull and a bear each read both reports and make their case, one round, 200 words each.
4. The main session acts as portfolio manager. It weighs both sides and writes `plans.json` with entry, stop, target, horizon and confidence per idea. It never sets size.
5. `desk check` runs every idea through the risk engine. It sizes the trade so a stop-out costs 1% of equity and rejects anything that breaks a rule: reward to risk under 2, a stop tighter than half an ATR, too much open risk, a daily loss over 3%, drawdown over 15%, an asset outside today's list, a short on spot.
6. Plans that pass wait for you in the dashboard. Approving one sends it to Binance.

Each agent has a word limit and reads files from the run folder instead of passing long reports through the conversation.

## Safety

Every order goes out with its stop already on the exchange, so a run that fails or a laptop that's off doesn't leave a position unprotected.

On spot, limit entries are sent as one OTOCO order list: the buy, and a stop-loss plus take-profit that activate when it fills. Market entries are followed by an OCO, and if that fails the coins are sold straight back. Spot is long only.

On USDⓈ-M futures, entries are market orders sent when price reaches the plan's level, in isolated margin. Stop and target go out right after as `closePosition` conditional orders on mark price. If the stop can't be placed, the position is closed at once. Futures limit entries need `desk watch` running, because the desk only sees the price when it syncs.

Stops only move in the trade's favor. Positions are closed when they outlive their horizon (3, 21 or 120 days by default). `desk kill --flatten` cancels everything and closes every position.

The agents can't approve trades, edit the risk code or read `.env`. `.claude/settings.json` blocks it.

This is a tool for running your own process, not a strategy that makes money. Most people who trade with leverage lose. Start in paper mode and stay there until the journal says otherwise.

## Setup

You need [uv](https://docs.astral.sh/uv/) and [Claude Code](https://code.claude.com).

```sh
git clone https://github.com/danieljancar/tradedesk.git
cd tradedesk
uv sync
cp desk.example.toml desk.toml
```

Paper mode needs no keys and simulates fills on live Binance candles. For testnet or live trading, copy `.env.example` to `.env` and add a Binance API key with trading permission only, withdrawals off and an IP restriction. Spot testnet keys come from [testnet.binance.vision](https://testnet.binance.vision).

## Running it

```sh
uv run desk serve          # dashboard on http://127.0.0.1:8420
claude                     # then type /daily
```

To see the dashboard without any setup, `uv run desk demo` replays a made-up run on a separate database.

To run every morning, point cron or launchd at `scripts/daily.sh`. It calls `claude -p "/daily" --permission-mode dontAsk`, which allows only the commands listed in `.claude/settings.json`.

Once a week, `/review` (or `scripts/review.sh` on a schedule) runs `desk stats` and rewrites `lessons.md`, which the portfolio manager reads before every decision.

## Telegram

The desk can message you on Telegram and take your answer from there. You get a message when a plan passes the risk check (with Approve and Drop buttons unless `auto_execute` is on), when an entry fills, when a position closes by stop or target, when the exchange returns an error, when a run finishes and when the kill switch is used. A position without a working stop is always sent, even during quiet hours and even if `error` is left out of `events`.

1. Message [@BotFather](https://t.me/BotFather), send `/newbot` and copy the token it gives you.
2. Send your new bot any message, then open `https://api.telegram.org/bot<token>/getUpdates` in a browser. The number under `"chat":{"id":...}` is your chat id.
3. Put both in `.env` as `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
4. In `desk.toml` set `telegram = true` under `[notify]`. `events` picks which messages you get, `quiet_hours = "23-07"` holds back everything except errors and stop-outs during those local hours.
5. Run `uv run desk report --send` once to check it arrives.

`desk bot` long-polls Telegram and only answers your chat id. Approve on a plan does the same as the dashboard: approve, then send it to the exchange. `/status` shows equity, open positions with open P&L and pending entries, `/plans` lists plans waiting with their buttons, `/report` sends the digest, `/kill` cancels every pending order and `/flatten` also closes every position. Both ask for a second tap, and that button stops working after 5 minutes.

On a Mac, `scripts/launchd/install.sh 07:30` installs two launchd jobs for your user: the bot, restarted if it stops, and `desk report --send` every morning at 07:30. Logs go to `data/logs/`. `scripts/launchd/install.sh --remove` takes both out again.

## Learning

Every idea counts, taken, passed or rejected. `desk learn` replays each one on real 1h candles until it hits its target or stop, expires unfilled or outlives its horizon, and stores the result with the market context of that day in the `outcomes` table. Each run's snapshot facts go to `snapshots`, together with what every asset did in the 24 and 72 hours after. `desk sync` updates both on the side, at most once an hour per idea.

`desk stats` (and `GET /api/learning`) turns that into calibration: hit rate and average R by confidence, asset, horizon, side and decision, the market after days with no ideas, and whether the bull or the bear side matched. Every number carries its sample size, and groups under 10 examples say "not enough data yet". Lessons may change how ideas are judged, never the risk limits. Once 10 ideas have resolved, `book.md` carries a one-line calibration summary.

## Commands

| Command | What it does |
| --- | --- |
| `desk scan` | Pick today's assets from the whole spot market |
| `desk snapshot`, `news`, `book` | Write the day's input files |
| `desk check plans.json` | Validate and size ideas |
| `desk plans`, `approve ID`, `reject ID` | Review proposed plans |
| `desk execute` | Send approved plans |
| `desk sync` | Pick up fills, stops, targets, expiries |
| `desk watch` | Keep syncing every 5 minutes |
| `desk status` | Equity and open positions |
| `desk stop ID PRICE`, `close ID` | Manage a position |
| `desk kill [--flatten]` | Cancel everything |
| `desk journal` | Closed trades with R multiples |
| `desk learn` | Replay every idea on real candles into `outcomes` |
| `desk stats` | Calibration report for `/review` |
| `desk report [--send]` | Short digest, printed or sent to Telegram |
| `desk bot` | Telegram bot for approvals, status and the kill switch |

## Configuration

`desk.example.toml` lists every setting with its default: mode (`paper`, `testnet`, `live`), market (`spot`, `futures`), watchlist, risk limits, hold times and whether passing plans go out without approval.

The `[universe]` section controls the scan. Pairs under 20M USDT of 24h volume are skipped, stablecoins, fiat and leveraged tokens never show up, and `exclude` drops any asset you don't want. The scan adds its top 6 movers after the watchlist, the `always` list and PAXG, up to 12 assets a day. Scan picks go through the same risk rules as everything else. With `enabled = false` the desk uses only the watchlist, like before.

## Development

```sh
uv run pytest
uv run ruff check
uv run ruff format
```

The dashboard is a React app in `frontend/` (Vite, shadcn/ui, Lightweight Charts, Recharts, Motion). The built files are committed in `src/tradedesk/web/dist`, so running the desk only needs uv. To change the UI you need Node and pnpm:

```sh
cd frontend
pnpm install
pnpm dev      # hot reload on :5173, talks to `desk serve` on :8420
pnpm build    # writes src/tradedesk/web/dist
```

Binance calls are tested against recorded responses in `tests/test_exchange.py`, the paper flow end to end in `tests/test_paper_flow.py`.

The roles and the debate follow [TradingAgents](https://github.com/TauricResearch/TradingAgents). The order safety rules (protect or close, validate prices in code, never trust a number the model wrote) come from reading [NOFX](https://github.com/NoFxAiOS/nofx) and [Freqtrade](https://www.freqtrade.io).

## License

MIT
