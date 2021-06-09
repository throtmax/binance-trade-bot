import pytest

import os, datetime

from binance_trade_bot.config import Config
from binance_trade_bot.models import Coin

def ConfigTest ():

    params = dict()

    params['CURRENT_COIN'] = 'ETH'
    params['CURRENT_COIN_SYMBOL'] = 'ETH'

    params['API_KEY'] = 'vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A'
    params['API_SECRET_KEY'] = 'NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j'
    params['SUPPORTED_COIN_LIST'] = "XLM TRX ICX EOS IOTA ONT QTUM ETC ADA XMR DASH NEO ATOM DOGE VET BAT OMG BTT"
    params['BRIDGE_SYMBOL'] = "USDT"
    params['SCOUT_MULTIPLIER'] = "5"
    params['SCOUT_SLEEP_TIME'] = "1"
    params['TLD'] = 'com'
    params['STRATEGY'] = 'default'
    params['BUY_TIMEOUT']  = "0"
    params['SELL_TIMEOUT'] = "0"
    params['BUY_ORDER_TYPE'] = 'limit'
    params['SELL_ORDER_TYPE'] = 'market'

    params['BRIDGE'] = 'USDT'  ## ??????????

    return(params)

@pytest.fixture(scope='function')
def DoUserConfigEnv():

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

    params = ConfigTest()
    for ikey in params.keys() :
        os.environ[ikey] = params[ikey]

    return

def test_config_on_run(DoUserConfigEnv):

    config = Config()
    params = ConfigTest()

    for ikey in params:
        mustvalue= params[ikey]
        if ikey=='CURRENT_COIN':   ikey = 'CURRENT_COIN_SYMBOL'
        if ikey=='API_KEY':        ikey = 'BINANCE_API_KEY'
        if ikey=='API_SECRET_KEY': ikey = 'BINANCE_API_SECRET_KEY'
        if ikey=='TLD':            ikey = 'BINANCE_TLD'

        getvalue = eval('config.'+ikey)

        if ikey=='SUPPORTED_COIN_LIST' : getvalue  = ' '.join(getvalue)
        if ikey=='SCOUT_MULTIPLIER'    : mustvalue = float(mustvalue)
        if ikey=='SCOUT_SLEEP_TIME'    : mustvalue = int(mustvalue)
        if ikey=='BUY_ORDER_TYPE'      : mustvalue = mustvalue.upper()
        if ikey=='SELL_ORDER_TYPE'     : mustvalue = mustvalue.upper()
        if ikey=='BRIDGE'              : mustvalue = Coin(mustvalue, False)

        if ikey=="BRIDGE"              : continue # probably compute field from BRIDGE_SYMBOL

        #getvalue = '6789' # for debug test only
        assert mustvalue == getvalue, f'Config values and input values not compare for {ikey}, must be {mustvalue}, get {getvalue}'

    #with pytest.raises(KeyError) as rraise :
    #    config = Config()
