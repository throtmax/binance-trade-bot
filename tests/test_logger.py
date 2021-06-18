import pytest
import os

from binance_trade_bot.logger import Logger
from .common import infra

@pytest.fixture(scope='function', params=['crypto_trading', 'boba_boba'])
def createAndDeleteFile(infra, request):

    ln = request.param
    fn = os.path.join('logs', ln+'.log')

    if os.path.exists(fn):
        os.remove(fn)

    yield ln, fn

    if os.path.exists(fn):
        os.remove(fn)



def test_log1(capsys, createAndDeleteFile) :

    ln,fn = createAndDeleteFile

    #caplog - not work?

    logs = Logger(enable_notifications=True,logging_service=ln)

    assert os.path.exists(fn), "Log file not exists"

    logs.error('rroorree')
    captured = capsys.readouterr()
    assert str(captured).find('ERROR')>-1

    logs.info ('ooffnnii')
    captured = capsys.readouterr()
    assert str(captured).find('INFO')>-1

    logs.warning('ggnniinnrraaww')
    captured = capsys.readouterr()
    assert str(captured).find('WARNING')>-1

    assert os.path.exists(fn), "Log file not exists"

@pytest.mark.xfail
def test_log1_(capsys,createAndDeleteFile): # bad case

    ln,fn = createAndDeleteFile

    #caplog - not work?

    logs = Logger(enable_notifications=True,logging_service=ln)

    assert os.path.exists(fn), "Log file not exists"

    logs.debug('gguubbeedd', notification=True)
    captured = capsys.readouterr()
    assert str(captured).find('DEBUG')>-1

    logs.log('guliguli',level='ddebug',notification=True)
    captured = capsys.readouterr()
    assert str(captured).find('DEBUG')>-1

    assert os.path.exists(fn), "Log file not exists"

@pytest.mark.xfail
def test_log2(capsys,createAndDeleteFile):

    ln,fn = createAndDeleteFile

    # caplog - not work?

    logs2 = Logger(enable_notifications=False, logging_service=ln)

    assert os.path.exists(fn), "Log file not exists"

    logs2.warning('ggnniinnrraaww',notification=False)
    captured = capsys.readouterr()
    assert len(str(captured))==0 , 'Notification==False , but informing?'
    print('\n',captured)

