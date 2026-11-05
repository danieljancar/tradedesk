"""Two sleeves on one account. The core holds fixed weights for the long run and is rebalanced
when an asset drifts past the band; the active sleeve trades with the rest of the equity.

Drift is measured against each asset's own target value: BTC at 60% of a 300 core has a target
of 180, and with a 5% band a buy is proposed under 171 and a trim over 189. Buys become plans
with sleeve "core". Trims sell whole core lots and wait in the trims table for approval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tradedesk import risk
from tradedesk.binance.market import SymbolRules
from tradedesk.config import Market, Settings
from tradedesk.db import Database, now

if TYPE_CHECKING:
    from tradedesk.desk import Desk

TARGET_MULT = 1.9
CASH = {"USDT", "USDC", "FDUSD", "USD", "DAI"}
CLASSES = {"BTC": "bitcoin", "ETH": "ether", "PAXG": "gold", "XAUT": "gold"}
PENDING_PLANS = ("proposed", "approved", "placed")


def asset_class(asset: str) -> str:
    return "cash" if asset in CASH else CLASSES.get(asset, "altcoins")


def rebalance(
    settings: Settings,
    holdings: list[dict],
    equity: float,
    prices: dict[str, float],
    rules: dict[str, SymbolRules],
) -> list[dict]:
    """One row per core asset with its target, value, drift and the action to take.
    holdings are core lots with asset, qty, opened_at and id (None for an order not filled yet)."""
    p = settings.portfolio
    if p.core_pct <= 0:
        return []
    lots: dict[str, list[dict]] = {}
    for h in holdings:
        lots.setdefault(h["asset"], []).append(h)
    assets = [*p.core_targets, *(a for a in lots if a not in p.core_targets)]
    rows = []
    for asset in assets:
        price, r = prices[asset], rules[asset]
        weight = p.core_targets.get(asset, 0.0)
        target = equity * p.core_pct / 100 * weight / 100
        mine = sorted(lots.get(asset, []), key=lambda x: x["opened_at"], reverse=True)
        value = sum(x["qty"] for x in mine) * price
        drift = value - target
        drift_pct = drift / target * 100 if target else (100.0 if value else 0.0)
        row = {
            "asset": asset,
            "weight": weight,
            "price": price,
            "target": round(target, 2),
            "value": round(value, 2),
            "drift": round(drift, 2),
            "drift_pct": round(drift_pct, 2),
            "action": "hold",
            "qty": 0.0,
            "amount": 0.0,
            "lots": [],
            "note": "",
        }
        if target and drift_pct < -p.rebalance_band_pct:
            qty = r.qty(-drift / price)
            stop = max(r.price(price * (1 - p.core_stop_pct / 100)), r.exit_band(price)[0])
            exit_qty = r.qty(qty * (1 - risk.SPOT_FEE_BUFFER))
            if exit_qty < r.min_qty or exit_qty * stop < r.min_notional:
                row["note"] = f"gap of {-drift:.2f} is below the exchange minimum"
            else:
                row |= {"action": "buy", "qty": qty, "amount": round(qty * price, 2)}
        elif drift_pct > p.rebalance_band_pct:
            left, picked = value, []
            for lot in mine:
                lot_value = lot["qty"] * price
                too_small = lot["qty"] < r.min_qty or lot_value < r.min_notional
                if lot["id"] is None or too_small or left - lot_value < target:
                    continue
                picked.append(lot)
                left -= lot_value
            if picked:
                row |= {
                    "action": "trim",
                    "qty": sum(x["qty"] for x in picked),
                    "amount": round(value - left, 2),
                    "lots": [x["id"] for x in picked],
                }
            else:
                row["note"] = "no whole lot can be sold without going under target"
        rows.append(row)
    return rows


def size_buy(settings: Settings, book: risk.Book, row: dict, rules: SymbolRules) -> risk.Verdict:
    """Core buys skip the trade rules but not exchange minimums, free cash, the daily loss limit
    or the drawdown pause."""
    reasons = []
    if settings.market is Market.FUTURES:
        reasons.append("the core sleeve needs market = spot, futures net every symbol")
    reasons += risk.account_blocks(settings, book)
    price = row["price"]
    low, high = rules.exit_band(price)
    stop = max(rules.price(price * (1 - settings.portfolio.core_stop_pct / 100)), low)
    take_profit = min(rules.price(price * TARGET_MULT), high)
    qty = rules.qty(min(row["qty"], max(0.0, book.free_quote) * 0.995 / price))
    exit_qty = rules.qty(qty * (1 - risk.SPOT_FEE_BUFFER))
    if exit_qty < rules.min_qty or exit_qty * stop < rules.min_notional:
        reasons.append(
            f"size {qty} ({qty * price:.2f} {settings.quote}) with free cash "
            f"{book.free_quote:.2f} is below the exchange minimum {rules.min_notional}"
        )
    return risk.Verdict(
        ok=not reasons,
        reasons=reasons,
        entry=price,
        stop=stop,
        take_profit=take_profit,
        qty=qty,
        risk_amount=qty * (price - stop),
        reward_risk=round((take_profit - price) / (price - stop), 2),
        leverage=1,
    )


def holdings(db: Database) -> list[dict]:
    lots = db.all(
        "SELECT id, asset, qty, opened_at FROM positions WHERE status = 'open' AND sleeve = 'core' "
        "AND id NOT IN (SELECT position_id FROM trims WHERE status = 'approved')"
    )
    lots += [
        {"id": None, "asset": p["asset"], "qty": p["qty"] or 0, "opened_at": p["created_at"]}
        for p in db.all(
            "SELECT * FROM plans WHERE sleeve = 'core' AND side = 'long' "
            "AND status IN ('approved', 'placed')"
        )
    ]
    return lots


def current(desk: Desk, equity: float) -> list[dict]:
    s = desk.settings
    lots = holdings(desk.db)
    assets = {*s.portfolio.core_targets, *(x["asset"] for x in lots)}
    prices = {a: desk.broker.price(s.symbol(a)) for a in assets}
    rules = {a: desk.broker.rules(s.symbol(a)) for a in assets}
    return rebalance(s, lots, equity, prices, rules)


def _buy_plan(desk: Desk, run_id: str | None, row: dict, book: risk.Book) -> dict:
    s = desk.settings
    symbol = s.symbol(row["asset"])
    verdict = size_buy(s, book, row, desk.broker.rules(symbol))
    status = "proposed" if verdict.ok else "rejected"
    plan_id = desk.db.insert(
        "plans",
        run_id=run_id,
        asset=row["asset"],
        symbol=symbol,
        horizon="long",
        side="long",
        rating="buy",
        entry_type="market",
        entry=verdict.entry,
        stop=verdict.stop,
        take_profit=verdict.take_profit,
        confidence=100,
        thesis=(
            f"Core rebalance: {row['asset']} at {row['value']:.2f} of a {row['target']:.2f} "
            f"target ({row['weight']:g}% of the core)."
        ),
        invalidation=(
            f"Core stop {(1 - verdict.stop / verdict.entry) * 100 if verdict.entry else 0:.0f}% "
            "under entry, the weights change, "
            "or the core is switched off."
        ),
        status=status,
        reasons="; ".join(verdict.reasons),
        qty=verdict.qty,
        risk_amount=verdict.risk_amount,
        reward_risk=verdict.reward_risk,
        leverage=1,
        sleeve="core",
        created_at=now(),
        updated_at=now(),
    )
    if verdict.ok:
        book.free_quote -= verdict.notional
    desk.log(
        "risk",
        "pass" if verdict.ok else "reject",
        f"Core buy {row['asset']} {verdict.qty:g} at {verdict.entry:g}: {status}",
        "\n".join(verdict.reasons),
        refs=[f"plan:{plan_id}"],
    )
    return {"id": plan_id, "asset": row["asset"], "status": status, "reasons": verdict.reasons}


def _trims(desk: Desk, run_id: str | None, row: dict) -> list[dict]:
    out = []
    for lot_id in row["lots"]:
        lot = desk.db.one("SELECT * FROM positions WHERE id = ?", lot_id)
        value = lot["qty"] * row["price"]
        trim_id = desk.db.insert(
            "trims",
            run_id=run_id,
            position_id=lot_id,
            asset=row["asset"],
            qty=lot["qty"],
            price=row["price"],
            value=value,
            reason=(
                f"{row['asset']} is at {row['value']:.2f} against a target of {row['target']:.2f}, "
                f"selling the lot from {lot['opened_at'][:10]}"
            ),
            status="proposed",
            created_at=now(),
            updated_at=now(),
        )
        out.append({"id": trim_id, "position": lot_id, "asset": row["asset"], "value": value})
    return out


def propose(desk: Desk) -> dict:
    """Replace earlier open proposals with fresh ones and write rebalance.md."""
    db, s = desk.db, desk.settings
    with db.tx() as c:
        c.execute(
            "UPDATE plans SET status = 'cancelled', updated_at = ? "
            "WHERE sleeve = 'core' AND status = 'proposed'",
            (now(),),
        )
        c.execute(
            "UPDATE trims SET status = 'cancelled', updated_at = ? WHERE status = 'proposed'",
            (now(),),
        )
    run_id = desk.run_id() or desk.start_run()
    book = desk.book()
    rows = current(desk, book.equity)
    plans, trims = [], []
    if s.market is Market.FUTURES:
        desk.log("desk", "output", "Rebalance skipped, the core sleeve needs market = spot")
        return {"rows": rows, "plans": [], "trims": []}
    for row in rows:
        if row["action"] == "buy":
            plans.append(_buy_plan(desk, run_id, row, book))
        elif row["action"] == "trim":
            trims += _trims(desk, run_id, row)
    if s.execution.auto_execute:
        for p in plans:
            if p["status"] == "proposed":
                desk.approve(p["id"])
        for t in trims:
            if t["asset"] in s.portfolio.core_targets:
                approve_trim(desk, t["id"])
    text = report(s, book.equity, rows, plans, trims)
    (desk.run_dir(run_id) / "rebalance.md").write_text(text)
    desk.log("desk", "output", f"Rebalance: {len(plans)} buys, {len(trims)} trims", text)
    return {"rows": rows, "plans": plans, "trims": trims}


def report(
    settings: Settings, equity: float, rows: list[dict], plans: list[dict], trims: list[dict]
) -> str:
    p = settings.portfolio
    core = equity * p.core_pct / 100
    lines = [
        f"# Core rebalance ({p.core_pct:g}% of {equity:.2f} {settings.quote} = {core:.2f})",
        f"band {p.rebalance_band_pct:g}% of each target, core stop {p.core_stop_pct:g}% "
        "under entry",
        *[row_line(r) for r in rows],
    ]
    lines += [
        f"- plan {x['id']} buy {x['asset']}: {x['status']} {'; '.join(x['reasons'])}".rstrip()
        for x in plans
    ]
    lines += [
        f"- trim {x['id']} sells position {x['position']} ({x['asset']}, {x['value']:.2f})"
        for x in trims
    ]
    return "\n".join(lines) + "\n"


def row_line(r: dict) -> str:
    action = {
        "buy": f"buy {r['qty']:g} for {r['amount']:.2f}",
        "trim": f"sell lots {', '.join(map(str, r['lots']))} for {r['amount']:.2f}",
    }.get(r["action"], r["note"] or "inside the band")
    return (
        f"- {r['asset']} {r['weight']:g}%: target {r['target']:.2f}, now {r['value']:.2f} "
        f"({r['drift_pct']:+.1f}%), {action}"
    )


def book_lines(desk: Desk, equity: float) -> list[str]:
    p = desk.settings.portfolio
    if p.core_pct <= 0:
        return []
    rows = current(desk, equity)
    held = sum(r["value"] for r in rows)
    waiting = pending(desk.db)
    lines = [
        "## Core",
        f"core target {p.core_pct:g}% of equity, now {held / equity * 100:.1f}% ({held:.2f}). "
        "Core lots are rebalanced by `desk rebalance`, not traded.",
        *[row_line(r) for r in rows],
    ]
    if waiting["plans"] or waiting["trims"]:
        lines.append(
            "- rebalance waiting: "
            + ", ".join(
                [f"plan {x['id']} buy {x['asset']} ({x['status']})" for x in waiting["plans"]]
                + [f"trim {x['id']} {x['asset']} ({x['status']})" for x in waiting["trims"]]
            )
        )
    return lines


def approve_trim(desk: Desk, trim_id: int) -> None:
    trim = desk.db.one("SELECT * FROM trims WHERE id = ?", trim_id)
    if trim is None or trim["status"] != "proposed":
        raise ValueError(f"trim {trim_id} is not waiting for approval")
    desk.db.update("trims", trim_id, status="approved", updated_at=now())
    desk.log("desk", "approve", f"Trim {trim_id} approved ({trim['asset']})")


def reject_trim(desk: Desk, trim_id: int) -> None:
    desk.db.update("trims", trim_id, status="cancelled", updated_at=now())
    desk.log("desk", "reject", f"Trim {trim_id} dropped")


def execute_trims(desk: Desk, only: int | None = None) -> list[str]:
    out = []
    for t in desk.db.all("SELECT * FROM trims WHERE status = 'approved' ORDER BY id"):
        if only is not None and t["id"] != only:
            continue
        try:
            desk.close(t["position_id"], "core rebalance")
        except Exception as e:
            desk.db.update("trims", t["id"], status="failed", updated_at=now())
            desk.log("exchange", "error", f"Trim {t['id']} failed", str(e))
            out.append(f"trim {t['id']}: failed, {e}")
            continue
        desk.db.update("trims", t["id"], status="done", updated_at=now())
        out.append(f"trim {t['id']}: sold position {t['position_id']}")
    return out


def pending(db: Database) -> dict:
    return {
        "plans": db.all(
            "SELECT * FROM plans WHERE sleeve = 'core' AND status IN (?, ?, ?) ORDER BY id",
            *PENDING_PLANS,
        ),
        "trims": db.all("SELECT * FROM trims WHERE status IN ('proposed', 'approved') ORDER BY id"),
    }


def state(desk: Desk, fx: dict) -> dict:
    """Equity in quote and base currency, sleeves, allocation, core drift, pending rebalances."""
    s = desk.settings
    equity = desk.broker.equity()
    by_asset: dict[str, float] = {}
    core_value = 0.0
    for p in desk.db.open_positions():
        value = p["qty"] * desk.broker.price(p["symbol"])
        by_asset[p["asset"]] = by_asset.get(p["asset"], 0.0) + value
        if p["sleeve"] == "core":
            core_value += value
    quote_balance = getattr(desk.broker, "quote_balance", None)
    cash = quote_balance() if quote_balance else equity - sum(by_asset.values())
    by_asset[s.quote] = by_asset.get(s.quote, 0.0) + max(0.0, cash)
    total = sum(by_asset.values()) or 1.0
    by_class: dict[str, float] = {}
    for asset, value in by_asset.items():
        by_class[asset_class(asset)] = by_class.get(asset_class(asset), 0.0) + value
    rate = fx.get("rate")

    def share(value: float, of: float) -> float:
        return round(value / of * 100, 2) if of else 0.0

    return {
        "quote": s.quote,
        "base_currency": s.portfolio.base_currency,
        "equity": round(equity, 2),
        "equity_base": round(equity * rate, 2) if rate else None,
        "fx": fx,
        "sleeves": {
            "active": {
                "value": round(equity - core_value, 2),
                "share": share(equity - core_value, equity),
            },
            "core": {
                "value": round(core_value, 2),
                "share": share(core_value, equity),
                "target_pct": s.portfolio.core_pct,
            },
        },
        "allocation": {
            "by_asset": [
                {"asset": a, "value": round(v, 2), "share": share(v, total)}
                for a, v in sorted(by_asset.items(), key=lambda x: -x[1])
            ],
            "by_class": [
                {"class": c, "value": round(v, 2), "share": share(v, total)}
                for c, v in sorted(by_class.items(), key=lambda x: -x[1])
            ],
        },
        "core": current(desk, equity) if s.portfolio.core_pct > 0 else [],
        "pending": pending(desk.db),
    }
