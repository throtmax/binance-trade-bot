import pytest

import os, datetime, pathlib

#TODO fuse.hidenXXXXX - files don't remove directories

@pytest.fixture(autouse=True)
def infra(delete_ok=False, delete_ok_first=False, dirs=['logs','data']):

    if delete_ok_first:
        for iidirs in dirs:
            if pathlib.Path(iidirs).exists():
                for child in pathlib.Path(iidirs).iterdir():
                    print('\n',child)
                    #pathlib.Path(child).unlink()
                    os.remove(child)
                pathlib.Path(iidirs).rmdir()

    for iidirs in dirs:
        pathlib.Path(iidirs).mkdir(exist_ok=True)

    yield

    if delete_ok :
        for iidirs in dirs:
            childs = [child for child in pathlib.Path(iidirs).iterdir()]
            for child in childs:
                pathlib.Path(child).unlink()
                print(child)
            pathlib.Path(iidirs).rmdir()

    return()

@pytest.fixture()
def dmlc():

    logger: Logger = Logger(logging_service="guliguli")
    config: Config = Config()
    sqlite_cache = SqliteDict("data/testtest_cache.db")

    db = MockDatabase(logger, config)
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



def test_common(infra):
    return