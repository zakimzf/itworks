class ConversionUtils:
    @staticmethod
    def duration_to_seconds(duration):
        unit = duration[-1]
        if unit == "s":
            unit = 1
        elif unit == "m":
            unit = 60
        elif unit == "h":
            unit = 3600

        return int(duration[:-1]) * unit

    @staticmethod
    def calculate_rsi(prices, period=14, interval_seconds=60):
        # prices is a list/deque of 1s resolution prices
        # We need to sample it to get 'interval_seconds' resolution (e.g. 1m)
        
        if len(prices) < (period + 1) * interval_seconds:
            return None
            
        # Sample prices every 'interval_seconds'
        # We take the last element, then -61, -121 etc.
        # Slicing with step: prices[::-60] gives reversed list [now, -1m, -2m...]
        # We need at least period + 1 points to calculate gains/losses
        
        sampled_prices = list(prices)[::-interval_seconds][:period+1][::-1]
        
        if len(sampled_prices) < period + 1:
            return None
            
        gains = []
        losses = []
        
        for i in range(1, len(sampled_prices)):
            change = sampled_prices[i] - sampled_prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
                
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
