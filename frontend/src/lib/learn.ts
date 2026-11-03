// Plain-language layer: a glossary, and rules that turn the snapshot numbers into sentences.
// Everything here is computed from the run's own numbers. Nothing is generated or guessed.

export type Term = { term: string; short: string; long?: string; match?: RegExp };
export const GLOSSARY: Record<string, Term> = {
  price: {
    term: "Price",
    short: "The last traded price on Binance, in USDT.",
    long: "USDT is a stablecoin that tracks the US dollar, so a BTC price of 77,890 means one bitcoin costs about 77,890 dollars right now.",
  },
  candle: {
    term: "Candle",
    short: "One block of time on a chart: where price opened, closed, and its high and low.",
    long: "The desk reads 4-hour, daily and weekly candles. 4h shows the next few days, 1d the next weeks, 1w the bigger picture.",
    match: /\bcandles?\b/i,
  },
  timeframe: {
    term: "4h / 1d / 1w",
    short: "Timeframes: 4-hour, daily and weekly charts.",
    long: "Short trades (days) lean on 4h, mid trades (weeks) on 1d, long trades (months) on 1w. They often disagree, and that disagreement is useful information.",
    match: /\b(4h|1d|1w)\b/,
  },
  ema: {
    term: "EMA",
    short: "Exponential moving average: the average price of the last N candles, weighted to recent ones.",
    long: "ema20 is the short-term trend, ema50 the medium, ema200 the long. Price above all three, stacked 20 > 50 > 200, is a clean uptrend. Price below them is a downtrend. Mixed means sideways.",
    match: /\bema\s?(20|50|200)?\b/i,
  },
  rsi: {
    term: "RSI",
    short: "Relative Strength Index, 0 to 100: how hard buyers pushed versus sellers over the last 14 candles.",
    long: "Above 50 buyers had the edge, below 50 sellers did. Over 70 is called overbought (stretched up), under 30 oversold (stretched down). Stretched doesn't mean it turns. It means moves in that direction are getting tired.",
    match: /\bRSI\b/i,
  },
  macd: {
    term: "MACD histogram",
    short: "Whether momentum is speeding up or slowing down.",
    long: "Positive means the short-term trend is pulling ahead of the longer one (momentum building). Negative means it's falling behind. Watch for the sign flipping, that's often the earliest hint of a turn.",
    match: /\bmacd(_h| hist(ogram)?)?\b/i,
  },
  atr: {
    term: "ATR",
    short: "Average True Range: how far price typically moves in one candle.",
    long: "If daily ATR is 2.5%, a normal day swings about 2.5%. A stop closer than that is likely to get hit by ordinary noise, which is why the risk engine refuses stops under half an ATR.",
    match: /\bATR\b/i,
  },
  volume: {
    term: "Volume vs average",
    short: "How much traded in the last candle compared with the 20 before it.",
    long: "1.0 is normal. Under 0.7 is quiet: moves on low volume are less trustworthy. Over 1.5 is busy: something is happening.",
    match: /\bvol\/avg20\b|\bvolume\b/i,
  },
  support: {
    term: "Support",
    short: "A price where buyers stepped in before and stopped a fall.",
    long: "The desk finds these from past swing lows. Price often bounces near support. If it breaks through and closes below, that level often turns into resistance.",
    match: /\bsupports?\b/i,
  },
  resistance: {
    term: "Resistance",
    short: "A price where sellers showed up before and stopped a rise.",
    long: "Found from past swing highs. Breaking and closing above resistance is a common signal that buyers have taken over.",
    match: /\bresistances?\b/i,
  },
  funding: {
    term: "Funding rate",
    short: "A fee traders on perpetual futures pay each other every 8 hours.",
    long: "Positive means people betting up (longs) pay people betting down (shorts). +0.01% per 8h is the exchange's default baseline. Much higher means longs are crowded and paying to stay in. Negative means shorts are crowded.",
    match: /\bfunding\b/i,
  },
  oi: {
    term: "Open interest (OI)",
    short: "The total value of futures bets still open.",
    long: "Rising OI means new money is placing bets. Falling OI means people are closing bets. Price up with OI up is a trend with fuel. Price down with OI down is often just a clean-out.",
    match: /\bOI\b|\bopen interest\b/i,
  },
  longshort: {
    term: "Long/short ratio",
    short: "How many accounts are betting up for every one betting down.",
    long: "2.57 means 2.57 accounts long for each account short. When one side is very crowded, a move against them can force many to exit at once and the move gets sharper. People call that a flush or squeeze.",
    match: /\blong\/short\b/i,
  },
  crowding: {
    term: "Crowding / flush",
    short: "Too many traders on the same side, and the sharp move when they're forced out.",
    long: "Crowded longs plus a dip can trigger stop losses and liquidations in a chain, pushing price down fast. That's a flush. The opposite on shorts is a squeeze.",
    match: /\bcrowd(ed|ing)\b|\bflush\b|\bsqueeze\b/i,
  },
  feargreed: {
    term: "Fear & Greed index",
    short: "A 0-100 mood score for the crypto market, built from volatility, volume, social media and more.",
    long: "Under 25 is extreme fear, over 75 extreme greed. It's a crowd-mood reading, not a signal by itself. Some traders deliberately lean against extremes.",
    match: /\bfear (&|and) greed\b/i,
  },
  dominance: {
    term: "Dominance",
    short: "Bitcoin's share of the whole crypto market's value.",
    long: "Rising BTC dominance usually means money is hiding in bitcoin and the rest of the market is weaker.",
    match: /\bdominance\b/i,
  },
  long: {
    term: "Long",
    short: "A bet that price goes up. You buy now, sell higher later.",
    long: "On spot (what this desk trades by default) you can only go long. Betting down (short) needs futures.",
    match: /\blongs?\b(?!\/)/i,
  },
  short: {
    term: "Short",
    short: "A bet that price goes down. Only possible on futures.",
    long: "You borrow and sell now, then buy back cheaper. Losses on a short have no ceiling if price keeps rising, which is why the stop matters even more.",
    match: /\bshorts?\b(?! \(days\)| term)/i,
  },
  spot: {
    term: "Spot",
    short: "Buying the actual coin. No borrowing, no leverage, long only.",
    long: "The safest way to trade: the most you can lose is what you put in that trade.",
    match: /\bspot\b/i,
  },
  futures: {
    term: "Futures and leverage",
    short: "Contracts that track the price and let you borrow to make bigger bets.",
    long: "3x leverage means a 1% move becomes a 3% gain or loss. Most people who trade with leverage lose money.",
    match: /\bfutures\b|\bleverage\b/i,
  },
  entry: {
    term: "Entry",
    short: "The price the trade opens at.",
    long: "A limit entry waits for that price. A market entry buys right away at whatever the price is.",
    match: /\bentry\b/i,
  },
  stop: {
    term: "Stop loss",
    short: "The price where the trade is closed to cap the loss.",
    long: "This desk places the stop on Binance itself, so it works even if your laptop is off. It sits just past a real level, so the idea is wrong if price gets there, not just noisy.",
    match: /\bstop(-loss| loss)?s?\b/i,
  },
  target: {
    term: "Take profit / target",
    short: "The price where the trade closes in profit.",
    long: "Usually at the next real resistance (for a long), because that's where sellers have shown up before.",
    match: /\btake[ _-]profit\b|\btargets?\b/i,
  },
  rr: {
    term: "Reward to risk (R/R)",
    short: "How much the trade can make for each unit it can lose.",
    long: "R/R 2.4 means the target is 2.4 times further away than the stop. With R/R over 2 you can be wrong more than half the time and still come out ahead. The desk refuses anything under 2.",
    match: /\bR\/R\b|\breward[ -]to[ -]risk\b/i,
  },
  r: {
    term: "R (R-multiple)",
    short: "Profit or loss measured in units of the risk taken.",
    long: "If a trade risked 10 USDT and made 24, that's +2.4R. Losing the full stop is -1R. It makes trades of different sizes comparable.",
    match: /\b[+-]?\d+(\.\d+)?R\b/,
  },
  risk: {
    term: "Risk per trade",
    short: "What you lose if the stop is hit, as a share of the account.",
    long: "The desk sizes every trade so a stop-out costs 1% of equity. Ten losses in a row cost about 10%, not everything.",
    match: /\brisk per trade\b|\bopen risk\b/i,
  },
  drawdown: {
    term: "Drawdown",
    short: "How far the account has fallen from its highest point.",
    long: "At 15% drawdown the desk stops opening new trades until equity recovers.",
    match: /\bdrawdown\b/i,
  },
  equity: {
    term: "Equity",
    short: "What the account is worth right now, including open trades.",
    match: /\bequity\b/i,
  },
  horizon: {
    term: "Horizon",
    short: "How long a trade is meant to run: short (days), mid (weeks), long (months).",
    long: "Positions are closed automatically if they outlive their horizon: 3, 21 or 120 days by default.",
    match: /\bhorizon\b/i,
  },
  confidence: {
    term: "Confidence",
    short: "How sure the portfolio manager is, 0 to 100.",
    long: "Under 60 the risk engine refuses the trade. Lower confidence also means a smaller size.",
    match: /\bconfidence\b/i,
  },
  bias: {
    term: "Bias",
    short: "The direction the chart leans: up, down or none.",
    match: /\bbias\b/i,
  },
  range: {
    term: "Range",
    short: "Price moving sideways between a floor and a ceiling, without a clear trend.",
    match: /\brange\b/i,
  },
  momentum: {
    term: "Momentum",
    short: "How fast and how strongly price is moving in one direction.",
    match: /\bmomentum\b/i,
  },
  etf: {
    term: "ETF flows",
    short: "Money going into or out of exchange-traded funds that hold bitcoin, like BlackRock's IBIT.",
    long: "Big outflows mean large investors are selling through the stock market. It's one of the clearest signs of institutional mood.",
    match: /\bETFs?\b|\bIBIT\b/,
  },
  cpi: {
    term: "CPI, jobs report, FOMC",
    short: "US inflation data, employment data and the Federal Reserve's rate meetings.",
    long: "They move interest-rate expectations. Higher-for-longer rates usually hurt crypto. Traders often avoid new risk right before them.",
    match: /\bCPI\b|\bFOMC\b|\bjobs report\b|\bJOLTS\b/,
  },
  paper: {
    term: "Paper mode",
    short: "Simulated trading with fake money on real prices.",
    long: "Fills are simulated on live Binance prices. Nothing reaches the exchange.",
    match: /\bpaper\b/i,
  },
};

const TERM_KEYS = Object.keys(GLOSSARY).filter((k) => GLOSSARY[k].match);

// ---------- number formatting ----------
export function px(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "n/a";
  const a = Math.abs(n);
  if (a >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (a >= 1) return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return Number(n.toPrecision(4)).toString();
}
export const pc = (n: number | null | undefined, d = 1) => (n == null ? "n/a" : `${n >= 0 ? "+" : ""}${n.toFixed(d)}%`);

// ---------- reading one asset ----------
function trend(price: number, f: any) {
  if (!f || f.ema20 == null || f.ema50 == null) return { dir: "none", text: "not enough data" };
  const above = [price > f.ema20, price > f.ema50, f.ema200 == null ? null : price > f.ema200];
  const stackedUp = f.ema20 > f.ema50 && (f.ema200 == null || f.ema50 > f.ema200);
  const stackedDown = f.ema20 < f.ema50 && (f.ema200 == null || f.ema50 < f.ema200);
  if (above.every((x) => x !== false) && stackedUp) return { dir: "up", text: "above every average, averages stacked upward" };
  if (above.every((x) => x !== true) && stackedDown) return { dir: "down", text: "below every average, averages stacked downward" };
  const n = above.filter((x) => x === true).length;
  return { dir: "range", text: `above ${n} of ${above.filter((x) => x !== null).length} averages, no clean stack` };
}

function rsiRead(r: number | null) {
  if (r == null) return "not in data";
  if (r >= 70) return "overbought: buyers pushed hard, pullbacks are common from here";
  if (r >= 55) return "buyers in control";
  if (r > 45) return "balanced between buyers and sellers";
  if (r > 30) return "sellers have the edge, but it isn't oversold yet (that's under 30)";
  return "oversold: selling has been heavy. Bounces often start here, but it can stay low";
}

function nearest(levels: any, price: number) {
  const all = [...(levels?.["1d"]?.support || []), ...(levels?.["4h"]?.support || [])];
  const allR = [...(levels?.["1d"]?.resistance || []), ...(levels?.["4h"]?.resistance || [])];
  const below: number | undefined = all.filter((x: number) => x < price).sort((a: number, b: number) => b - a)[0];
  const above: number | undefined = allR.filter((x: number) => x > price).sort((a: number, b: number) => a - b)[0];
  return { below, above };
}

export type Read = { key: string; label: string; value: string; text: string; term: string; tone?: string };
export function readAsset(asset: string, f: any) {
  const price = f.price;
  const frames = f.frames || {};
  const trends = Object.fromEntries(["4h", "1d", "1w"].map((tf) => [tf, trend(price, { ...frames[tf] })]));
  const d1 = frames["1d"] || {};
  const lv = nearest(f.levels, price);
  const der = f.derivatives;
  const lines: Read[] = [];

  lines.push({
    key: "trend", label: "Trend",
    value: ["4h", "1d", "1w"].map((tf) => `${tf} ${{ up: "▲", down: "▼", range: "▸", none: "·" }[trends[tf].dir as string]}`).join("  "),
    text: `Days (4h): ${trends["4h"].text}. Weeks (1d): ${trends["1d"].text}. Months (1w): ${trends["1w"].text}.`,
    term: "ema",
  });
  if (d1.rsi != null) lines.push({
    key: "rsi", label: "RSI 1d", value: d1.rsi.toFixed(0), term: "rsi",
    text: `${d1.rsi.toFixed(0)} is ${rsiRead(d1.rsi)}.`,
    tone: d1.rsi >= 55 ? "up" : d1.rsi <= 45 ? "down" : "flat",
  });
  if (d1.macd_h != null) lines.push({
    key: "macd", label: "Momentum", value: d1.macd_h >= 0 ? "rising" : "fading", term: "macd",
    text: d1.macd_h >= 0
      ? "The MACD histogram is positive: the short-term trend is pulling ahead of the longer one."
      : "The MACD histogram is negative: the short-term trend is losing ground to the longer one.",
    tone: d1.macd_h >= 0 ? "up" : "down",
  });
  if (d1.atr != null) lines.push({
    key: "atr", label: "ATR 1d", value: `${d1.atr_pct.toFixed(1)}%`, term: "atr",
    text: `On a normal day ${asset} swings about ${px(d1.atr)}. A stop closer than half of that (${px(d1.atr / 2)}) gets hit by noise, so the risk engine refuses it.`,
  });
  if (lv.below || lv.above) lines.push({
    key: "levels", label: "Support → Res.",
    value: `${lv.below ? px(lv.below) : "?"} → ${lv.above ? px(lv.above) : "?"}`, term: "support",
    text: [
      lv.below && `Buyers stepped in near ${px(lv.below)} before, ${((price - lv.below) / price * 100).toFixed(1)}% below now.`,
      lv.above && `Sellers showed up near ${px(lv.above)}, ${((lv.above - price) / price * 100).toFixed(1)}% above.`,
    ].filter(Boolean).join(" "),
  });
  if (d1.vol_ratio != null) lines.push({
    key: "vol", label: "Volume", term: "volume",
    value: `${d1.vol_ratio.toFixed(1)}×`,
    text: `Today's volume is ${d1.vol_ratio.toFixed(1)}× the 20-day average. ${d1.vol_ratio < 0.7 ? "Moves on thin volume are less trustworthy." : d1.vol_ratio > 1.5 ? "Something is going on, moves carry more weight." : "Nothing unusual."}`,
  });
  if (der) {
    const fr = der.funding_pct;
    lines.push({
      key: "funding", label: "Funding", value: `${fr >= 0 ? "+" : ""}${fr.toFixed(4)}%`, term: "funding",
      text: Math.abs(fr) <= 0.011
        ? "Right at the default baseline. Futures traders aren't paying up to hold either side."
        : fr > 0 ? "Longs are paying above baseline to stay in. The long side is getting crowded."
          : "Shorts are paying to stay in. The short side is crowded, a squeeze up is possible.",
      tone: Math.abs(fr) <= 0.011 ? "flat" : fr > 0 ? "warn" : "up",
    });
    const ls = der.long_short_ratio;
    lines.push({
      key: "ls", label: "Long/short", value: ls.toFixed(2), term: "longshort",
      text: ls > 2
        ? `${ls.toFixed(2)} accounts long for every short. The crowd is leaning up. If price dips, their exits can make the drop sharper.`
        : ls < 0.8 ? "More accounts short than long. A rise could squeeze them out and speed it up."
          : "Fairly balanced between longs and shorts.",
      tone: ls > 2 || ls < 0.8 ? "warn" : "flat",
    });
    const oi = der.oi_change_7d_pct;
    lines.push({
      key: "oi", label: "OI 7d", value: pc(oi, 1), term: "oi",
      text: oi < -2 ? "Traders are closing futures bets. Less fuel for a big move either way."
        : oi > 2 ? "New money is opening futures bets. Moves can get bigger from here."
          : "Roughly unchanged this week.",
    });
  }

  const bias = trends["1d"].dir;
  const headline = bias === "up"
    ? `${asset} is trending up on the daily chart.`
    : bias === "down" ? `${asset} is trending down on the daily chart.`
      : `${asset} is moving sideways on the daily chart.`;
  const tail: string[] = [];
  if (d1.rsi != null) tail.push(d1.rsi < 45 ? "momentum is soft" : d1.rsi > 55 ? "momentum is firm" : "momentum is neutral");
  if (der && der.long_short_ratio > 2) tail.push("and the crowd is leaning long");
  return {
    headline: `${headline} ${tail.length ? tail.join(" ").replace(/^./, (c) => c.toUpperCase()) + "." : ""}`.trim(),
    trends, lines, levels: lv,
  };
}

export function readMood(m: any) {
  if (!m) return null;
  const fg = m.fear_greed?.[0];
  if (!fg) return null;
  const week: number[] = m.fear_greed.map((d: any) => d.value);
  const text = fg.value < 25 ? "Extreme fear. People are scared, and selling has been heavy."
    : fg.value < 45 ? "Fear. The mood is cautious."
      : fg.value <= 55 ? "Neutral."
        : fg.value <= 75 ? "Greed. The mood is optimistic."
          : "Extreme greed. People are euphoric, which is often when risk is highest.";
  return { value: fg.value, label: fg.label, text, week };
}

export function planStory(p: any, quote = "USDT") {
  const dir = p.side === "long" ? "Buy" : "Sell short";
  const when = p.entry_type === "limit" ? `if price reaches ${px(p.entry)}` : `now, around ${px(p.entry)}`;
  const risk = Number(p.risk_amount || 0);
  const gain = risk && p.reward_risk ? risk * p.reward_risk : null;
  return [
    `${dir} ${p.asset} ${when}.`,
    `If it goes the wrong way to ${px(p.stop)}, the exchange closes it${risk ? ` and the desk loses ${risk.toFixed(2)} ${quote}` : ""}.`,
    `If it reaches ${px(p.take_profit)}, it closes in profit${gain ? `, about ${gain.toFixed(2)} ${quote}` : ""}.`,
    p.reward_risk ? `That's ${p.reward_risk}× more upside than downside (R/R).` : "",
  ].filter(Boolean).join(" ");
}

// ---------- annotate prose with glossary buttons ----------
export function annotate(root: HTMLElement) {
  const seen = new Set();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement?.closest("button, a, code, .term") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  for (const node of nodes) {
    let text = node.nodeValue || "";
    const frag = document.createDocumentFragment();
    let changed = false;
    while (text) {
      let best: { k: string; m: RegExpExecArray } | null = null;
      for (const k of TERM_KEYS) {
        if (seen.has(k)) continue;
        const m = GLOSSARY[k].match!.exec(text);
        if (m && (!best || m.index < best.m.index)) best = { k, m };
      }
      if (!best) break;
      const hit: { k: string; m: RegExpExecArray } = best;
      changed = true;
      seen.add(hit.k);
      frag.append(text.slice(0, hit.m.index));
      const b = document.createElement("button");
      b.type = "button";
      b.className = "term";
      b.dataset.term = hit.k;
      b.textContent = hit.m[0];
      frag.append(b);
      text = text.slice(hit.m.index + hit.m[0].length);
    }
    if (changed) {
      frag.append(text);
      node.replaceWith(frag);
    }
  }
}
