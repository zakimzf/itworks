import logging

from datetime import datetime


from utils import ConversionUtils

class ReportGenerator:
    def __init__(
        self,
        telegram,
        alert_skip_threshold,
        pump_emoji="\U0001F7E2",  # 🟢
        dump_emoji="\U0001F534",  # 🔴
    ):
        self.telegram = telegram
        self.alert_skip_threshold = alert_skip_threshold
        self.pump_emoji = pump_emoji
        self.dump_emoji = dump_emoji

        self.logger = logging.getLogger("report-generator")

    async def send_pump_message(self, symbol, interval, change, price):
        await self.telegram.send_message(
            """\
{0} <b>{1} [{2} Interval]</b> | Change: <i>{3:.3f}%</i> | Price: <i>{4:.10f}</i>

<a href="https://www.binance.com/en/trade/{1}?type=spot">Open in Binance App</a>\
            """.format(
                self.pump_emoji, symbol, interval, change * 100, price
            ),
            is_alert_chat=False,
        )

    async def send_dump_message(self, symbol, interval, change, price):
        await self.telegram.send_message(
            """\
{0} <b>{1} [{2} Interval]</b> | Change: <i>{3:.3f}%</i> | Price: <i>{4:.10f}</i>

<a href="https://www.binance.com/en/trade/{1}?type=spot">Open in Binance App</a>\
            """.format(
                self.dump_emoji, symbol, interval, change * 100, price
            ),
            is_alert_chat=False,
        )

    async def send_new_listings(self, symbols_to_add):
        message = """\
<b>New Listings</b>
{0} new pairs found, adding to monitored list.

<b>Adding Pairs:</b>\
            """.format(
            len(symbols_to_add)
        )

        message += "\n"
        for symbol in symbols_to_add:
            message += "- <i>{0}</i>\n".format(symbol)

        await self.telegram.send_news_message(message, is_alert_chat=True)

    async def send_pump_dump_message(
        self,
        asset,
        chart_intervals,
        outlier_intervals,
        current_time,
        dump_enabled=True,
    ):
        change_biggest_delta = 0
        no_of_alerts = 0
        message = ""

        for interval in chart_intervals:

            change = asset[interval]["change_current"]

            # Skip report if no outlier
            if abs(change) < outlier_intervals[interval]:
                self.logger.debug(
                    "Change for asset: %s for interval: %s is to low: %s. Skipping report creation.",
                    asset["symbol"],
                    interval,
                    change,
                )
                continue

            # Remember biggest change of all intervals, to skip later notification
            change_last = asset[interval]["change_last"]
            change_delta = change - change_last

            if abs(change_delta) > abs(change_biggest_delta):
                change_biggest_delta = change_delta

            # Remember the total number of alerts
            no_of_alerts += 1

            if change > 0:
                message += "{0} <b>{1} Interval</b> | Change: <i>{2:.3f}%</i>\n".format(
                    self.pump_emoji,
                    interval,
                    change * 100,
                    asset["price"][-1],
                )

            if change < 0 and dump_enabled:
                message += "{0} <b>{1} Interval</b> | Change: <i>{2:.3f}%</i>\n".format(
                    self.dump_emoji,
                    interval,
                    change * 100,
                    asset["price"][-1],
                )

        # Skip alert if change is not big enough to avoid spam
        if abs(change_biggest_delta) < (self.alert_skip_threshold / 100):
            self.logger.debug(
                "Change for asset: %s on all intervals is to low: %s. Skipping this alert report.",
                asset["symbol"],
                change_biggest_delta,
            )
            return

        # Get 24h Volume if available (it's the last element in volume deque if populated)
        vol = asset["volume"][-1] if len(asset["volume"]) > 0 else 0
        
        # Calculate RSI
        rsi = ConversionUtils.calculate_rsi(asset["price"])
        rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
        
        news_message = """\
<b>{0}</b> | {1} Alert(s) | {2}

Price: <i>{3:.10f}</i> | 24h Vol: <i>{4:.2f}</i> | RSI(14): <i>{5}</i>

{6}
<a href="https://www.binance.com/en/trade/{0}?type=spot">Open in Binance App</a>\
            """.format(
            asset["symbol"],
            no_of_alerts,
            datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S"),
            asset["price"][-1],
            vol,
            rsi_str,
            message,
        )

        await self.telegram.send_news_message(news_message)

    async def send_top_pump_dump_statistics_report(
        self,
        assets,
        interval,
        top_pump_enabled=True,
        top_dump_enabled=True,
        additional_stats_enabled=True,
        no_of_reported_coins=5,
    ):

        if not top_pump_enabled or not top_dump_enabled:
            return

        message = "<b>[{0} Interval]</b>\n\n".format(interval)

        if top_pump_enabled:
            pump_sorted_list = sorted(
                assets,
                key=lambda item: item[interval]["change_current"],
                reverse=True,
            )[0:no_of_reported_coins]

            message += "{0} <b>Top {1} Pumps</b>\n".format(
                self.pump_emoji, no_of_reported_coins
            )

            for asset in pump_sorted_list:
                message += "- {0}: <i>{1:.2f}</i>%\n".format(
                    asset["symbol"], asset[interval]["change_current"] * 100
                )
            message += "\n"

        if top_dump_enabled:
            dump_sorted_list = sorted(
                assets, key=lambda item: item[interval]["change_current"]
            )[0:no_of_reported_coins]

            message += "{0} <b>Top {1} Dumps</b>\n".format(
                self.dump_emoji, no_of_reported_coins
            )

            for asset in dump_sorted_list:
                message += "- {0}: <i>{1:.2f}</i>%\n".format(
                    asset["symbol"], asset[interval]["change_current"] * 100
                )

        if additional_stats_enabled:
            if top_pump_enabled or top_dump_enabled:
                message += "\n"
            message += self.generate_additional_statistics_report(assets, interval)

        await self.telegram.send_report_message(message, is_alert_chat=True)

    def generate_additional_statistics_report(self, assets, interval):
        up = 0
        down = 0
        sum_change = 0

        for asset in assets:
            if asset[interval]["change_current"] > 0:
                up += 1
            elif asset[interval]["change_current"] < 0:
                down += 1

            sum_change += asset[interval]["change_current"]

        avg_change = sum_change / len(assets)

        return "<b>Average Change:</b> {0:.2f}%\n {1} {2} / {3} {4}".format(
            avg_change * 100,
            self.pump_emoji,
            up,
            self.dump_emoji,
            down,
        )
