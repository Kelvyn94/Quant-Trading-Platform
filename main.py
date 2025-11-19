from fastapi import FastAPI
from scrapers import scrape_prices
from database import db_setup, db_utils

app = FastAPI()

@app.get("/prices")
def get_prices():
    return db_utils.get_prices()

@app.on_event("startup")
def startup_event():
    db_setup.create_tables()
    scrape_prices.scrape_and_save()