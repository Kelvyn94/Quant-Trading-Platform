# backend/app/services/order_block_engine.py
class OrderBlockEngine:
    @staticmethod
    def detect_order_blocks(df):
        """
        Detect bullish/bearish order blocks
        """
        order_blocks = []
        for i in range(1, len(df)-1):
            # placeholder: last opposite candle before strong impulse
            if df['close'][i] > df['open'][i] and df['close'][i+1] > df['close'][i]:
                order_blocks.append({'type':'bullish_ob','index':i})
            elif df['close'][i] < df['open'][i] and df['close'][i+1] < df['close'][i]:
                order_blocks.append({'type':'bearish_ob','index':i})
        return order_blocks