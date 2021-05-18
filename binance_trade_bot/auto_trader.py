from datetime import datetime
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from .binance_api_manager import BinanceAPIManager
from .config import Config
from .database import Database
from .logger import Logger
from .models import Coin, CoinValue, Pair, ScoutHistory


class AutoTrader:
    def __init__(self, binance_manager: BinanceAPIManager, database: Database, logger: Logger, config: Config):
        self.manager = binance_manager
        self.db = database
        self.logger = logger
        self.config = config

    def initialize(self):
        self.initialize_trade_thresholds()

    def transaction_through_bridge(self, from_coin: Coin, to_coin: Coin, sell_price: float, buy_price: float):
        """
        Jump from the source coin to the destination coin through bridge coin
        """
        can_sell = False
        balance = self.manager.get_currency_balance(from_coin.symbol)

        if balance and balance * sell_price > self.manager.get_min_notional(
            from_coin.symbol, self.config.BRIDGE.symbol
        ):
            can_sell = True
        else:
            self.logger.info("Skipping sell")

        if can_sell and self.manager.sell_alt(from_coin, self.config.BRIDGE, sell_price) is None:
            self.logger.info("Couldn't sell, going back to scouting mode...")
            return None

        result = self.manager.buy_alt(to_coin, self.config.BRIDGE, buy_price)
        if result is not None:
            self.db.set_current_coin(to_coin)
            price = result.price
            if abs(price) < 1e-15:
                price = result.cumulative_filled_quantity / result.cumulative_quote_qty

            self.update_trade_threshold(to_coin, price)
            return result

        self.logger.info("Couldn't buy, going back to scouting mode...")
        return None

    def update_trade_threshold(self, coin: Coin, coin_price: float):
        """
        Update all the coins with the threshold of buying the current held coin
        """

        if coin_price is None:
            self.logger.info("Skipping update... current coin {} not found".format(coin + self.config.BRIDGE))
            return

        session: Session
        with self.db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.to_coin == coin):
                from_coin_price = self.manager.get_ticker_price(pair.from_coin + self.config.BRIDGE)

                if from_coin_price is None:
                    self.logger.info(
                        "Skipping update for coin {} not found".format(pair.from_coin + self.config.BRIDGE)
                    )
                    continue

                pair.ratio = from_coin_price / coin_price

    def initialize_trade_thresholds(self):
        """
        Initialize the buying threshold of all the coins for trading between them
        """
        session: Session
        with self.db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.ratio.is_(None)).all():
                if not pair.from_coin.enabled or not pair.to_coin.enabled:
                    continue
                self.logger.info(f"Initializing {pair.from_coin} vs {pair.to_coin}")

                from_coin_price = self.manager.get_ticker_price(pair.from_coin + self.config.BRIDGE)
                if from_coin_price is None:
                    self.logger.info(
                        "Skipping initializing {}, symbol not found".format(pair.from_coin + self.config.BRIDGE)
                    )
                    continue

                to_coin_price = self.manager.get_ticker_price(pair.to_coin + self.config.BRIDGE)
                if to_coin_price is None:
                    self.logger.info(
                        "Skipping initializing {}, symbol not found".format(pair.to_coin + self.config.BRIDGE)
                    )
                    continue

                pair.ratio = from_coin_price / to_coin_price

    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        raise NotImplementedError()

    def _get_ratios(self, coin: Coin, coin_price, enable_scout_log=True) -> Tuple[Dict[Pair, float], Dict[str, float]]:
        """
        Given a coin, get the current price ratio for every other enabled coin
        """
        ratio_dict: Dict[Pair, float] = {}
        prices: Dict[str, float] = {}

        scout_logs = []
        for pair in self.db.get_pairs_from(coin):
            optional_coin_price = self.manager.get_ticker_price(pair.to_coin + self.config.BRIDGE)
            prices[pair.to_coin_id] = optional_coin_price

            if optional_coin_price is None:
                self.logger.info(
                    "Skipping scouting... optional coin {} not found".format(pair.to_coin + self.config.BRIDGE)
                )
                continue

            if enable_scout_log:
                scout_logs.append(ScoutHistory(pair, pair.ratio, coin_price, optional_coin_price))

            # Obtain (current coin)/(optional coin)
            coin_opt_coin_ratio = coin_price / optional_coin_price

            transaction_fee = self.manager.get_fee(pair.from_coin, self.config.BRIDGE, True) + self.manager.get_fee(
                pair.to_coin, self.config.BRIDGE, False
            )

            ratio_dict[pair] = (
                coin_opt_coin_ratio - transaction_fee * self.config.SCOUT_MULTIPLIER * coin_opt_coin_ratio
            ) - pair.ratio

        if len(scout_logs) > 0:
            self.db.batch_log_scout(scout_logs)

        return ratio_dict, prices

    def _jump_to_best_coin(self, coin: Coin, coin_price: float):
        """
        Given a coin, search for a coin to jump to
        """
        can_walk_deeper = True
        jump_chain = [coin.symbol]
        # We simulate a possible buy chain and land on its very end, updating all ratios along the path
        # as it would be if we buy them all with real orders
        last_coin: Coin = coin
        last_coin_price = coin_price
        while can_walk_deeper:
            ratio_dict, prices = self._get_ratios(last_coin, last_coin_price, enable_scout_log=(len(jump_chain) > 1))

            ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}

            # if we have any viable options, pick the one with the biggest ratio
            if ratio_dict:
                new_best_pair = max(ratio_dict, key=ratio_dict.get)
                if len(jump_chain) > 1:  # update thresholds because we should buy anyway when walk through chain
                    self.update_trade_threshold(last_coin, last_coin_price)
                last_coin = new_best_pair.to_coin
                last_coin_price = prices[last_coin.symbol]
                jump_chain.append(last_coin.symbol)
            else:
                can_walk_deeper = False

        if len(jump_chain) > 1:
            if len(jump_chain) > 2:
                self.logger.info(f"Squashed jump chain: {jump_chain}")
            if jump_chain[0] != jump_chain[-1]:
                self.logger.info(f"Will be jumping from {coin} to {last_coin}")
                self.transaction_through_bridge(coin, last_coin, coin_price, last_coin_price)
            else:
                self.update_trade_threshold(coin, coin_price)
                self.logger.info(f"Eliminated jump loop from {coin} to {coin}")

    def bridge_scout(self):
        """
        If we have any bridge coin leftover, buy a coin with it that we won't immediately trade out of
        """
        bridge_balance = self.manager.get_currency_balance(self.config.BRIDGE.symbol)

        for coin in self.db.get_coins():
            current_coin_price = self.manager.get_ticker_price(coin + self.config.BRIDGE)

            if current_coin_price is None:
                continue

            ratio_dict, prices = self._get_ratios(coin, current_coin_price)
            if not any(v > 0 for v in ratio_dict.values()):
                # There will only be one coin where all the ratios are negative. When we find it, buy it if we can
                if bridge_balance > self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol):
                    self.logger.info(f"Will be purchasing {coin} using bridge coin")
                    self.manager.buy_alt(coin, self.config.BRIDGE, prices[coin.symbol])
                    return coin
        return None

    def update_values(self):
        """
        Log current value state of all altcoin balances against BTC and USDT in DB.
        """
        now = datetime.now()

        coins = self.db.get_coins(False)
        cv_batch = []
        for coin in coins:
            balance = self.manager.get_currency_balance(coin.symbol)
            if balance == 0:
                continue
            usd_value = self.manager.get_ticker_price(coin + "USDT")
            btc_value = self.manager.get_ticker_price(coin + "BTC")
            cv = CoinValue(coin, balance, usd_value, btc_value, datetime=now)
            cv_batch.append(cv)
        self.db.batch_update_coin_values(cv_batch)
