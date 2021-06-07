from array import array
from math import nan
from typing import Dict, Iterable, KeysView, List, Optional, Tuple, Type

from binance_trade_bot.models import Pair


class CoinStub:
    _instances: List["CoinStub"] = []
    _instances_by_symbol: Dict[str, "CoinStub"] = {}

    def __init__(self, ratio_idx: int, symbol: str):
        """
        Don't call this directly, use create method
        :param ratio_idx:
        :param symbol:
        """
        self.idx = ratio_idx
        self.symbol = symbol

    def __repr__(self):
        return f"CoinStub({self.idx}, {self.symbol})"

    @classmethod
    def create(cls: Type["CoinStub"], symbol: str) -> "CoinStub":
        idx = len(cls._instances)
        new_instance = cls(idx, symbol)
        cls._instances.append(new_instance)
        cls._instances_by_symbol[symbol] = new_instance
        return new_instance

    @classmethod
    def get_by_idx(cls: Type["CoinStub"], idx: int) -> "CoinStub":
        return cls._instances[idx]

    @classmethod
    def get_by_symbol(cls: Type["CoinStub"], symbol: str) -> "CoinStub":
        return cls._instances_by_symbol.get(symbol, None)

    @classmethod
    def reset(cls: Type["CoinStub"]):
        cls._instances.clear()
        cls._instances_by_symbol.clear()

    @classmethod
    def len_coins(cls: Type["CoinStub"]) -> int:
        return len(cls._instances)

    @classmethod
    def get_all(cls: Type["CoinStub"]) -> List["CoinStub"]:
        return cls._instances


class RatiosManager:
    """
    Provides memory storage for all ratios in a form of dense square matrix with a row major order.
    It also has a basic transaction support in a form of commit/rollback calls, which should be much
    more lightweight than SQLAlchemy ORM does.
    """

    def __init__(self, ratios: Optional[Iterable[Pair]] = None):
        self.n = CoinStub.len_coins()
        self._data = array("d", (nan if i != j else 1.0 for i in range(self.n) for j in range(self.n)))
        self._dirty: Dict[Tuple[int, int], float] = {}
        if ratios is not None:
            for pair in ratios:
                i = CoinStub.get_by_symbol(pair.from_coin.symbol).idx
                j = CoinStub.get_by_symbol(pair.to_coin.symbol).idx
                val = pair.ratio if pair.ratio is not None else nan
                self._data[self.n * i + j] = val

    def set(self, from_coin_idx: int, to_coin_idx: int, val: float, /):
        cell = (from_coin_idx, to_coin_idx)
        if cell not in self._dirty:
            self._dirty[cell] = self._data[self.n * cell[0] + cell[1]]
        self._data[self.n * cell[0] + cell[1]] = val

    def get(self, from_coin_idx: int, to_coin_idx: int, /) -> float:
        return self._data[self.n * from_coin_idx + to_coin_idx]

    def get_from_coin(self, from_coin_idx: int):
        return self._data[self.n * from_coin_idx : self.n * (from_coin_idx + 1)]

    def get_to_coin(self, to_coin_idx: int):
        return self._data[to_coin_idx :: self.n]

    def get_dirty(self) -> KeysView[Tuple[int, int]]:
        return self._dirty.keys()

    def rollback(self):
        for cell, old_value in self._dirty.items():
            self._data[self.n * cell[0] + cell[1]] = old_value
        self._dirty.clear()

    def commit(self):
        self._dirty.clear()
