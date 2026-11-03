import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from tradedesk.binance.client import BinanceError, Client
from tradedesk.broker.futures import FuturesBroker
from tradedesk.broker.spot import SpotBroker
from tradedesk.config import Market

from .conftest import FakeMarket

SPOT = "https://testnet.binance.vision"
FUT = "https://testnet.binancefuture.com"


def params(call) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(str(call.request.url)).query).items()}


def plan(**kw) -> dict:
    return (
        dict(
            symbol="BTCUSDT",
            side="long",
            entry_type="limit",
            entry=99.0,
            stop=94.0,
            take_profit=111.0,
            qty=0.5,
            leverage=2,
        )
        | kw
    )


@respx.mock
def test_spot_limit_entry_sends_otoco_with_exchange_stop(settings):
    route = respx.post(f"{SPOT}/api/v3/orderList/otoco").mock(
        return_value=httpx.Response(
            200,
            json={
                "orderListId": 7,
                "orderReports": [
                    {"type": "LIMIT", "orderId": 1},
                    {"type": "LIMIT_MAKER", "orderId": 2},
                    {"type": "STOP_LOSS", "orderId": 3},
                ],
            },
        )
    )
    broker = SpotBroker(settings, Client(SPOT, "k", "s"), FakeMarket())
    placed = broker.place(plan())
    sent = params(route.calls[0])
    assert sent["workingSide"] == "BUY" and sent["workingPrice"] == "99"
    assert sent["pendingBelowType"] == "STOP_LOSS" and sent["pendingBelowStopPrice"] == "94"
    assert sent["pendingAboveType"] == "LIMIT_MAKER" and sent["pendingAbovePrice"] == "111"
    assert float(sent["pendingQuantity"]) < 0.5
    assert "signature" in sent
    assert route.calls[0].request.headers["X-MBX-APIKEY"] == "k"
    assert placed.refs == {"list": 7, "entry": 1, "target": 2, "stop": 3}


@respx.mock
def test_spot_market_entry_sells_back_when_protection_fails(settings):
    orders = respx.post(f"{SPOT}/api/v3/order").mock(
        side_effect=[
            httpx.Response(200, json={"executedQty": "0.5", "cummulativeQuoteQty": "50"}),
            httpx.Response(200, json={}),
        ]
    )
    respx.post(f"{SPOT}/api/v3/orderList/oco").mock(
        return_value=httpx.Response(400, json={"code": -2010, "msg": "rejected"})
    )
    broker = SpotBroker(settings, Client(SPOT, "k", "s"), FakeMarket())
    with pytest.raises(BinanceError):
        broker.place(plan(entry_type="market"))
    assert params(orders.calls[1])["side"] == "SELL"


@respx.mock
def test_futures_closes_position_when_stop_fails(settings):
    s = settings.model_copy(update={"market": Market.FUTURES})
    respx.post(f"{FUT}/fapi/v1/marginType").mock(
        return_value=httpx.Response(400, json={"code": -4046, "msg": "No need to change"})
    )
    respx.post(f"{FUT}/fapi/v1/leverage").mock(return_value=httpx.Response(200, json={}))
    orders = respx.post(f"{FUT}/fapi/v1/order").mock(
        side_effect=[
            httpx.Response(200, json={"avgPrice": "100", "executedQty": "0.5"}),
            httpx.Response(200, json={"avgPrice": "100", "executedQty": "0.5"}),
        ]
    )
    respx.post(f"{FUT}/fapi/v1/algoOrder").mock(
        return_value=httpx.Response(400, json={"code": -2021, "msg": "would trigger"})
    )
    broker = FuturesBroker(s, Client(FUT, "k", "s"), FakeMarket())
    with pytest.raises(BinanceError):
        broker.place(plan(entry_type="market"))
    close = params(orders.calls[1])
    assert close["side"] == "SELL" and close["reduceOnly"] == "true"


@respx.mock
def test_futures_protection_uses_close_position_on_mark_price(settings):
    s = settings.model_copy(update={"market": Market.FUTURES})
    respx.post(f"{FUT}/fapi/v1/marginType").mock(return_value=httpx.Response(200, json={}))
    respx.post(f"{FUT}/fapi/v1/leverage").mock(return_value=httpx.Response(200, json={}))
    respx.post(f"{FUT}/fapi/v1/order").mock(
        return_value=httpx.Response(200, json={"avgPrice": "100", "executedQty": "0.5"})
    )
    algo = respx.post(f"{FUT}/fapi/v1/algoOrder").mock(
        side_effect=[
            httpx.Response(200, json={"algoId": 11}),
            httpx.Response(200, json={"algoId": 12}),
        ]
    )
    broker = FuturesBroker(s, Client(FUT, "k", "s"), FakeMarket())
    placed = broker.place(plan(entry_type="market", side="short", stop=105.0, take_profit=88.0))
    stop = params(algo.calls[0])
    assert stop["type"] == "STOP_MARKET" and stop["side"] == "BUY"
    assert stop["closePosition"] == "true" and stop["workingType"] == "MARK_PRICE"
    assert placed.refs == {"stop": 11, "target": 12}
    assert json.dumps(placed.refs)
