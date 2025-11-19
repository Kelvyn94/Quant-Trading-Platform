import sqlite3
import os

# Ensure folder exists
os.makedirs('database', exist_ok=True)

# Connect to database
conn = sqlite3.connect('database/trading.db')
cursor = conn.cursor()

# Create tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS prices (
    date TEXT PRIMARY KEY,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS economic_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    currency TEXT,
    impact TEXT,
    event TEXT,
    forecast REAL,
    actual REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sentiment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    source TEXT,
    sentiment TEXT
)
""")

conn.commit()
conn.close()

print("Database and tables created successfully.")