import yfinance as yf
import sqlite3

def download_and_save(symbol, interval, period, table_name):
    print(f"Downloading {interval} -> {table_name}")
    
    df = yf.download(symbol, interval=interval, period=period)
    df.reset_index(inplace=True)
    
    # Standardize column names
    df.rename(columns={
        "Date": "date",
        "Datetime": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume"
    }, inplace=True)

    conn = sqlite3.connect("../database/trading.db")
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    conn.close()

    print(f"Saved {len(df)} rows into {table_name}")

# ---------------------------------------------
# GOLD FUTURES SYMBOL (GLOBAL)
symbol = "GC=F"

# Timeframes & periods
timeframes = [
    ("1d", "10y",   "gold_1d"),
    ("4h", "730d",  "gold_4h"),   # 2 years
    ("1h", "730d",  "gold_1h"),
    ("30m", "60d",  "gold_30m"),
    ("15m", "60d",  "gold_15m"),
    ("5m",  "30d",  "gold_5m"),
    ("1m",  "14d",  "gold_1m"),
]

# Download all TFs
for interval, period, table in timeframes:
    download_and_save(symbol, interval, period, table)