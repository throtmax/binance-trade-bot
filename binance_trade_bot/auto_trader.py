import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, Tuple

from sqlalchemy.orm import Session, scoped_session

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
        if self.manager.sell_alt(from_coin, self.config.BRIDGE, sell_price) is None:
            self.logger.error(
                f"Market sell failed, from_coin: {from_coin}, to_coin: {to_coin}, sell_price: {sell_price}"
            )

        result = self.manager.buy_alt(to_coin, self.config.BRIDGE, buy_price)
        if result is not None:
            self.db.set_current_coin(to_coin)
            price = result.price
            if abs(price) < 1e-15:
                price = result.cumulative_filled_quantity / result.cumulative_quote_qty

            update_successful = False
            while not update_successful:
                update_successful = self.update_trade_threshold(to_coin, price, result.cumulative_quote_qty)
                if not update_successful:
                    self.logger.info("Update of ratios failed, retry in 1s")
                    time.sleep(1)

            return result

        self.logger.info("Couldn't buy, going back to scouting mode...")
        return None

    def update_trade_threshold(
        self, coin: Coin, coin_buy_price: float, quote_amount: float, external_session=None
    ) -> bool:
        """
        Update all the coins with the threshold of buying the current held coin

        :returns True if update was successful, False otherwise
        """

        if coin_buy_price is None:
            self.logger.info("Skipping update... current coin {} not found".format(coin + self.config.BRIDGE))
            return False

        external_session: Session
        with self.db.manage_session(external_session) as session:
            for pair in session.query(Pair).filter(Pair.to_coin == coin):
                from_coin_price, _ = self.manager.get_market_sell_price_fill_quote(
                    pair.from_coin + self.config.BRIDGE, quote_amount
                )

                if from_coin_price is None:
                    self.logger.info(
                        f"Update for coin {pair.from_coin + self.config.BRIDGE} can't be performed, not enough orders "
                        f"in order book "
                    )
                    return False

                pair.ratio = from_coin_price / coin_buy_price
        return True

    def initialize_trade_thresholds(self):
        """
        Initialize the buying threshold of all the coins for trading between them
        """
        session: Session
        with self.db.db_session() as session:
            pairs = session.query(Pair).filter(Pair.ratio.is_(None)).all()
            grouped_pairs = defaultdict(list)
            for pair in pairs:
                if pair.from_coin.enabled and pair.to_coin.enabled:
                    grouped_pairs[pair.from_coin.symbol].append(pair)
            for from_coin_symbol, group in grouped_pairs.items():
                self.logger.info(f"Initializing {from_coin_symbol} vs [{', '.join([p.to_coin.symbol for p in group])}]")
                for pair in group:
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

    def _get_ratios(
        self, coin: Coin, coin_sell_price, quote_amount, enable_scout_log=True, session=None
    ) -> Tuple[Dict[Pair, float], Dict[str, Tuple[float, float]]]:
        """
        Given a coin, get the current price ratio for every other enabled coin
        """
        ratio_dict: Dict[Pair, float] = {}
        price_amounts: Dict[str, (float, float)] = {}

        scout_logs = []
        for pair in self.db.get_pairs_from(coin, external_session=session):
            optional_coin_buy_price, optional_coin_amount = self.manager.get_market_buy_price(
                pair.to_coin + self.config.BRIDGE, quote_amount
            )

            if optional_coin_buy_price is None:
                self.logger.info(  # NB: exclude missing coins on start-up
                    f"Market price for coin {pair.to_coin + self.config.BRIDGE} can't be calculated, skipping"
                )
                continue

            price_amounts[pair.to_coin_id] = (optional_coin_buy_price, optional_coin_amount)

            if enable_scout_log:
                scout_logs.append(ScoutHistory(pair, pair.ratio, coin_sell_price, optional_coin_buy_price))

            # Obtain (current coin)/(optional coin)
            coin_opt_coin_ratio = coin_sell_price / optional_coin_buy_price

            transaction_fee = self.manager.get_fee(pair.from_coin, self.config.BRIDGE, True) + self.manager.get_fee(
                pair.to_coin, self.config.BRIDGE, False
            )

            ratio_dict[pair] = (
                coin_opt_coin_ratio - transaction_fee * self.config.SCOUT_MULTIPLIER * coin_opt_coin_ratio
            ) - pair.ratio

        if len(scout_logs) > 0:
            self.db.batch_log_scout(scout_logs)

        return ratio_dict, price_amounts

    def _jump_to_best_coin(
        self, coin: Coin, coin_sell_price: float, quote_amount: float, coin_amount: float
    ):  # pylint: disable=too-many-locals
        """
        Given a coin, search for a coin to jump to
        """
        can_walk_deeper = True
        jump_chain = [coin.symbol]
        # We simulate a possible buy chain and land on its very end, updating all ratios along the path
        # as it would be if we buy them all with real orders
        last_coin: Coin = coin
        last_coin_sell_price = coin_sell_price
        last_coin_buy_price = 0.0  # it will be set for reasonable value after we found our first jump candidate
        last_coin_quote = quote_amount
        last_coin_amount = coin_amount
        session: scoped_session
        is_initial_coin = True
        with self.db.db_session() as session:
            while can_walk_deeper:
                if not is_initial_coin:
                    last_coin_sell_price, last_coin_quote = self.manager.get_market_sell_price(
                        last_coin.symbol + self.config.BRIDGE.symbol, last_coin_amount
                    )
                    if last_coin_sell_price is None:
                        session.rollback()
                        return
                ratio_dict, prices = self._get_ratios(
                    last_coin, last_coin_sell_price, last_coin_quote, enable_scout_log=is_initial_coin, session=session
                )

                ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}

                # if we have any viable options, pick the one with the biggest ratio
                if ratio_dict:
                    new_best_pair = max(ratio_dict, key=ratio_dict.get)
                    if not is_initial_coin:  # update thresholds because we should buy anyway when walk through chain
                        # This should be performed in a single transaction so we don't leave our ratios in invalid state
                        if not self.update_trade_threshold(last_coin, last_coin_buy_price, last_coin_quote, session):
                            session.rollback()
                            return
                    last_coin = new_best_pair.to_coin
                    last_coin_buy_price, last_coin_amount = prices[last_coin.symbol]
                    jump_chain.append(last_coin.symbol)
                    is_initial_coin = False
                else:
                    can_walk_deeper = False
            session.expunge_all()

        if not is_initial_coin:
            if len(jump_chain) > 2:
                self.logger.info(f"Squashed jump chain: {jump_chain}")
            if jump_chain[0] != jump_chain[-1]:
                self.logger.info(f"Will be jumping from {coin} to {last_coin}")
                self.transaction_through_bridge(coin, last_coin, coin_sell_price, last_coin_buy_price)
            else:
                self.update_trade_threshold(coin, coin_sell_price, quote_amount)
                self.logger.info(f"Eliminated jump loop from {coin} to {coin}")

    def bridge_scout(self):
        """
        If we have any bridge coin leftover, buy a coin with it that we won't immediately trade out of
        """
        bridge_balance = self.manager.get_currency_balance(self.config.BRIDGE.symbol)

        coins = self.db.get_coins()
        if all(
            bridge_balance <= self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol) for coin in coins
        ):
            return None

        print("do bridge scout")

        for coin in coins:
            current_coin_price = self.manager.get_ticker_price(coin + self.config.BRIDGE)

            if current_coin_price is None:
                continue

            ratio_dict, _ = self._get_ratios(coin, current_coin_price, bridge_balance)
            if not any(v > 0 for v in ratio_dict.values()):
                # There will only be one coin where all the ratios are negative. When we find it, buy it if we can
                if bridge_balance > self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol):
                    self.logger.info(f"Will be purchasing {coin} using bridge coin")
                    result = self.manager.buy_alt(
                        coin, self.config.BRIDGE, self.manager.get_ticker_price(coin + self.config.BRIDGE)
                    )
                    if result is not None:
                        self.db.set_current_coin(coin)
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
