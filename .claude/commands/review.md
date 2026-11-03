---
description: Weekly review that rewrites lessons.md from the desk's calibration stats
allowed-tools: Bash(uv run desk *) Read Write
---

Run `uv run desk stats`. It replays every idea the desk ever had (taken, passed or rejected) on real 1h candles and prints hit rate and average R by confidence, asset, horizon, side and decision, what the watchlist did after days with zero ideas, and whether the bull or bear side matched the market. Every number carries its sample size n.

Then run `uv run desk journal --days 30` for the theses behind the closed trades.

Read `lessons.md` if it exists and rewrite it. Guardrails:

- **No lesson from fewer than 10 examples.** If a group says "not enough data yet", it gives no lesson. If nothing has n of 10 or more, write the single line `- not enough data yet (n <overall n> resolved ideas)` and stop there.
- Lessons change how the portfolio manager judges ideas: which setups to trust, when to lower confidence, when passing is the better call. They never change risk limits, size, leverage, stops past a level or the minimum reward to risk. Those belong to the risk engine and the human.
- At most 8 lines, each a concrete rule in plain words with the n behind it in brackets, for example:

  `- Trust 75+ confidence less: it hits 38%, no better than 65-74 (n 13)`
  `- Short-horizon ideas lose on average, prefer mid when the case is equal (avg -0.3R, n 11)`
  `- Rejected ideas would have lost, the risk check is earning its keep (avg -0.6R, n 10)`

- Keep a lesson only while the stats still back it. Drop it when the newer numbers contradict it or its group falls under 10.
- A stopped-out trade with a sound thesis is not a lesson. No general trading wisdom, only what this desk's numbers show.

Reply with the overall hit rate and average R with their n, and the lines you added, changed or dropped.
