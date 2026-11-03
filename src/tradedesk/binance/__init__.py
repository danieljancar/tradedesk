from tradedesk.binance.client import BinanceError, Client, base_url
from tradedesk.binance.market import MarketData, SymbolRules
from tradedesk.config import Market, Mode, Settings, api_keys


def market_data(settings: Settings, venue: bool = False) -> MarketData:
    """Live public data by default; venue=True reads from the exchange the broker trades on."""
    source = settings if venue else settings.model_copy(update={"mode": Mode.LIVE})
    spot = Client(base_url(source, Market.SPOT))
    futures = Client(base_url(source, Market.FUTURES))
    return MarketData(spot, futures, settings.market)


def trading_client(settings: Settings) -> Client:
    key, secret = api_keys()
    return Client(base_url(settings, settings.market), key, secret)


__all__ = ["BinanceError", "Client", "MarketData", "SymbolRules", "market_data", "trading_client"]
