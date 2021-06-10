import pytest

import os, datetime, pathlib

#TODO fuse.hidenXXXXX - files don't remove directories

@pytest.fixture()
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

def test_common(infra):
    return