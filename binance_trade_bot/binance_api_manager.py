import math
import time
import traceback
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, Optional

from binance.client import Client
from binance.exceptions import BinanceAPIException
from cachetools import TTLCache, cached

from .binance_stream_manager import BinanceCache, BinanceOrder, BinanceStreamManager, OrderGuard
from .config import Config
from .database import Database
from .logger import Logger
from .models import Coin


def float_as_decimal_str(num: float):
    return f"{num:0.08f}".rstrip("0").rstrip(".")  # remove trailing zeroes too


class AbstractOrderBalanceManager(ABC):
    @abstractmethod
    def get_currency_balance(self, currency_symbol: str, force=False):
        pass

    @abstractmethod
    def create_order(self, **params):
        pass

    def make_order(self, side: str, symbol: str, quantity: float, quote_quantity: float):
        params = {
            "symbol": symbol,
            "side": side,
            "quantity": float_as_decimal_str(quantity),
            "type": Client.ORDER_TYPE_MARKET,
        }
        if side == Client.SIDE_BUY:
            del params["quantity"]
            params["quoteOrderQty"] = float_as_decimal_str(quote_quantity)
        return self.create_order(**params)


class PaperOrderBalanceManager(AbstractOrderBalanceManager):
    def __init__(self, bridge_symbol: str, client: Client, cache: BinanceCache, initial_balances: Dict[str, float]):
        self.balances = initial_balances
        self.bridge = bridge_symbol
        self.client = client
        self.cache = cache
        self.fake_order_id = 0

    def get_currency_balance(self, currency_symbol: str, force=False):
        return self.balances.get(currency_symbol, 0.0)

    def create_order(self, **params):
        return self.client.create_test_order(**params)

    def make_order(self, side: str, symbol: str, quantity: float, quote_quantity: float):
        symbol_base = symbol[: -len(self.bridge)]
        if side == Client.SIDE_SELL:
            self.balances[self.bridge] = self.get_currency_balance(self.bridge) + quote_quantity * 0.999
            self.balances[symbol_base] = self.get_currency_balance(symbol_base) - quantity
        else:
            self.balances[self.bridge] = self.get_currency_balance(self.bridge) - quote_quantity
            self.balances[symbol_base] = self.get_currency_balance(symbol_base) + quantity * 0.999
        super().make_order(side, symbol, quantity, quote_quantity)

        self.fake_order_id += 1
        order = self.cache.orders[str(self.fake_order_id)] = BinanceOrder(
            defaultdict(
                lambda: "",
                order_id=str(self.fake_order_id),
                current_order_status="FILLED",
                cumulative_filled_quantity=str(quantity),
                cumulative_quote_asset_transacted_quantity=str(quote_quantity),
                order_price="0",
            )
        )
        return {"executedQty": "0", "status": "FILLED", "orderId": order.id}


class BinanceOrderBalanceManager(AbstractOrderBalanceManager):
    def __init__(self, logger: Logger, binance_client: Client, cache: BinanceCache):
        self.logger = logger
        self.binance_client = binance_client
        self.cache = cache

    def create_order(self, **params):
        return self.binance_client.create_order(**params)

    def get_currency_balance(self, currency_symbol: str, force=False):
        """
        Get balance of a specific coin
        """
        with self.cache.open_balances() as cache_balances:
            balance = cache_balances.get(currency_symbol, None)
            if force or balance is None:
                cache_balances.clear()
                cache_balances.update(
                    {
                        currency_balance["asset"]: float(currency_balance["free"])
                        for currency_balance in self.binance_client.get_account()["balances"]
                    }
                )
                self.logger.debug(f"Fetched all balances: {cache_balances}")
                if currency_symbol not in cache_balances:
                    cache_balances[currency_symbol] = 0.0
                    return 0.0
                return cache_balances.get(currency_symbol, 0.0)

            return balance


class BinanceAPIManager:
    def __init__(
        self,
        client: Client,
        cache: BinanceCache,
        config: Config,
        db: Database,
        logger: Logger,
        order_balance_manager: AbstractOrderBalanceManager,
    ):
        # initializing the client class calls `ping` API endpoint, verifying the connection
        self.binance_client = client
        self.db = db
        self.logger = logger
        self.config = config

        self.cache = cache
        self.order_balance_manager = order_balance_manager
        self.stream_manager: BinanceStreamManager = BinanceStreamManager(
            self.cache,
            self.config,
            self.logger,
        )
        self.setup_websockets()

    @staticmethod
    def create_manager(config: Config, db: Database, logger: Logger):
        cache = BinanceCache()
        client = Client(
            config.BINANCE_API_KEY,
            config.BINANCE_API_SECRET_KEY,
            tld=config.BINANCE_TLD,
        )
        return BinanceAPIManager(client, cache, config, db, logger, BinanceOrderBalanceManager(logger, client, cache))

    @staticmethod
    def create_manager_paper_trading(
        config: Config, db: Database, logger: Logger, initial_balances: Optional[Dict[str, float]] = None
    ):
        if initial_balances is None:
            initial_balances = {config.BRIDGE.symbol: 100.0}
        cache = BinanceCache()
        client = Client(
            config.BINANCE_API_KEY,
            config.BINANCE_API_SECRET_KEY,
            tld=config.BINANCE_TLD,
        )
        return BinanceAPIManager(
            client,
            cache,
            config,
            db,
            logger,
            PaperOrderBalanceManager(config.BRIDGE.symbol, client, cache, initial_balances),
        )

    def setup_websockets(self):
        self.stream_manager.start()

    @cached(cache=TTLCache(maxsize=1, ttl=43200))
    def get_trade_fees(self) -> Dict[str, float]:
        return {ticker["symbol"]: float(ticker["takerCommission"]) for ticker in self.binance_client.get_trade_fee()}

    @cached(cache=TTLCache(maxsize=1, ttl=60))
    def get_using_bnb_for_fees(self):
        return self.binance_client.get_bnb_burn_spot_margin()["spotBNBBurn"]

    def get_fee(self, origin_coin: Coin, target_coin: Coin, selling: bool):
        base_fee = self.get_trade_fees()[origin_coin + target_coin]
        if not self.get_using_bnb_for_fees():
            return base_fee

        # The discount is only applied if we have enough BNB to cover the fee
        amount_trading = (
            self._sell_quantity(origin_coin.symbol, target_coin.symbol)
            if selling
            else self._buy_quantity(origin_coin.symbol, target_coin.symbol)
        )

        fee_amount = amount_trading * base_fee * 0.75
        if origin_coin.symbol == "BNB":
            fee_amount_bnb = fee_amount
        else:
            origin_price = self.get_ticker_price(origin_coin + Coin("BNB"))
            if origin_price is None:
                return base_fee
            fee_amount_bnb = fee_amount * origin_price

        bnb_balance = self.get_currency_balance("BNB")

        if bnb_balance >= fee_amount_bnb:
            return base_fee * 0.75
        return base_fee

    def get_account(self):
        """
        Get account information
        """
        return self.binance_client.get_account()

    def get_market_sell_price(self, symbol: str, amount: float) -> (float, float):
        return self.stream_manager.get_market_sell_price(symbol, amount)

    def get_market_buy_price(self, symbol: str, quote_amount: float) -> (float, float):
        return self.stream_manager.get_market_buy_price(symbol, quote_amount)

    def get_market_sell_price_fill_quote(self, symbol: str, quote_amount: float) -> (float, float):
        return self.stream_manager.get_market_sell_price_fill_quote(symbol, quote_amount)

    def get_ticker_price(self, ticker_symbol: str):
        """
        Get ticker price of a specific coin
        """
        price = self.cache.ticker_values.get(ticker_symbol, None)
        if price is None and ticker_symbol not in self.cache.non_existent_tickers:
            self.cache.ticker_values = {
                ticker["symbol"]: float(ticker["price"]) for ticker in self.binance_client.get_symbol_ticker()
            }
            self.logger.debug(f"Fetched all ticker prices: {self.cache.ticker_values}")
            price = self.cache.ticker_values.get(ticker_symbol, None)
            if price is None:
                self.logger.info(f"Ticker does not exist: {ticker_symbol} - will not be fetched from now on")
                self.cache.non_existent_tickers.add(ticker_symbol)

        return price

    def get_currency_balance(self, currency_symbol: str, force=False) -> float:
        """
        Get balance of a specific coin
        """
        return self.order_balance_manager.get_currency_balance(currency_symbol, force)

    def retry(self, func, *args, **kwargs):
        time.sleep(1)
        attempts = 0
        while attempts < 20:
            try:
                return func(*args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                self.logger.warning(f"Failed to Buy/Sell. Trying Again (attempt {attempts}/20)")
                if attempts == 0:
                    self.logger.warning(traceback.format_exc())
                attempts += 1
        return None

    def get_symbol_filter(self, origin_symbol: str, target_symbol: str, filter_type: str):
        return next(
            _filter
            for _filter in self.binance_client.get_symbol_info(origin_symbol + target_symbol)["filters"]
            if _filter["filterType"] == filter_type
        )

    @cached(cache=TTLCache(maxsize=2000, ttl=43200))
    def get_alt_tick(self, origin_symbol: str, target_symbol: str):
        step_size = self.get_symbol_filter(origin_symbol, target_symbol, "LOT_SIZE")["stepSize"]
        if step_size.find("1") == 0:
            return 1 - step_size.find(".")
        return step_size.find("1") - 1

    @cached(cache=TTLCache(maxsize=2000, ttl=43200))
    def get_min_notional(self, origin_symbol: str, target_symbol: str):
        return float(self.get_symbol_filter(origin_symbol, target_symbol, "MIN_NOTIONAL")["minNotional"])

    def _wait_for_order(self, order_id) -> Optional[BinanceOrder]:  # pylint: disable=unsubscriptable-object
        while True:
            order_status: BinanceOrder = self.cache.orders.get(order_id, None)
            if order_status is not None:
                break
            self.logger.debug(f"Waiting for order {order_id} to be created")
            time.sleep(1)

        self.logger.debug(f"Order created: {order_status}")

        while order_status.status != "FILLED":
            order_status = self.cache.orders.get(order_id, None)
            if order_status.status != "FILLED":
                self.logger.debug(f"Waiting for order {order_id} to be filled")
                time.sleep(1)

        self.logger.debug(f"Order filled: {order_status}")
        return order_status

    def wait_for_order(
        self, order_id, order_guard: OrderGuard
    ) -> Optional[BinanceOrder]:  # pylint: disable=unsubscriptable-object
        with order_guard:
            return self._wait_for_order(order_id)

    def buy_alt(self, origin_coin: Coin, target_coin: Coin, buy_price: float) -> BinanceOrder:
        return self.retry(self._buy_alt, origin_coin, target_coin, buy_price)

    def _buy_quantity(
        self, origin_symbol: str, target_symbol: str, target_balance: float = None, from_coin_price: float = None
    ):
        target_balance = target_balance or self.get_currency_balance(target_symbol)
        from_coin_price = from_coin_price or self.get_ticker_price(origin_symbol + target_symbol)

        origin_tick = self.get_alt_tick(origin_symbol, target_symbol)
        return math.floor(target_balance * 10 ** origin_tick / from_coin_price) / float(10 ** origin_tick)

    def _buy_alt(self, origin_coin: Coin, target_coin: Coin, buy_price: float):  # pylint: disable=too-many-locals
        """
        Buy altcoin
        """
        origin_symbol = origin_coin.symbol
        target_symbol = target_coin.symbol

        with self.cache.open_balances() as balances:
            balances.clear()

        origin_balance = self.get_currency_balance(origin_symbol)
        target_balance = self.get_currency_balance(target_symbol)
        from_coin_price = buy_price

        trade_log = self.db.start_trade_log(origin_coin, target_coin, False)

        order_quantity = self._buy_quantity(origin_symbol, target_symbol, target_balance, from_coin_price)
        self.logger.info(f"BUY QTY {order_quantity} of <{origin_symbol}>")

        # Try to buy until successful
        order = None
        order_guard = self.stream_manager.acquire_order_guard()
        while order is None:
            try:
                order = self.order_balance_manager.make_order(
                    side=Client.SIDE_BUY,
                    symbol=origin_symbol + target_symbol,
                    quantity=order_quantity,
                    quote_quantity=target_balance,
                )
                self.logger.info(order)
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(1)
            except Exception as e:  # pylint: disable=broad-except
                self.logger.warning(f"Unexpected Error: {e}")

        executed_qty = float(order.get("executedQty", 0))
        if executed_qty > 0 and order["status"] == "FILLED":
            order_quantity = executed_qty  # Market buys provide QTY of actually bought asset

        trade_log.set_ordered(origin_balance, target_balance, order_quantity)

        order_guard.set_order(origin_symbol, target_symbol, int(order["orderId"]))
        order = self.wait_for_order(order["orderId"], order_guard)

        if order is None:
            return None

        self.logger.info(f"Bought {origin_symbol}")

        trade_log.set_complete(order.cumulative_quote_qty)

        return order

    def sell_alt(self, origin_coin: Coin, target_coin: Coin, sell_price: float) -> BinanceOrder:
        return self.retry(self._sell_alt, origin_coin, target_coin, sell_price)

    def _sell_quantity(self, origin_symbol: str, target_symbol: str, origin_balance: float = None):
        origin_balance = origin_balance or self.get_currency_balance(origin_symbol)

        origin_tick = self.get_alt_tick(origin_symbol, target_symbol)
        return math.floor(origin_balance * 10 ** origin_tick) / float(10 ** origin_tick)

    def _sell_alt(self, origin_coin: Coin, target_coin: Coin, sell_price: float):  # pylint: disable=too-many-locals
        """
        Sell altcoin
        """
        origin_symbol = origin_coin.symbol
        target_symbol = target_coin.symbol

        # get fresh balances
        with self.cache.open_balances() as balances:
            balances.clear()

        origin_balance = self.get_currency_balance(origin_symbol)
        target_balance = self.get_currency_balance(target_symbol)
        from_coin_price = sell_price

        trade_log = self.db.start_trade_log(origin_coin, target_coin, True)

        order_quantity = self._sell_quantity(origin_symbol, target_symbol, origin_balance)
        self.logger.info(f"Selling {order_quantity} of {origin_symbol}")

        self.logger.info(f"Balance is {origin_balance}")
        order = None
        order_guard = self.stream_manager.acquire_order_guard()
        while order is None:
            try:
                order = self.order_balance_manager.make_order(
                    side=Client.SIDE_SELL,
                    symbol=origin_symbol + target_symbol,
                    quantity=order_quantity,
                    quote_quantity=from_coin_price * order_quantity,
                )
                self.logger.info(order)
            except BinanceAPIException as e:
                self.logger.info(e)
                time.sleep(1)
            except Exception as e:  # pylint: disable=broad-except
                self.logger.warning(f"Unexpected Error: {e}")

        self.logger.info("order")
        self.logger.info(order)

        trade_log.set_ordered(origin_balance, target_balance, order_quantity)

        order_guard.set_order(origin_symbol, target_symbol, int(order["orderId"]))
        order = self.wait_for_order(order["orderId"], order_guard)

        if order is None:
            return None

        new_balance = self.get_currency_balance(origin_symbol)
        while new_balance >= origin_balance:
            new_balance = self.get_currency_balance(origin_symbol, True)

        self.logger.info(f"Sold {origin_symbol}")

        trade_log.set_complete(order.cumulative_quote_qty)

        return order
