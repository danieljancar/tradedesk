# tradedesk

A local crypto desk: whole-market scan, gold, a trading sleeve and an optional long-term core sleeve, Telegram alerts. Python code fetches data, enforces risk and talks to Binance. Agents in `.claude/agents` write the analysis. `/daily` runs a full day, `/review` updates `lessons.md` from the calibration stats.

## Commands

`uv run desk --help` lists everything. The ones you'll use: `run start`, `sync`, `snapshot` (runs the market scan first), `news`, `book`, `post`, `check`, `execute`, `status`, `journal`, `learn`, `stats`. For you, not the agents: `scan`, `rebalance`, `trim`, `analytics`, `report`, `bot`. Run folders live in `runs/<id>/`.

## Rules

- Numbers come from `snapshot.md`, `book.md` or a tool result. Never estimate a price, level or indicator.
- The risk engine in `src/tradedesk/risk.py` decides size, leverage and whether a trade passes. Don't edit it, `config.py` or `desk.toml` to make a plan pass, and don't approve plans. Approval belongs to the human.
- Every position has a stop on the exchange. Stops only move in the trade's favor.
- Keep files short. Each agent has a word limit; stay under it.

## Development

`uv run pytest`, `uv run ruff check`, `uv run ruff format`. Exchange calls are tested with recorded responses in `tests/test_exchange.py`.
