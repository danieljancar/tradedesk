from tradedesk.binance import market_data, trading_client
from tradedesk.broker.base import Broker, Exit, Fill, Placed
from tradedesk.broker.futures import FuturesBroker
from tradedesk.broker.paper import PaperBroker
from tradedesk.broker.spot import SpotBroker
from tradedesk.config import Market, Mode, Settings
from tradedesk.db import Database


def make_broker(settings: Settings, db: Database) -> Broker:
    md = market_data(settings, venue=True)
    if settings.mode is Mode.PAPER:
        return PaperBroker(settings, md, db)
    client = trading_client(settings)
    if settings.market is Market.FUTURES:
        return FuturesBroker(settings, client, md)
    return SpotBroker(settings, client, md, db)


__all__ = ["Broker", "Exit", "Fill", "Placed", "make_broker"]
