import yfinance as yf
import sqlite3
import os

# Connect to database
conn = sqlite3.connect(os.path.join('database', 'trading.db'))
cursor = conn.cursor()

# Download Gold (symbol GC=F) historical prices
data = yf.download("GC=F", period="1y", interval="1d")
data.reset_index(inplace=True)

# Insert data into database
for _, row in data.iterrows():
    cursor.execute("""
    INSERT OR IGNORE INTO prices (date, open, high, low, close, volume)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        row['Date'].strftime('%Y-%m-%d'),
        row['Open'],
        row['High'],
        row['Low'],
        row['Close'],
        row['Volume']
    ))

conn.commit()
conn.close()

print("Gold prices populated from Yahoo Finance!")