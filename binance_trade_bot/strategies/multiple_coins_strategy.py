import time
from datetime import datetime

from binance_trade_bot.auto_trader import AutoTrader


class Strategy(AutoTrader):
    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        for coin in self.db.get_coins():
            current_coin_balance = self.manager.get_currency_balance(coin.symbol)
            coin_price, quote_amount = self.manager.get_market_sell_price(
                coin + self.config.BRIDGE, current_coin_balance
            )

            if coin_price is None:
                self.logger.info("Skipping scouting... current coin {} not found".format(coin + self.config.BRIDGE))
                continue

            min_notional = self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol)

            if coin_price * current_coin_balance < min_notional:
                continue

            # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot
            # has stopped. Not logging though to reduce log size.
            print(
                f"{datetime.now()} - CONSOLE - INFO - I am scouting the best trades. "
                f"Current coin: {coin + self.config.BRIDGE} ",
                end="\r",
            )

            t1 = time.monotonic_ns()
            self._jump_to_best_coin(coin, coin_price, quote_amount, current_coin_balance)
            print(f"Jump took {time.monotonic_ns() - t1}")

        self.bridge_scout()
