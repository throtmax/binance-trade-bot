import pytest

import os, datetime
from typing import Dict, List

from binance.client import Client
from sqlitedict import SqliteDict

from binance_trade_bot.backtest import backtest, MockDatabase, MockBinanceManager
from binance_trade_bot.binance_api_manager import BinanceAPIManager, BinanceOrderBalanceManager
from binance_trade_bot.binance_stream_manager import BinanceCache, BinanceOrder
from binance_trade_bot.config import Config
from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.models import Pair, ScoutHistory
from binance_trade_bot.strategies import get_strategy



from .common import infra
import runpy as rr


@pytest.fixture(scope='function')
def DoUserConfig():
    '''
    CURRENT_COIN_SYMBOL:
    SUPPORTED_COIN_LIST: "XLM TRX ICX EOS IOTA ONT QTUM ETC ADA XMR DASH NEO ATOM DOGE VET BAT OMG BTT"
    BRIDGE_SYMBOL: USDT
    API_KEY: vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A
    API_SECRET_KEY: NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j
    SCOUT_MULTIPLIER: 5
    SCOUT_SLEEP_TIME: 1
    TLD: com
    STRATEGY: default
    BUY_TIMEOUT: 0
    SELL_TIMEOUT: 0
    BUY_ORDER_TYPE: limit
    SELL_ORDER_TYPE: market
    '''

    # os.environ['CURRENT_COIN'] = 'ETH'
    os.environ['CURRENT_COIN_SYMBOL'] = 'ETH'

    os.environ['API_KEY'] = 'vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A'
    os.environ['API_SECRET_KEY'] = 'NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j'
    # os.environ['CURRENT_COIN_SYMBOL'] = 'BTT'
    os.environ['SUPPORTED_COIN_LIST'] = "XLM TRX ICX EOS IOTA ONT QTUM ETC ADA XMR DASH NEO ATOM DOGE VET BAT OMG BTT"
    os.environ['BRIDGE_SYMBOL'] = "USDT"
    os.environ['SCOUT_MULTIPLIER'] = "5"
    os.environ['SCOUT_SLEEP_TIME'] = "1"
    os.environ['TLD'] = 'com'
    os.environ['STRATEGY'] = 'default'
    os.environ['BUY_TIMEOUT'] = "0"
    os.environ['SELL_TIMEOUT'] = "0"
    os.environ['BUY_ORDER_TYPE'] = 'limit'
    os.environ['SELL_ORDER_TYPE'] = 'market'

    yield


@pytest.mark.timeout(60)
@pytest.mark.skip(reason='Long working time')
def test_backtest_main_module_on_run(capsys, infra, DoUserConfig):
    with pytest.raises(KeyError) as rraise:
        # rr.run_module('../backtest.py',run_name='__main__')
        rr.run_path('backtest.py', run_name='__main__')

    assert True


#####@pytest.mark.skip(reason="for debug time")
def test_backtest1_on_run(infra, DoUserConfig):
    backtest(datetime.datetime(2021, 6, 1), datetime.datetime.now())
    assert True


@pytest.mark.timeout(600)
@pytest.mark.parametrize("date_start", [datetime.datetime(2021, 6, 1), ])
@pytest.mark.parametrize("date_end", [datetime.datetime(2021, 6, 5), ])
@pytest.mark.parametrize("interval", [10, 5, 20, 30])
def test_backtest2_on_run(infra, DoUserConfig, date_start, date_end, interval):
    history = []
    for manager in backtest(date_start, date_end, interval=interval):
        btc_value = manager.collate_coins("BTC")
        bridge_value = manager.collate_coins(manager.config.BRIDGE.symbol)
        history.append((btc_value, bridge_value))
        btc_diff = round((btc_value - history[0][0]) / history[0][0] * 100, 3)
        bridge_diff = round((bridge_value - history[0][1]) / history[0][1] * 100, 3)

        print(datetime.datetime.now(), "-" * 40)
        print(datetime.datetime.now(), "TIME:", manager.datetime)
        print(datetime.datetime.now(), "BALANCES:", manager.balances)
        print(datetime.datetime.now(), "BTC VALUE:", btc_value, f"({btc_diff}%)")
        print(datetime.datetime.now(), f"{manager.config.BRIDGE.symbol} VALUE:", bridge_value, f"({bridge_diff}%)")

    assert True

@pytest.fixture()
def mmbm():

    logger: Logger = Logger(logging_service="guliguli")
    config: Config = Config()
    sqlite_cache = SqliteDict("data/testtest_cache.db")

    db = MockDatabase(logger, config)
    db.create_database()
    db.set_coins(config.SUPPORTED_COIN_LIST)
    #print(config.SUPPORTED_COIN_LIST)

    start_date: datetime = datetime.datetime(2021, 6, 1)
    start_balances: Dict[str, float] = dict()
    start_balances['XLM']  = 100
    start_balances['DOGE'] = 101
    start_balances['BTT']  = 102
    start_balances['BAD']  = 103
    start_balances['USDT']  = 1000

    manager = MockBinanceManager(
        Client(config.BINANCE_API_KEY, config.BINANCE_API_SECRET_KEY, tld=config.BINANCE_TLD),
        sqlite_cache,
        BinanceCache(),
        config,
        db,
        logger,
        start_date,
        start_balances,
    )

    yield db, manager

    #manager.close()
    #db.close()
    sqlite_cache.close()

class TestMockBinanceManager:

    # TODO: Relook later
    @pytest.mark.skip
    def test_set_reinit_trader_callback(self):
        assert False

    @pytest.mark.parametrize("coins_list", [pytest.param([], marks=pytest.mark.xfail), ['XLM', 'DOGE'], ['BUGAGA', ]])
    def test_set_coins(self, DoUserConfig, mmbm, coins_list):

        db, manager = mmbm

        manager.set_coins(coins_list)
        assert True

    def test_setup_websockets(self, DoUserConfig, mmbm):
        db, manager = mmbm
        manager.setup_websockets()
        assert True

    @pytest.mark.parametrize("interval", [pytest.param(-10, marks=pytest.mark.xfail),
                                          pytest.param(0, marks=pytest.mark.xfail),
                                          10, 20, 1440-1, 1440, 1440+1, 100*1440])
    def test_increment(self, DoUserConfig, mmbm, interval):
        db, manager  = mmbm
        old_datetime = manager.datetime
        manager.increment(interval=interval)
        print('\n', interval, old_datetime, manager.datetime)
        assert manager.datetime == datetime.timedelta(minutes=interval)+old_datetime

    def test_get_fee(self, DoUserConfig, mmbm):
        db, manager = mmbm
        assert manager.get_fee('GOT', 'BAI', False) == 0.001
        assert manager.get_fee('GOT', 'BAI', True) == 0.001

    # TODO: Not verify across historical_klines request?
    def test_get_ticker_price(self,DoUserConfig, mmbm):
        db, manager = mmbm
        val = manager.get_ticker_price('XLMUSDT')
        #print(val, manager.datetime)
        assert val

    def test_get_currency_balance(self, DoUserConfig, mmbm):
        db, manager = mmbm
        assert manager.get_currency_balance('GOT') == 0.0
        assert manager.get_currency_balance('XLM') == 100.0
        assert manager.get_currency_balance('DOGE') == 101.0
        assert manager.get_currency_balance('BTT') == 102.0
        assert manager.get_currency_balance('BAD') == 103.0
        assert manager.get_currency_balance('USDT') == 1000.0

    # TODO: No check on None result
    def test_get_market_sell_price(self, DoUserConfig, mmbm):
        db, manager = mmbm
        val = manager.get_ticker_price('XLMUSDT')
        price01 = manager.get_market_sell_price('XLMUSDT', 20)
        assert price01[0]
        assert price01[1] == val*20.0

    # TODO: No check on None result
    @pytest.mark.parametrize('ticker',['XLMUSDT', 'BTTUSDT','BTCUSDT'])
    def test_get_market_buy_price(self, DoUserConfig, mmbm, ticker):
        db, manager = mmbm
        qoute = 100.0
        price   = manager.get_ticker_price(ticker)
        price01 = manager.get_market_buy_price(ticker, qoute)
        assert price01[0]
        assert price01[1] == qoute/price

    # TODO: === previous? Are is sell or buy
    @pytest.mark.skip(reason='Unclear, buy or sell?')
    def test_get_market_sell_price_fill_quote(self, DoUserConfig, mmbm):
        db, manager = mmbm
        qoute = 100.0
        price   = manager.get_ticker_price('XLMUSDT')
        price01 = manager.get_market_sell_price_fill_quote('XLMUSDT', qoute)
        assert price01[0]
        assert price01[1] == qoute/price

    @pytest.mark.parametrize('origin_coin',['BTT', 'XLM'])
    @pytest.mark.parametrize('target_coin',['USDT', ])
    def test_buy_alt(self, DoUserConfig, mmbm, origin_coin, target_coin):
        db, manager = mmbm

        from_coin_price = manager.get_ticker_price(origin_coin + target_coin)

        buy_price = from_coin_price+1e-14
        with pytest.raises(AssertionError):
            res: BinanceOrder = manager.buy_alt(origin_coin, target_coin, buy_price)

        target_balance = manager.get_currency_balance(target_coin)
        order_quantity =  manager.buy_quantity(origin_coin, target_coin, target_balance, from_coin_price)
        target_quantity = order_quantity * from_coin_price

        buy_price = from_coin_price
        res: BinanceOrder = manager.buy_alt(origin_coin, target_coin, buy_price)

        assert res.cumulative_quote_qty == target_quantity
        assert res.price == from_coin_price
        assert res.cumulative_filled_quantity == order_quantity

        target_balance = manager.get_currency_balance(target_coin)
        order_quantity = manager.buy_quantity(origin_coin, target_coin, target_balance, from_coin_price)
        target_quantity = order_quantity * from_coin_price

        buy_price = 0.0
        res: BinanceOrder = manager.buy_alt(origin_coin, target_coin, buy_price)

        assert res.cumulative_quote_qty == target_quantity
        assert res.price == from_coin_price
        assert res.cumulative_filled_quantity == order_quantity

    @pytest.mark.parametrize('origin_coin',['BTT', 'XLM'])
    @pytest.mark.parametrize('target_coin',['USDT', ])
    def test_sell_alt(self, DoUserConfig, mmbm, origin_coin, target_coin):
        db, manager = mmbm

        from_coin_price = manager.get_ticker_price(origin_coin + target_coin)

        sell_price = from_coin_price+1e-14
        with pytest.raises(AssertionError):
            res = manager.sell_alt(origin_coin, target_coin, sell_price)

        sell_price = from_coin_price
        origin_balance = manager.get_currency_balance(origin_coin)
        order_quantity = manager.sell_quantity(origin_coin, target_coin, origin_balance)
        target_quantity = order_quantity * from_coin_price

        res = manager.sell_alt(origin_coin, target_coin, sell_price)
        print(res)
        assert res.cumulative_quote_qty == target_quantity
        assert res.price == from_coin_price
        assert res.cumulative_filled_quantity == order_quantity


    # TODO: Add calculation
    @pytest.mark.parametrize('target_ticker',['BTT', 'XLM', 'DOGE'])
    def test_collate_coins(self, DoUserConfig, mmbm, target_ticker):
        db, manager = mmbm
        res = manager.collate_coins(target_ticker)
        print(f'\nresult - {res}')
        assert True
