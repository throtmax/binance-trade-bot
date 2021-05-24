import asyncio
import threading
import uuid
from contextlib import asynccontextmanager, contextmanager, suppress
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

import binance.client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from unicorn_binance_websocket_api import BinanceWebSocketApiManager

from .config import Config
from .logger import Logger


class ThreadSafeAsyncLock:
    def __init__(self):
        self._init_lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def attach_loop(self):
        with self._init_lock:
            self._async_lock = asyncio.Lock()
            self.loop = asyncio.get_running_loop()

    def acquire(self):
        self.__enter__()

    def release(self):
        self.__exit__(None, None, None)

    def __enter__(self):
        self._init_lock.__enter__()
        if self._async_lock is not None:
            asyncio.run_coroutine_threadsafe(self._async_lock.__aenter__(), self.loop).result()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._async_lock is not None:
            asyncio.run_coroutine_threadsafe(self._async_lock.__aexit__(exc_type, exc_val, exc_tb), self.loop).result()
        self._init_lock.__exit__(exc_type, exc_val, exc_tb)

    async def __aenter__(self):
        await self._async_lock.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._async_lock.__aexit__(exc_type, exc_val, exc_tb)


class BinanceOrder:  # pylint: disable=too-few-public-methods
    def __init__(self, report):
        self.event = report
        self.symbol = report["symbol"]
        self.side = report["side"]
        self.order_type = report["order_type"]
        self.id = report["order_id"]
        self.cumulative_quote_qty = float(report["cumulative_quote_asset_transacted_quantity"])
        self.status = report["current_order_status"]
        self.price = float(report["order_price"])
        self.time = report["transaction_time"]
        self.cumulative_filled_quantity = float(report["cumulative_filled_quantity"])

    def __repr__(self):
        return f"<BinanceOrder {self.event}>"


class BinanceCache:  # pylint: disable=too-few-public-methods
    def __init__(self):
        self.ticker_values: Dict[str, float] = {}
        self._balances: Dict[str, float] = {}
        self._balances_mutex: ThreadSafeAsyncLock = ThreadSafeAsyncLock()
        self.non_existent_tickers: Set[str] = set()
        self.orders: Dict[str, BinanceOrder] = {}

    def attach_loop(self):
        self._balances_mutex.attach_loop()

    @contextmanager
    def open_balances(self):
        with self._balances_mutex:
            yield self._balances

    @asynccontextmanager
    async def open_balances_async(self):
        async with self._balances_mutex:
            yield self._balances


class AsyncListenerContext:
    def __init__(
        self,
        buffer_names: List[str],
        cache: BinanceCache,
        logger: Logger,
        client: binance.AsyncClient,
        pending_orders: Set[Tuple[str, int]],
        pending_orders_mutex: ThreadSafeAsyncLock,
    ):
        self.queues: Dict[str, asyncio.Queue] = {name: asyncio.Queue() for name in buffer_names}
        self.loop = asyncio.get_running_loop()
        self.buffer_names = buffer_names
        self.cache = cache
        self.logger = logger
        self.resolver = None
        self.stopped = False
        self.client = client
        self.pending_orders = pending_orders
        self.pending_orders_mutex = pending_orders_mutex

    def attach_stream_uuid_resolver(self, resolver: Callable[[uuid.UUID], str]):
        self.resolver = resolver

    def resolve_stream_id(self, stream_id: uuid.UUID) -> str:
        return self.resolver(stream_id)

    def add_stream_data(self, stream_data, stream_buffer_name: Union[str, bool] = False):
        if self.stopped:
            return
        asyncio.run_coroutine_threadsafe(self.queues[stream_buffer_name].put(stream_data), self.loop)

    def add_signal_data(self, signal_data: Dict):
        if self.stopped:
            return
        stream_id = signal_data["stream_id"]
        buffer_name = self.resolver(stream_id)
        asyncio.run_coroutine_threadsafe(self.queues[buffer_name].put(signal_data), self.loop)

    async def shutdown(self):
        self.logger.debug("prepare graceful loop shutdown")
        self.stopped = True
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.logger.debug("loop shutdown")
        self.resolver = None  # to prevent circular ref
        self.loop.stop()


class AppendProxy:
    def __init__(self, append_proxy_func):
        self.append_proxy_func = append_proxy_func

    def append(self, obj):
        self.append_proxy_func(obj)

    def pop(self):  # pylint: disable=no-self-use
        return None


class AsyncListenedBWAM(BinanceWebSocketApiManager):
    def __init__(self, async_listener_context: AsyncListenerContext, *args, **kwargs):
        self.async_listener_context = async_listener_context
        super().__init__(*args, process_stream_data=self.async_listener_context.add_stream_data, **kwargs)
        self.stream_signal_buffer = AppendProxy(self.async_listener_context.add_signal_data)
        self.async_listener_context.attach_stream_uuid_resolver(self.stream_uuid_resolver)

    def stream_uuid_resolver(self, stream_id: uuid.UUID):
        return self.stream_list[stream_id]["stream_buffer_name"]

    def stop_manager_with_all_streams(self):
        super().stop_manager_with_all_streams()
        asyncio.run_coroutine_threadsafe(self.async_listener_context.shutdown(), self.async_listener_context.loop)


BUFFER_NAME_MINITICKERS = "mt"
BUFFER_NAME_USERDATA = "ud"
BUFFER_NAME_DEPTH = "de"


class AsyncListener:
    def __init__(self, buffer_name: str, async_context: AsyncListenerContext):
        self.buffer_name = buffer_name
        self.async_context = async_context

    @staticmethod
    def is_stream_signal(obj):
        return "type" in obj

    async def handle_signal(self, signal):  # pylint: disable=unused-argument
        ...

    async def handle_data(self, data):  # pylint: disable=unused-argument
        ...

    async def run_loop(self):
        while True:
            data = await self.async_context.queues[self.buffer_name].get()

            if AsyncListener.is_stream_signal(data):
                await self.handle_signal(data)
            else:
                await self.handle_data(data)


class TickerListener(AsyncListener):
    def __init__(self, async_context: AsyncListenerContext):
        super().__init__(BUFFER_NAME_MINITICKERS, async_context)

    async def handle_data(self, data):
        if "event_type" in data:
            if data["event_type"] == "24hrMiniTicker":
                for event in data["data"]:
                    self.async_context.cache.ticker_values[event["symbol"]] = float(event["close_price"])
            else:
                self.async_context.logger.error(f"Unknown event type found: {data}")


class UserDataListener(AsyncListener):
    def __init__(self, async_context: AsyncListenerContext):
        super().__init__(BUFFER_NAME_USERDATA, async_context)

    async def handle_data(self, data):
        if "event_type" in data:
            event_type = data["event_type"]
            if event_type == "executionReport":
                self.async_context.logger.debug(f"execution report: {data}")
                order = BinanceOrder(data)
                self.async_context.cache.orders[order.id] = order
            elif event_type == "balanceUpdate":
                self.async_context.logger.debug(f"Balance update: {data}")
                async with self.async_context.cache.open_balances_async() as balances:
                    asset = data["asset"]
                    if asset in balances:
                        del balances[data["asset"]]
            elif event_type in ("outboundAccountPosition", "outboundAccountInfo"):
                self.async_context.logger.debug(f"{event_type}: {data}")
                async with self.async_context.cache.open_balances_async() as balances:
                    for bal in data["balances"]:
                        balances[bal["asset"]] = float(bal["free"])

    async def _fetch_pending_orders(self):
        pending_orders: Set[Tuple[str, int]]
        async with self.async_context.pending_orders_mutex:
            pending_orders = self.async_context.pending_orders.copy()
        for (symbol, order_id) in pending_orders:
            order = None
            while True:
                try:
                    order = await self.async_context.client.get_order(symbol=symbol, orderId=order_id)
                except (BinanceRequestException, BinanceAPIException) as e:
                    self.async_context.logger.error(f"Got exception during fetching pending order: {e}")
                if order is not None:
                    break
                await asyncio.sleep(1)
            fake_report = {
                "symbol": order["symbol"],
                "side": order["side"],
                "order_type": order["type"],
                "order_id": order["orderId"],
                "cumulative_quote_asset_transacted_quantity": float(order["cummulativeQuoteQty"]),
                "current_order_status": order["status"],
                "order_price": float(order["price"]),
                "transaction_time": order["time"],
            }
            self.async_context.logger.info(
                f"Pending order {order_id} for symbol {symbol} fetched:\n{fake_report}", False
            )
            self.async_context.cache.orders[fake_report["order_id"]] = BinanceOrder(fake_report)

    async def _invalidate_balances(self):
        async with self.async_context.cache.open_balances_async() as balances:
            balances.clear()

    async def handle_signal(self, signal):
        signal_type = signal["type"]
        if signal_type == "CONNECT":
            self.async_context.logger.debug("Connect for userdata arrived", False)
            await self._fetch_pending_orders()
            await self._invalidate_balances()


class OrderGuard:
    def __init__(self, pending_orders: Set[Tuple[str, int]], mutex: ThreadSafeAsyncLock):
        self.pending_orders = pending_orders
        self.mutex = mutex
        # lock immediately because OrderGuard
        # should be entered and put tag that shouldn't be missed
        self.mutex.acquire()
        self.tag = None

    def set_order(self, origin_symbol: str, target_symbol: str, order_id: int):
        self.tag = (origin_symbol + target_symbol, order_id)

    def __enter__(self):
        try:
            if self.tag is None:
                raise Exception("OrderGuard wasn't properly set")
            self.pending_orders.add(self.tag)
        finally:
            self.mutex.release()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pending_orders.remove(self.tag)


class BinanceStreamManager(threading.Thread):
    def __init__(self, cache: BinanceCache, config: Config, logger: Logger):
        super().__init__()
        self.cache = cache
        self.config = config
        self.logger = logger
        self.bwam: Optional[AsyncListenedBWAM] = None
        self.async_context: Optional[AsyncListenerContext] = None

        self.pending_orders: Set[Tuple[str, int]] = set()
        self.pending_orders_mutex: ThreadSafeAsyncLock = ThreadSafeAsyncLock()

    async def arun(self):
        self.cache.attach_loop()
        self.pending_orders_mutex.attach_loop()
        client = await binance.AsyncClient.create(
            self.config.BINANCE_API_KEY, self.config.BINANCE_API_SECRET_KEY, tld=self.config.BINANCE_TLD
        )
        self.async_context = AsyncListenerContext(
            [BUFFER_NAME_MINITICKERS, BUFFER_NAME_USERDATA],
            self.cache,
            self.logger,
            client,
            self.pending_orders,
            self.pending_orders_mutex,
        )
        self.bwam = AsyncListenedBWAM(
            self.async_context,
            output_default="UnicornFy",
            enable_stream_signal_buffer=True,
            exchange=f"binance.{self.config.BINANCE_TLD}",
        )
        quotes = set(map(str.lower, [self.config.BRIDGE.symbol, "usdt", "btc", "bnb"]))
        markets = [coin.lower() + quote for quote in quotes for coin in self.config.SUPPORTED_COIN_LIST]
        self.bwam.create_stream(["miniTicker"], markets, stream_buffer_name=BUFFER_NAME_MINITICKERS)
        self.bwam.create_stream(
            ["arr"],
            ["!userData"],
            api_key=self.config.BINANCE_API_KEY,
            api_secret=self.config.BINANCE_API_SECRET_KEY,
            stream_buffer_name=BUFFER_NAME_USERDATA,
        )
        await asyncio.gather(
            *[TickerListener(self.async_context).run_loop(), UserDataListener(self.async_context).run_loop()]
        )

    def run(self) -> None:
        with suppress(asyncio.CancelledError):
            asyncio.run(self.arun())

    def acquire_order_guard(self):
        return OrderGuard(self.pending_orders, self.pending_orders_mutex)

    def close(self):
        self.bwam.stop_manager_with_all_streams()
