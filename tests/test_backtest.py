import pytest

import os, datetime
from binance_trade_bot import backtest

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

@pytest.mark.timeout(60)
@pytest.mark.skip(reason='Long working time')
def test_backtest_main_module_on_run(capsys, infra, DoUserConfig) :
    with pytest.raises(KeyError) as rraise :
        #rr.run_module('../backtest.py',run_name='__main__')
        rr.run_path('backtest.py',run_name='__main__')

    assert True

#####@pytest.mark.skip(reason="for debug time")
def test_backtest1_on_run(infra,DoUserConfig):
    backtest(datetime.datetime(2021,6,1),datetime.datetime.now())
    assert True

@pytest.mark.timeout(600)
@pytest.mark.parametrize("date_start",[datetime.datetime(2021,6,1),])
@pytest.mark.parametrize("date_end",[datetime.datetime(2021,6,3),])
@pytest.mark.parametrize("interval",[10,])
def test_backtest2_on_run(infra,DoUserConfig, date_start, date_end, interval):
    history = []
    for manager in backtest(date_start,date_end, interval=interval):

        btc_value = manager.collate_coins("BTC")
        bridge_value = manager.collate_coins(manager.config.BRIDGE.symbol)
        history.append((btc_value, bridge_value))
        btc_diff = round((btc_value - history[0][0]) / history[0][0] * 100, 3)
        bridge_diff = round((bridge_value - history[0][1]) / history[0][1] * 100, 3)

        print(datetime.datetime.now(), "-"*40)
        print(datetime.datetime.now(), "TIME:", manager.datetime)
        print(datetime.datetime.now(), "BALANCES:", manager.balances)
        print(datetime.datetime.now(), "BTC VALUE:", btc_value, f"({btc_diff}%)")
        print(datetime.datetime.now(), f"{manager.config.BRIDGE.symbol} VALUE:", bridge_value, f"({bridge_diff}%)")

    assert True

