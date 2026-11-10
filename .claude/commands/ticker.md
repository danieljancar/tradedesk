---
description: Daily market brief (Handelsticker). Writes data/ticker/<date>.md and keeps data/ticker/calendar.md current.
---

You write the desk's daily market brief. It's a reference the desk and Daniel come back to, so each brief builds on the earlier ones.

1. Run `uv run desk ticker`. It prints the data file for today, then up to five earlier briefs, then the calendar path.
2. Read the data file, the earlier briefs and `data/ticker/calendar.md` if it exists.
3. Do up to 6 web searches for what the data can't tell you: the macro calendar for the next 8 weeks (FOMC, CPI, jobs, SNB, ECB), what the Fed and other central banks signalled last, the political or policy stories behind the biggest moves, and the strategies or themes traders are talking about this week. Skip a search when an earlier brief already answered it and nothing changed.
4. Write `data/ticker/<today>.md` in the layout below.
5. Update `data/ticker/calendar.md`: one line per future event, `YYYY-MM-DD event, what's expected, why it matters for us`. Drop past events, add new ones, fix changed dates. Keep it sorted.
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
