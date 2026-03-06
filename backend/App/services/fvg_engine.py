# backend/app/services/fvg_engine.py
class FVGEngine:
    @staticmethod
    def detect_fvg(df):
        """
        Detect bullish/bearish FVG zones
        """
        fvg_zones = []
        for i in range(1, len(df)-1):
            if df['high'][i-1] < df['low'][i+1]:
                fvg_zones.append({'type':'bullish_fvg','top':df['low'][i+1],'bottom':df['high'][i-1]})
            elif df['low'][i-1] > df['high'][i+1]:
                fvg_zones.append({'type':'bearish_fvg','top':df['low'][i+1],'bottom':df['high'][i-1]})
        return fvg_zones