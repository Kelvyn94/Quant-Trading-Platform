# backend/app/services/swing_detector.py
class SwingDetector:
    @staticmethod
    def find_swings(df):
        """
        Detect swing highs and lows in the dataframe
        """
        swings = []
        for i in range(2, len(df)-2):
            if df['high'][i] > df['high'][i-1] and df['high'][i] > df['high'][i+1]:
                swings.append({'type':'swing_high','price':df['high'][i],'index':i})
            if df['low'][i] < df['low'][i-1] and df['low'][i] < df['low'][i+1]:
                swings.append({'type':'swing_low','price':df['low'][i],'index':i})
        return swings