import logging
import sys, os

from  binance_trade_bot.logger import Logger

def test_log1(capsys) :

    #caplog - not work?

    if os.path.exists(os.path.join('logs', 'crypto_trading.log')) :
        os.remove(os.path.join('logs', 'crypto_trading.log'))

    logs = Logger(enable_notifications=True)

    logs.error('rroorree')
    captured = capsys.readouterr()
    assert str(captured).find('ERROR')>-1

    logs.info ('ooffnnii')
    captured = capsys.readouterr()
    assert str(captured).find('INFO')>-1

    logs.warning('ggnniinnrraaww')
    captured = capsys.readouterr()
    assert str(captured).find('WARNING')>-1
    '''
    logs.debug('gguubbeedd', notification=True)
    captured = capsys.readouterr()
    assert str(captured).find('DEBUG')>-1
    
    logs.log('guliguli',level='ddebug',notification=True)
    captured = capsys.readouterr()
    assert str(captured).find('DEBUG')>-1
    '''
    assert os.path.exists(os.path.join('logs','crypto_trading.log')) , "Default log file not exists"

    if os.path.exists(os.path.join('logs', 'crypto_trading.log')) :
        os.remove(os.path.join('logs', 'crypto_trading.log'))

    #print('\nempty:',captured)

    assert True

def test_log2(capsys):

    # caplog - not work?

    if os.path.exists(os.path.join('logs', 'boba_boba.log')) :
        os.remove(os.path.join('logs', 'boba_boba.log'))

    logs2 = Logger(enable_notifications=False, logging_service='boba_boba')

    assert os.path.exists(os.path.join('logs','boba_boba.log')) , "Random log file not exists"

    logs2.warning('ggnniinnrraaww',notification=False)
    captured = capsys.readouterr()
    print('\n',captured)
    assert len(str(captured))==0 , 'Notification==False , but informing?'

    if os.path.exists(os.path.join('logs', 'boba_boba.log')) :
        os.remove(os.path.join('logs', 'boba_boba.log'))

    assert True