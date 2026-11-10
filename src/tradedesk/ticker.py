"""The daily market brief ("Handelsticker"): the data file the writer works from, and the folder
the briefs pile up in, so each one can build on the last ones."""

from datetime import UTC, date, datetime
from pathlib import Path

from tradedesk import heatmap, macro, trending, wire

KEEP = 5  # earlier briefs the writer reads


def folder(root: Path) -> Path:
    path = root / "ticker"
    path.mkdir(parents=True, exist_ok=True)
    return path


def briefs(root: Path) -> list[Path]:
    """Briefs newest first. The data files and the event calendar sit next to them."""
    return sorted(folder(root).glob("????-??-??.md"), reverse=True)


def _pct(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v:+.{digits}f}%"


def _board_lines() -> list[str]:
    try:
        board = heatmap.board()
    except RuntimeError as e:
        return [f"heatmap unavailable: {e}"]
    out = []
    for g in board["groups"]:
        tiles = [t for t in g["tiles"] if t.get("1d") is not None]
        if not tiles:
            continue
        out.append(f"## {g['name']}")
        for t in sorted(tiles, key=lambda t: t["1d"], reverse=True):
            out.append(
                f"- {t['name']} ({t['symbol']}): 1d {_pct(t['1d'])}, 1w {_pct(t.get('1w'))}, "
                f"1m {_pct(t.get('1m'))}"
            )
    return out


def _macro_lines() -> list[str]:
    data = macro.overview()
    r = data["regime"]
    out = [
        "## Macro",
        f"regime {r['label']}, {r['tailwinds']} tailwinds, {r['headwinds']} headwinds "
        f"of {r['total']}",
    ]
    for d in data["drivers"]:
        if d["value"] is None:
            continue
        out.append(
            f"- {d['name']}: {d['value']:g} {d['unit']} as of {d['as_of']}, "
            f"1w {_pct(d['change_1w'], 2)}, 1m {_pct(d['change_1m'], 2)}, "
            f"3m {_pct(d['change_3m'], 2)}. {d['reason']}"
        )
    fg = data.get("fear_greed") or []
    if fg:
        out.append(
            f"- Fear and greed: {fg[-1]['v']:g} today, {fg[max(0, len(fg) - 8)]['v']:g} a week ago"
        )
    g = data.get("crypto") or {}
    if g:
        out.append(
            f"- Crypto market cap {g['market_cap'] / 1e12:.2f}T, 24h {_pct(g['change_24h'])}, "
            f"volume {g['volume'] / 1e9:.0f}B, BTC dominance {g['btc_dominance']:.1f}%, "
            f"ETH {g['eth_dominance']:.1f}%"
        )
    return out


def _trending_lines() -> list[str]:
    rows = trending.coins(set()) or []
    out = ["## Trending coins (CoinGecko searches)"]
    out += [
        f"- {r['name']} ({r['symbol']}), rank {r['rank']}, 24h {_pct(r['change_24h'])}"
        for r in rows[:15]
    ]
    return out


def _headline_lines(limit: int = 60) -> list[str]:
    out = ["## Headlines, last 48h"]
    for h in wire.headlines()[:limit]:
        when = datetime.fromtimestamp(h["ts"], UTC).strftime("%m-%d %H:%M")
        out.append(f"- [{when}, {h.get('source', '')}, {h.get('category', '')}] {h['title']}")
    return out


def write_data(root: Path, day: date | None = None) -> Path:
    """Everything the brief is written from, in one file. Each part fails on its own."""
    day = day or datetime.now(UTC).date()
    parts = [f"# Market data {day.isoformat()}"]
    for build in (_macro_lines, _board_lines, _trending_lines, _headline_lines):
        try:
            parts += ["", *build()]
        except Exception as e:  # one dead source shouldn't stop the brief
            parts += ["", f"{build.__name__.strip('_')} unavailable: {e}"]
    path = folder(root) / f"{day.isoformat()}-data.md"
    path.write_text("\n".join(parts) + "\n")
    return path
