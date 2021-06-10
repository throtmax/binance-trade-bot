import pytest

import os

from binance_trade_bot.database import Database
from binance_trade_bot.logger   import Logger
from binance_trade_bot.config   import Config
from binance_trade_bot.models.coin import Coin

from .common import infra

@pytest.fixture(scope='class', autouse=True)
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

    #os.environ['CURRENT_COIN'] = 'ETH'
    os.environ['CURRENT_COIN_SYMBOL'] = 'ETH'

    os.environ['API_KEY'] = 'vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A'
    os.environ['API_SECRET_KEY'] = 'NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j'
    #os.environ['CURRENT_COIN_SYMBOL'] = 'BTT'
    os.environ['SUPPORTED_COIN_LIST'] = "XLM TRX ICX EOS IOTA ONT QTUM ETC ADA XMR DASH NEO ATOM DOGE VET BAT OMG BTT"
    os.environ['BRIDGE_SYMBOL'] = "USDT"
    os.environ['SCOUT_MULTIPLIER'] = "5"
    os.environ['SCOUT_SLEEP_TIME'] = "1"
    os.environ['TLD'] = 'com'
    os.environ['STRATEGY'] = 'default'
    os.environ['BUY_TIMEOUT']  = "0"
    os.environ['SELL_TIMEOUT'] = "0"
    os.environ['BUY_ORDER_TYPE'] = 'limit'
    os.environ['SELL_ORDER_TYPE'] = 'market'

    yield

class TestDatabase:
    def test_socketio_connect(self):
        assert False

    def test_db_session(self):
        assert False

    def test_schedule_execute_later(self):
        assert False

    def test_execute_postponed_calls(self):
        assert False

    def test_manage_session(self):
        assert False

    def test_set_coins(self,DoUserConfig, infra):
        logger = Logger("db_testing", enable_notifications=False)
        config = Config()

        dbtest = Database(logger, config)
        dbtest.create_database()

        # testing empty
        dbtest.set_coins([])
        listCoins = dbtest.get_coins(only_enabled=False)
        assert len(listCoins) == len(config.SUPPORTED_COIN_LIST), "Not matched size"
        for ii in listCoins:
            assert ii.symbol in config.SUPPORTED_COIN_LIST, "No matched"

        # testing not empty
        dbtest.set_coins(config.SUPPORTED_COIN_LIST)
        listCoins = dbtest.get_coins(only_enabled=False)
        assert len(listCoins) == len(config.SUPPORTED_COIN_LIST), "Not matched size"
        for ii in listCoins:
            assert ii.symbol in config.SUPPORTED_COIN_LIST, "No matched"

    def test_get_coins(self,DoUserConfig,infra):

        logger = Logger("db_testing", enable_notifications=False)
        config = Config()

        dbtest = Database(logger, config)
        dbtest.create_database()

        # TODO: what do with enable?
        # testing empty
        dbtest.set_coins([])
        listCoins = dbtest.get_coins(only_enabled=False)
        assert len(listCoins) == len(config.SUPPORTED_COIN_LIST), "Not matched size"
        for ii in listCoins:
            assert ii.symbol in config.SUPPORTED_COIN_LIST, "No matched"

        # testing not empty
        dbtest.set_coins(config.SUPPORTED_COIN_LIST)
        listCoins = dbtest.get_coins(only_enabled=False)
        assert len(listCoins) == len(config.SUPPORTED_COIN_LIST), "Not matched size"
        for ii in listCoins:
            assert ii.symbol in config.SUPPORTED_COIN_LIST, "No matched"

    def test_get_coin(self,infra):

        logger = Logger("db_testing", enable_notifications=False)
        config = Config()

        dbtest = Database(logger, config)
        dbtest.create_database()

        # TODO: not KeyError raises?
        '''
        with pytest.raises(KeyError) :
            ccoin = dbtest.get_coin('XXXXXX')
        '''

        dbtest.set_coins(config.SUPPORTED_COIN_LIST)

        # testing string
        ccoin = dbtest.get_coin(config.SUPPORTED_COIN_LIST[0])
        assert config.SUPPORTED_COIN_LIST[0] == ccoin.symbol

        # testing type
        ccoin = dbtest.get_coin(Coin(config.SUPPORTED_COIN_LIST[-1]))
        assert config.SUPPORTED_COIN_LIST[-1] == ccoin.symbol

    def test_set_current_coin(self, infra):

        logger = Logger("db_testing", enable_notifications=False)
        config = Config()

        dbtest = Database(logger, config)
        dbtest.create_database()

        # TODO: not KeyError raises?
        '''
        with pytest.raises(KeyError) :
            ccoin = dbtest.get_coin('XXXXXX')
        '''

        dbtest.set_coins(config.SUPPORTED_COIN_LIST)

        # testing string
        dbtest.set_current_coin(config.SUPPORTED_COIN_LIST[0])
        ccoin: Coin = dbtest.get_current_coin()
        assert config.SUPPORTED_COIN_LIST[0] == ccoin.symbol

        # testing type
        dbtest.set_current_coin(Coin(config.SUPPORTED_COIN_LIST[-1]))
        ccoin: Coin = dbtest.get_current_coin()
        assert config.SUPPORTED_COIN_LIST[-1] == ccoin.symbol

    def test_get_current_coin(self):
        logger = Logger("db_testing", enable_notifications=False)
        config = Config()

        dbtest = Database(logger, config)
        dbtest.create_database()

        # TODO: add specificate
        # TODO: not KeyError raises?
        '''
        with pytest.raises(KeyError) :
            ccoin = dbtest.get_coin('XXXXXX')
        '''

        dbtest.set_coins(config.SUPPORTED_COIN_LIST)

        # testing string
        dbtest.set_current_coin(config.SUPPORTED_COIN_LIST[0])
        ccoin: Coin = dbtest.get_current_coin()
        assert config.SUPPORTED_COIN_LIST[0] == ccoin.symbol

        # testing type
        dbtest.set_current_coin(Coin(config.SUPPORTED_COIN_LIST[-1]))
        ccoin: Coin = dbtest.get_current_coin()
        assert config.SUPPORTED_COIN_LIST[-1] == ccoin.symbol

    def test_get_pair(self,DoUserConfig,infra):
        assert False

    def test_batch_log_scout(self,DoUserConfig,infra):
        assert False

    def test_prune_scout_history(self):
        assert False

    def test_prune_value_history(self):
        assert False

    def test_create_database(self):
        assert False

    def test_start_trade_log(self):
        assert False

    def test_send_update(self):
        assert False

    def test_migrate_old_state(self):
        assert False

    def test_commit_ratios(self):
        assert False

    def test_batch_update_coin_values(self):
        assert False
