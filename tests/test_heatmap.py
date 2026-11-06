from tradedesk import heatmap

DAY = 86_400


def spark(symbol, closes, price):
    start = 1_790_000_000
    return {
        "symbol": symbol,
        "response": [
            {
                "meta": {"regularMarketPrice": price, "currency": "USD"},
                "timestamp": [start + i * DAY for i in range(len(closes))],
                "indicators": {"quote": [{"close": closes}]},
            }
        ],
    }


def test_changes_by_calendar_days():
    closes = [100.0 + i for i in range(40)]  # one close a day, the last is 139
    row = heatmap.parse({"spark": {"result": [spark("BTC-USD", closes, 139.0)]}})["BTC-USD"]
    assert round(row["1d"], 2) == round((139 / 138 - 1) * 100, 2)
    assert round(row["1w"], 2) == round((139 / 132 - 1) * 100, 2)
    assert round(row["1m"], 2) == round((139 / 109 - 1) * 100, 2)


def test_gaps_and_missing_prices():
    rows = heatmap.parse(
        {"spark": {"result": [spark("A", [10.0, None, 12.0], 12.0), spark("B", [1.0], None)]}}
    )
    assert "B" not in rows
    assert rows["A"]["1m"] is None and round(rows["A"]["1d"]) == 20


def test_board_groups_and_fallback(monkeypatch):
    heatmap._cache = None
    monkeypatch.setattr(heatmap, "caps", lambda symbols: {"^GSPC": 1.0})
    monkeypatch.setattr(
        heatmap,
        "_fetch",
        lambda symbols: {s: {"price": 1.0, "1d": 0.5, "1w": None, "1m": None} for s in symbols},
    )
    out = heatmap.board()
    names = [g["name"] for g in out["groups"]]
    assert names[0] == "Indexes" and "Swiss stocks" in names
    assert out["groups"][0]["tiles"][0]["name"] == "S&P 500"
    assert out["groups"][0]["tiles"][0]["cap"] == 1.0
    assert out["groups"][0]["tiles"][1]["cap"] is None
