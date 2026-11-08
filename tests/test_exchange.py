import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from tradedesk.binance.client import BinanceError, Client
from tradedesk.broker.base import Unprotected
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
            id=5,
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
    respx.get(f"{FUT}/fapi/v3/positionRisk").mock(
        return_value=httpx.Response(200, json=[{"positionAmt": "0.5", "entryPrice": "100"}])
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


@respx.mock
def test_spot_market_buy_recovered_by_client_id_after_timeout(settings):
    respx.post(f"{SPOT}/api/v3/order").mock(side_effect=httpx.ReadTimeout("slow"))
    lookup = respx.get(f"{SPOT}/api/v3/order").mock(
        return_value=httpx.Response(200, json={"executedQty": "0.5", "cummulativeQuoteQty": "50"})
    )
    respx.post(f"{SPOT}/api/v3/orderList/oco").mock(
        return_value=httpx.Response(
            200,
            json={
                "orderListId": 9,
                "orderReports": [
                    {"type": "LIMIT_MAKER", "orderId": 2},
                    {"type": "STOP_LOSS", "orderId": 3},
                ],
            },
        )
    )
    broker = SpotBroker(settings, Client(SPOT, "k", "s"), FakeMarket())
    placed = broker.place(plan(entry_type="market"))
    assert params(lookup.calls[0])["origClientOrderId"] == "desk-5"
    assert placed.open and placed.refs["stop"] == 3


@respx.mock
def test_spot_expired_entry_keeps_partial_fill_protected(settings):
    respx.delete(f"{SPOT}/api/v3/orderList").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{SPOT}/api/v3/order").mock(
        return_value=httpx.Response(
            200, json={"status": "CANCELED", "executedQty": "0.3", "cummulativeQuoteQty": "29.7"}
        )
    )
    oco = respx.post(f"{SPOT}/api/v3/orderList/oco").mock(
        return_value=httpx.Response(
            200,
            json={
                "orderListId": 9,
                "orderReports": [
                    {"type": "LIMIT_MAKER", "orderId": 2},
                    {"type": "STOP_LOSS", "orderId": 3},
                ],
            },
        )
    )
    broker = SpotBroker(settings, Client(SPOT, "k", "s"), FakeMarket())
    fill = broker.cancel(plan(exchange=json.dumps({"list": 7, "entry": 1})))
    assert fill and fill.qty < 0.3
    assert params(oco.calls[0])["belowStopPrice"] == "94"


@respx.mock
def test_spot_flags_position_without_stop(settings):
    respx.get(f"{SPOT}/api/v3/order").mock(
        return_value=httpx.Response(200, json={"status": "CANCELED", "executedQty": "0"})
    )
    broker = SpotBroker(settings, Client(SPOT, "k", "s"), FakeMarket())
    position = {
        "id": 1,
        "symbol": "BTCUSDT",
        "entry_price": 100,
        "qty": 0.5,
        "exchange": json.dumps({"list": 7, "stop": 3, "target": 2}),
    }
    with pytest.raises(Unprotected):
        broker.exit_status(position)


@respx.mock
def test_futures_cancels_stop_when_target_fails(settings):
    s = settings.model_copy(update={"market": Market.FUTURES})
    respx.post(f"{FUT}/fapi/v1/marginType").mock(return_value=httpx.Response(200, json={}))
    respx.post(f"{FUT}/fapi/v1/leverage").mock(return_value=httpx.Response(200, json={}))
    respx.post(f"{FUT}/fapi/v1/order").mock(
        return_value=httpx.Response(200, json={"avgPrice": "100", "executedQty": "0.5"})
    )
    respx.post(f"{FUT}/fapi/v1/algoOrder").mock(
        side_effect=[
            httpx.Response(200, json={"algoId": 11}),
            httpx.Response(400, json={"code": -2021, "msg": "would trigger"}),
        ]
    )
    cancel = respx.delete(f"{FUT}/fapi/v1/algoOrder").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get(f"{FUT}/fapi/v3/positionRisk").mock(
        return_value=httpx.Response(200, json=[{"positionAmt": "0.5", "entryPrice": "100"}])
    )
    broker = FuturesBroker(s, Client(FUT, "k", "s"), FakeMarket())
    with pytest.raises(BinanceError):
        broker.place(plan(entry_type="market"))
    assert params(cancel.calls[0])["algoId"] == "11"


@respx.mock
def test_futures_trades_cross_in_multi_assets_mode(settings):
    s = settings.model_copy(update={"market": Market.FUTURES})
    respx.post(f"{FUT}/fapi/v1/marginType").mock(
        return_value=httpx.Response(400, json={"code": -4168, "msg": "Multi-Assets mode"})
    )
    leverage = respx.post(f"{FUT}/fapi/v1/leverage").mock(return_value=httpx.Response(200, json={}))
    broker = FuturesBroker(s, Client(FUT, "k", "s"), FakeMarket())
    broker._prepare("SOLUSDT", 3)
    assert leverage.called


@respx.mock
def test_futures_protects_first_when_the_fill_reads_late(settings, monkeypatch):
    monkeypatch.setattr("tradedesk.broker.futures.time.sleep", lambda _: None)
    s = settings.model_copy(update={"market": Market.FUTURES})
    respx.post(f"{FUT}/fapi/v1/marginType").mock(return_value=httpx.Response(200, json={}))
    respx.post(f"{FUT}/fapi/v1/leverage").mock(return_value=httpx.Response(200, json={}))
    # the order answer has no avgPrice and no fill yet, like the live ONE order
    respx.post(f"{FUT}/fapi/v1/order").mock(
        return_value=httpx.Response(200, json={"orderId": 1, "status": "NEW"})
    )
    respx.get(f"{FUT}/fapi/v1/order").mock(
        return_value=httpx.Response(
            200, json={"status": "FILLED", "executedQty": "8841", "cumQuote": "18.0"}
        )
    )
    algo = respx.post(f"{FUT}/fapi/v1/algoOrder").mock(
        side_effect=[
            httpx.Response(200, json={"algoId": 11}),
            httpx.Response(200, json={"algoId": 12}),
        ]
    )
    broker = FuturesBroker(s, Client(FUT, "k", "s"), FakeMarket())
    placed = broker.place(plan(entry_type="market"))
    assert algo.call_count == 2
    assert placed.qty == 8841 and abs(placed.fill_price - 18.0 / 8841) < 1e-12


def _futures(settings):
    s = settings.model_copy(update={"market": Market.FUTURES})
    respx.post(f"{FUT}/fapi/v1/marginType").mock(return_value=httpx.Response(200, json={}))
    respx.post(f"{FUT}/fapi/v1/leverage").mock(return_value=httpx.Response(200, json={}))
    return FuturesBroker(s, Client(FUT, "k", "s"), FakeMarket())


@respx.mock
def test_futures_limit_entry_rests_on_binance_with_stop_and_target(settings):
    broker = _futures(settings)
    order = respx.post(f"{FUT}/fapi/v1/order").mock(
        return_value=httpx.Response(200, json={"orderId": 7, "status": "NEW"})
    )
    respx.post(f"{FUT}/fapi/v1/algoOrder").mock(
        side_effect=[
            httpx.Response(200, json={"algoId": 11}),
            httpx.Response(200, json={"algoId": 12}),
        ]
    )
    placed = broker.place(plan(side="short", entry=105.0, stop=110.0, take_profit=90.0))
    sent = params(order.calls[0])
    assert sent["type"] == "LIMIT" and sent["side"] == "SELL" and float(sent["price"]) == 105.0
    assert placed.refs == {"entry": "desk-5", "stop": 11, "target": 12} and not placed.open


@respx.mock
def test_futures_limit_entry_waits_in_the_desk_when_binance_refuses_a_leg(settings):
    broker = _futures(settings)
    respx.post(f"{FUT}/fapi/v1/order").mock(return_value=httpx.Response(200, json={"orderId": 7}))
    respx.post(f"{FUT}/fapi/v1/algoOrder").mock(
        return_value=httpx.Response(400, json={"code": -4509, "msg": "no position"})
    )
    cancel = respx.delete(f"{FUT}/fapi/v1/order").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{FUT}/fapi/v1/order").mock(
        return_value=httpx.Response(200, json={"status": "CANCELED", "executedQty": "0"})
    )
    placed = broker.place(plan())
    assert placed.refs == {"waiting": True} and cancel.called


@respx.mock
def test_futures_resting_entry_fill_keeps_its_legs(settings):
    broker = _futures(settings)
    respx.get(f"{FUT}/fapi/v1/order").mock(
        return_value=httpx.Response(
            200, json={"status": "FILLED", "executedQty": "0.5", "avgPrice": "99.0"}
        )
    )
    p = plan(exchange=json.dumps({"entry": "desk-5", "stop": 11, "target": 12}))
    fill = broker.entry_status(p)
    assert fill.qty == 0.5 and fill.price == 99.0 and fill.refs == {"stop": 11, "target": 12}


@respx.mock
def test_futures_cancel_removes_entry_and_legs(settings):
    broker = _futures(settings)
    respx.delete(f"{FUT}/fapi/v1/order").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{FUT}/fapi/v1/order").mock(
        return_value=httpx.Response(200, json={"status": "CANCELED", "executedQty": "0"})
    )
    algos = respx.delete(f"{FUT}/fapi/v1/algoOrder").mock(return_value=httpx.Response(200, json={}))
    p = plan(exchange=json.dumps({"entry": "desk-5", "stop": 11, "target": 12}))
    assert broker.cancel(p) is None and algos.call_count == 2


@respx.mock
def test_futures_adopt_keeps_existing_stop_and_places_the_target(settings):
    broker = _futures(settings)
    respx.get(f"{FUT}/fapi/v3/positionRisk").mock(
        return_value=httpx.Response(200, json=[{"positionAmt": "8841", "entryPrice": "0.0020046"}])
    )
    respx.get(f"{FUT}/fapi/v1/openAlgoOrders").mock(
        return_value=httpx.Response(
            200, json=[{"algoId": 31, "orderType": "STOP_MARKET", "side": "SELL"}]
        )
    )
    algo = respx.post(f"{FUT}/fapi/v1/algoOrder").mock(
        return_value=httpx.Response(200, json={"algoId": 32})
    )
    fill = broker.adopt("ONEUSDT", 0.00189, 0.002476)
    assert fill.qty == 8841 and fill.refs == {"stop": 31, "target": 32}
    assert params(algo.calls[0])["type"] == "TAKE_PROFIT_MARKET"
