import yfinance as yf
import sqlite3

def save_to_db(df, table_name):
    conn = sqlite3.connect("../database/trading.db")
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    conn.close()
    print(f"Saved {len(df)} rows to {table_name}")

# ---------------------------------------------
# 🟡 Download Daily Gold (XAUUSD) Data
# ---------------------------------------------
gold_daily = yf.download("GC=F", interval="1d", period="5y")
gold_daily.reset_index(inplace=True)
gold_daily.rename(columns={
    "Date":"date",
    "Open":"open",
    "High":"high",
    "Low":"low",
    "Close":"close",
    "Volume":"volume"
}, inplace=True)

save_to_db(gold_daily, "gold_daily")

# ---------------------------------------------
# 🔵 Download 1-Hour Gold Data (H1)
# ---------------------------------------------
gold_h1 = yf.download("GC=F", interval="1h", period="730d")   # 2 years of H1 data
gold_h1.reset_index(inplace=True)
gold_h1.rename(columns={
    "Datetime":"date",
    "Open":"open",
    "High":"high",
    "Low":"low",
    "Close":"close",
    "Volume":"volume"
}, inplace=True)

save_to_db(gold_h1, "gold_h1")

# ---------------------------------------------
# 🟢 Download 15-Min Gold Data (M15)
# ---------------------------------------------
gold_m15 = yf.download("GC=F", interval="15m", period="60d")  # 2 months of 15m data
gold_m15.reset_index(inplace=True)
gold_m15.rename(columns={
    "Datetime":"date",
    "Open":"open",
    "High":"high",
    "Low":"low",
    "Close":"close",
    "Volume":"volume"
}, inplace=True)

save_to_db(gold_m15, "gold_m15")