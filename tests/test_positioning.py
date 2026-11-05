import httpx
import respx

from tradedesk.binance.client import Client
from tradedesk.binance.market import MarketData
from tradedesk.config import Market
from tradedesk.trending import parse

FUT = "https://fapi.example"


@respx.mock
def test_positioning_reads_every_series():
    respx.get(f"{FUT}/futures/data/openInterestHist").mock(
        return_value=httpx.Response(
            200, json=[{"timestamp": 1_000_000, "sumOpenInterestValue": "123.5"}]
        )
    )
    respx.get(f"{FUT}/futures/data/globalLongShortAccountRatio").mock(
        return_value=httpx.Response(200, json=[{"timestamp": 1_000_000, "longShortRatio": "1.8"}])
    )
    respx.get(f"{FUT}/futures/data/topLongShortPositionRatio").mock(
        return_value=httpx.Response(200, json=[{"timestamp": 1_000_000, "longShortRatio": "1.1"}])
    )
    respx.get(f"{FUT}/futures/data/takerlongshortRatio").mock(
        return_value=httpx.Response(200, json=[{"timestamp": 1_000_000, "buySellRatio": "0.9"}])
    )
    respx.get(f"{FUT}/fapi/v1/fundingRate").mock(
        return_value=httpx.Response(200, json=[{"fundingTime": 2_000_000, "fundingRate": "0.0001"}])
    )
    md = MarketData(Client("https://spot.example"), Client(FUT), Market.SPOT)
    out = md.positioning("BTCUSDT")
    assert out["open_interest"] == [{"t": 1000, "usd": 123.5}]
    assert out["long_short"][0]["accounts"] == 1.8
    assert out["top_traders"][0]["positions"] == 1.1
    assert out["taker"][0]["ratio"] == 0.9
    assert out["funding"] == [{"t": 2000, "pct": 0.01}]


@respx.mock
def test_positioning_is_empty_without_a_futures_market():
    respx.get(url__startswith=FUT).mock(
        return_value=httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
    )
    md = MarketData(Client("https://spot.example"), Client(FUT), Market.SPOT)
    assert all(v == [] for v in md.positioning("PAXGUSDT").values())


def test_trending_marks_what_binance_lists():
    payload = {
        "coins": [
            {
                "item": {
                    "id": "pepe",
                    "symbol": "pepe",
                    "name": "Pepe",
                    "market_cap_rank": 40,
                    "data": {
                        "price": 0.00001,
                        "price_change_percentage_24h": {"usd": 12.5},
                        "total_volume": "$1,234,567",
                    },
                }
            },
            {"item": {"id": "x", "symbol": "XYZ", "name": "Xyz", "data": {}}},
        ]
    }
    rows = parse(payload, {"PEPE"})
    assert rows[0]["on_binance"] and rows[0]["change_24h"] == 12.5
    assert rows[0]["volume"] == 1234567
    assert not rows[1]["on_binance"] and rows[1]["price"] is None
