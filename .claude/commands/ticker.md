---
description: Daily market brief (Handelsticker). Writes data/ticker/<date>.md and keeps data/ticker/events.json current.
---

You write the desk's daily market brief. It's a reference the desk and Daniel come back to, so each brief builds on the earlier ones.

1. Run `uv run desk ticker`. It prints the data file for today, then up to five earlier briefs, then the events file.
2. Read the data file, the earlier briefs and `data/ticker/events.json`. If it doesn't exist yet, start it from the events in `data/ticker/calendar.md`.
3. Do up to 8 web searches for what the data can't tell you: the event calendar for the next 8 weeks (FOMC, CPI, jobs, SNB, ECB, political and geopolitical dates like talks, summits, tariff deadlines, elections and rulings, crypto dates like Binance listings, token unlocks and ETF deadlines), what the Fed and other central banks signalled last, the political or policy stories behind the biggest moves, and the strategies or themes traders are talking about this week. Skip a search when an earlier brief already answered it and nothing changed.
4. Write `data/ticker/<today>.md` in the layout below.
5. Update `data/ticker/events.json`, a JSON list. It feeds Daniel's phone calendar and is public, so it holds no positions or desk plans. Never delete an event, past ones stay as the record; fix changed dates and add new ones. Each event:
   - `id`: short stable slug, never changed once set, e.g. `fomc-2026-12`
   - `date` `YYYY-MM-DD`, `end` for events over several days, `time` `HH:MM` in UTC only when the clock time is known (otherwise it's an all-day event), `minutes` if it runs longer than an hour
   - `title`: short, e.g. `FOMC rate decision`
   - `category`: `macro`, `central bank`, `politics`, `geopolitics`, `crypto` or `stocks`
   - `summary`: one sentence with what's expected
   - `notes`: 2 to 5 sentences going deeper: consensus and forecasts with who made them, what happened last time, which way a surprise likely pushes crypto, stocks and gold
   - `links`: 1 to 3 `{"title", "url"}` from your searches, the official source first
   Update the notes when news changes the picture. After the event, add one sentence with the outcome.
6. Reply with one line: the brief's path.

Layout, 700 words max:

- First line: the day's market in one sentence with numbers.
- `## Direction`: indexes, crypto and the macro regime. Up, down or sideways over 1d, 1w and 1m, and what changed against the earlier briefs.
- `## Sectors`: which sectors and industries lead and lag over 1w and 1m, with numbers. Call out rotations that started or ended since the earlier briefs.
- `## Stocks`: the big movers among the tracked US and Swiss stocks and the reason when a headline or search gives one.
- `## Crypto`: majors, trending coins, dominance, fear and greed.
- `## Politics and policy`: the headlines that move markets, with what they could change.
- `## Strategies`: what's working this week (trend, mean reversion, rotation into a sector, hedges) and what isn't, judged from the numbers.
- `## Coming up`: the next events from the calendar with the desk's plan for each: what we'd watch, and which way a surprise likely pushes crypto and stocks.
- `## Desk takeaways`: three to five lines the trading desk can use in its next runs.
- `## Sources`: the URLs from web search, one per line.

Rules:
- Numbers come from the data file or a search result. Never estimate a price, rate or date.
- Opinions and forecasts are labelled as such, with who said them.
- Build on earlier briefs: name what changed, don't repeat what didn't.
- The writing rules in CLAUDE.md apply.

Bash is only for `uv run desk ticker`. Use Read, Write and WebSearch for the rest.
