import pytest

import os, datetime
from typing import Dict, List

from binance.client import Client
from sqlitedict import SqliteDict

from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.backtest import backtest, MockDatabase, MockBinanceManager
from binance_trade_bot.binance_api_manager import BinanceAPIManager, BinanceOrderBalanceManager
from binance_trade_bot.binance_stream_manager import BinanceCache, BinanceOrder
from binance_trade_bot.config import Config
from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.models import Coin
from binance_trade_bot.strategies import get_strategy
from binance_trade_bot.ratios import CoinStub

from .common import infra, dmlc


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

@pytest.fixture()
def mmbm():

    logger: Logger = Logger(logging_service="guliguli")
    config: Config = Config()
    sqlite_cache = SqliteDict("data/testtest_cache.db")

    db = Database(logger, config)
    db.create_database()
    db.set_coins(config.SUPPORTED_COIN_LIST)

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

    yield db, manager, logger, config

    #manager.close()
    #db.close()
    sqlite_cache.close()

class StubAutoTrader(AutoTrader) :
    def scout(self):
        return

class TestAutoTrader:

    def test_initialize(self, DoUserConfig, mmbm):
        # test on run
        db, manager, logger, config = mmbm
        autotrade = StubAutoTrader(manager, db, logger, config)
        autotrade.initialize()
        assert True

    def test_transaction_through_bridge(self, DoUserConfig, mmbm):
        # test on run
        db, manager, logger, config = mmbm

        autotrade = StubAutoTrader(manager, db, logger, config)

        coinfrom = CoinStub.get_by_symbol('XLM')
        cointo = CoinStub.get_by_symbol('EOS')

        sell_price = autotrade.manager.get_ticker_price('XLMUSDT')
        buy_price  = autotrade.manager.get_ticker_price('EOSUSDT')

        autotrade.transaction_through_bridge(coinfrom, cointo, sell_price, buy_price)
        assert True

    # TODO: Check matrix+breaks
    @pytest.mark.parametrize("coin_symbol",['XLM', 'DOGE'])
    def test_update_trade_threshold(self, DoUserConfig, mmbm, coin_symbol):

        # test on run
        db, manager, logger, config = mmbm

        autotrade = StubAutoTrader(manager, db, logger, config)

        coin = CoinStub.get_by_symbol(coin_symbol)
        res = autotrade.update_trade_threshold(coin, None, 100)
        assert not res

        coin = CoinStub.get_by_symbol('XLM')
        res = autotrade.update_trade_threshold(coin, 1000, 100)
        assert res

    # TODO: Check value
    def test__max_value_in_wallet(self, DoUserConfig, mmbm):
        # test on run
        db, manager, logger, config = mmbm

        autotrade = StubAutoTrader(manager, db, logger, config)
        res = autotrade._max_value_in_wallet()
        print('\n_max_value_in_wallet', res)
        assert True

    # TODO: Check range(10)
    def test_initialize_trade_thresholds(self, DoUserConfig, mmbm):

        # test on run
        db, manager, logger, config = mmbm

        autotrade = StubAutoTrader(manager, db, logger, config)
        res = autotrade.initialize_trade_thresholds()
        assert True

    def test_scout(self, DoUserConfig, mmbm):

        # test on run
        db, manager, logger, config = mmbm

        autotrade = StubAutoTrader(manager, db, logger, config)
        autotrade.scout()
        assert True

    # TODO: Check amounts
    @pytest.mark.parametrize("coin_symbol",['XLM', 'DOGE'])
    def test__get_ratios(self, DoUserConfig, mmbm, coin_symbol):
        # test on run
        db, manager, logger, config = mmbm

        coin = CoinStub.get_by_symbol(coin_symbol)
        autotrade = StubAutoTrader(manager, db, logger, config)

        ratio_dict, price_amounts = autotrade._get_ratios(coin,100,100)
        print('\n', ratio_dict, '\n', price_amounts)
        assert True

    @pytest.mark.parametrize("coin_symbol",['XLM', 'DOGE'])
    def test__jump_to_best_coin(self, DoUserConfig, mmbm, coin_symbol):
        # test on run
        db, manager, logger, config = mmbm

        coin = CoinStub.get_by_symbol(coin_symbol)
        autotrade = StubAutoTrader(manager, db, logger, config)

        autotrade._jump_to_best_coin(coin, 100, 100, 20)
        assert True

    def test_bridge_scout(self, DoUserConfig, mmbm):
        # test on run
        db, manager, logger, config = mmbm

        autotrade = StubAutoTrader(manager, db, logger, config)

        res = autotrade.bridge_scout()
        assert res is None

    def test_update_values(self):
        assert False
