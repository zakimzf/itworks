import logging
import asyncio
import json
import aiohttp
from collections import deque
from time import time
from utils import ConversionUtils

class BinancePumpAndDumpAlerter:
    def __init__(
        self,
        api_url,
        watchlist,
        blacklist,
        pairs_of_interest,
        chart_intervals,
        outlier_intervals,
        top_report_intervals,
        extract_interval,
        retry_interval,
        reset_interval,
        top_pump_enabled,
        top_dump_enabled,
        additional_statistics_enabled,
        no_of_reported_coins,
        dump_enabled,
        check_new_listing_enabled,
        top_report_nearest_hour,
        telegram,
        report_generator,
    ):
        self.api_url = api_url
        self.watchlist = [x.upper() for x in watchlist]
        self.blacklist = [x.upper() for x in blacklist]
        self.pairs_of_interest = [x.upper() for x in pairs_of_interest]
        self.outlier_intervals = outlier_intervals
        self.extract_interval = extract_interval
        self.retry_interval = retry_interval
        self.reset_interval = reset_interval
        self.top_pump_enabled = top_pump_enabled
        self.top_dump_enabled = top_dump_enabled
        self.additional_statistics_enabled = additional_statistics_enabled
        self.no_of_reported_coins = no_of_reported_coins
        self.dump_enabled = dump_enabled
        self.check_new_listing_enabled = check_new_listing_enabled
        self.telegram = telegram
        self.report_generator = report_generator

        self.logger = logging.getLogger("pump-and-dump-alerter")

        self.assets = {} # Dict to store asset data: {symbol: {price: deque, ...}}
        
        # Calculate max deque size based on the largest interval needed
        max_interval_seconds = 0
        for interval in chart_intervals:
            seconds = ConversionUtils.duration_to_seconds(interval)
            if seconds > max_interval_seconds:
                max_interval_seconds = seconds
        
        # Add some buffer
        self.max_deque_len = int(max_interval_seconds / extract_interval) + 100
        self.logger.info(f"Max deque length set to {self.max_deque_len}")

        self.chart_intervals = {}
        for interval in chart_intervals:
            self.chart_intervals[interval] = {}
            self.chart_intervals[interval]["value"] = ConversionUtils.duration_to_seconds(interval)

        self.top_report_intervals = {}
        initial_time = int(time())
        nearest_hour = initial_time - (initial_time % 3600) + 3600
        
        for interval in top_report_intervals:
            self.top_report_intervals[interval] = {}
            if top_report_nearest_hour:
                self.top_report_intervals[interval]["start"] = nearest_hour
            else:
                self.top_report_intervals[interval]["start"] = initial_time
            self.top_report_intervals[interval]["value"] = ConversionUtils.duration_to_seconds(interval)

    def create_new_asset(self, symbol):
        asset = {
            "symbol": symbol, 
            "price": deque(maxlen=self.max_deque_len), 
            "volume": deque(maxlen=self.max_deque_len)
        }
        for interval in self.chart_intervals:
            asset[interval] = {
                "change_current": 0,
                "change_last": 0,
                "change_volume": 0
            }
        return asset

    def is_symbol_valid(self, symbol):
        if self.watchlist and symbol not in self.watchlist:
            return False
        if self.blacklist and symbol in self.blacklist:
            return False
        
        is_in_pairs_of_interest = False
        for pair in self.pairs_of_interest:
            if symbol.endswith(pair):
                is_in_pairs_of_interest = True
                break
        
        if not is_in_pairs_of_interest:
            return False

        for pair in self.pairs_of_interest:
            coin = symbol.replace(pair, "")
            if coin.endswith(("UP", "DOWN", "BULL", "BEAR")):
                return False
        
        return True

    async def run(self):
        # Initial fetch to populate assets
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.api_url) as response:
                    initial_data = await response.json()
                    for item in initial_data:
                        symbol = item['symbol']
                        if self.is_symbol_valid(symbol):
                            self.assets[symbol] = self.create_new_asset(symbol)
                            self.assets[symbol]['price'].append(float(item['price']))
            except Exception as e:
                self.logger.error(f"Failed to fetch initial prices: {e}")

        self.logger.info(f"Bot started. Tracking {len(self.assets)} pairs.")
        await self.telegram.send_generic_message(f"*Bot has started.* Following _{len(self.assets)}_ pairs.")

        # WebSocket Loop
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    # Using miniTicker for 1s updates for all symbols
                    ws_url = "wss://stream.binance.com:9443/ws/!miniTicker@arr"
                    self.logger.info(f"Connecting to WebSocket: {ws_url}")
                    
                    async with session.ws_connect(ws_url) as ws:
                        last_process_time = 0
                        
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                current_time = time()
                                
                                if current_time - last_process_time >= self.extract_interval:
                                    await self.process_batch(data, current_time)
                                    last_process_time = current_time
                                    
                                    # Check Top Pump/Dump reports
                                    await self.check_and_send_top_pump_dump_statistics_report(current_time)

                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                self.logger.error(f"WebSocket connection closed with exception {ws.exception()}")
                                break
            except Exception as e:
                self.logger.error(f"WebSocket error: {e}. Reconnecting in {self.retry_interval}s...")
                await asyncio.sleep(self.retry_interval)

    async def process_batch(self, data, current_time):
        # Create a map for O(1) access
        # item['q'] is Quote Asset Volume (e.g. USDT volume)
        ticker_map = {item['s']: {'price': float(item['c']), 'volume': float(item['q'])} for item in data}
        
        for symbol, asset in self.assets.items():
            if symbol in ticker_map:
                price = ticker_map[symbol]['price']
                volume = ticker_map[symbol]['volume']
                
                asset["price"].append(price)
                asset["volume"].append(volume)
                
                self.calculate_asset_change(asset)
                
                await self.report_generator.send_pump_dump_message(
                    asset,
                    self.chart_intervals,
                    self.outlier_intervals,
                    current_time,
                    self.dump_enabled,
                )
        
        # Handle new listings dynamically
        if self.check_new_listing_enabled:
            for item in data:
                symbol = item['s']
                if symbol not in self.assets and self.is_symbol_valid(symbol):
                    self.logger.info(f"New listing found: {symbol}")
                    self.assets[symbol] = self.create_new_asset(symbol)
                    self.assets[symbol]['price'].append(float(item['c']))
                    await self.report_generator.send_new_listings([symbol])

    def calculate_asset_change(self, asset):
        asset_length = len(asset["price"])
        
        for interval in self.chart_intervals:
            data_points = self.chart_intervals[interval]["value"] // self.extract_interval
            
            if data_points >= asset_length:
                continue
                
            price_current = asset["price"][-1]
            price_past = asset["price"][-1 - data_points]
            
            if price_current == 0:
                change = 0
            else:
                change = (price_current - price_past) / price_current
            
            asset[interval]["change_last"] = asset[interval]["change_current"]
            asset[interval]["change_current"] = change

    async def check_and_send_top_pump_dump_statistics_report(self, current_time):
        for interval, data in self.top_report_intervals.items():
            if current_time > data["start"] + data["value"] + 1:
                data["start"] = current_time - (current_time % ConversionUtils.duration_to_seconds(interval))
                await self.report_generator.send_top_pump_dump_statistics_report(
                    list(self.assets.values()),
                    interval,
                    self.top_pump_enabled,
                    self.top_dump_enabled,
                    self.additional_statistics_enabled,
                    self.no_of_reported_coins,
                )
