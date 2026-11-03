---
description: Weekly review of closed trades that rewrites lessons.md
allowed-tools: Bash(uv run desk:*), Read, Write
---

Run `uv run desk journal --days 30`. If there are fewer than 3 closed trades, reply "not enough trades to review yet" and stop.

For each trade the journal shows the thesis the desk had. Judge it against the outcome: did the thesis play out, did the stop sit at a sensible level, was the horizon right, did the target get hit or was it too far. Look for patterns across trades, not single bad luck. A stopped-out trade with a sound thesis is not a lesson.

Read `lessons.md` if it exists. Rewrite it with at most 10 lines, each a concrete rule the portfolio manager can follow, with the evidence in brackets, for example:

`- Skip mid-term longs while funding is above 0.03% (3 of 3 stopped out, Oct)`

Keep lessons that still hold, drop ones the newer trades contradict. No general trading wisdom, only what this desk's trades show.

Reply with the net result, win rate and the lines you changed.
