# backend/app/services/liquidity_engine.py
class LiquidityEngine:
    @staticmethod
    def detect_liquidity_sweep(df, swings):
        """
        Detect liquidity sweeps on candles
        """
        sweeps = []
        for s in swings:
            # placeholder: if candle wick goes beyond swing high/low
            if s['type'] == 'swing_high' and df['high'][s['index']] > s['price']:
                sweeps.append({'type':'liquidity_sweep_high','index':s['index']})
            elif s['type'] == 'swing_low' and df['low'][s['index']] < s['price']:
                sweeps.append({'type':'liquidity_sweep_low','index':s['index']})
        return sweeps