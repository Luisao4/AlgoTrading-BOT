import mysql.connector
import pandas as pd
import requests
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import time
from decimal import Decimal
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

COINGECKO_API_URL_PRO = "https://pro-api.coingecko.com/api/v3"
API_KEY = os.getenv("COINGECKO_API_KEY")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

# Create a SQLAlchemy engine
def create_db_engine():
    db_url = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    return create_engine(db_url)

# Database Functions
def fetch_tokens_from_db():
    """Fetch tokens from database using SQLAlchemy"""
    engine = create_db_engine()
    query = "SELECT id, name FROM Base_tokens"
    df = pd.read_sql(query, engine)
    return {row['id']: row['name'] for _, row in df.iterrows()}

def fetch_latest_timestamp_from_db(token_id):
    """Fetch the latest timestamp for a token from the database"""
    engine = create_db_engine()
    query = text('''
        SELECT MAX(timestamp) AS latest_timestamp 
        FROM Historical_Prices 
        WHERE token_id = :token_id
    ''')
    with engine.connect() as conn:
        result = conn.execute(query, {"token_id": token_id}).fetchone()
        return result[0] if result[0] else None

def fetch_coingecko_ohlc(token_id, from_timestamp):
    """Fetch OHLC data from CoinGecko API"""
    if not API_KEY:
        #print("CoinGecko API key missing. Skipping fetch.")
        return []
    try:
        to_timestamp = int(datetime.now().timestamp())  # Current time as the end timestamp
        response = requests.get(
            f"{COINGECKO_API_URL_PRO}/coins/{token_id}/ohlc/range?vs_currency=usd&from={from_timestamp}&to={to_timestamp}&interval=daily",
            headers={
                "accept": "application/json",
                "x-cg-pro-api-key": API_KEY
            },
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        #print(f"API error for {token_id}: {str(e)}")
        return []

def save_ohlc_to_db(token_id, data):
    """Save OHLC data to database with batch insert"""
    try:
        engine = create_db_engine()
        with engine.connect() as conn:
            # Prepare data for insertion
            insert_data = []
            for row in data:
                timestamp = int(row[0] / 1000)  # Convert from milliseconds to seconds
                open_price = float(row[1])
                high_price = float(row[2])
                low_price = float(row[3])
                close_price = float(row[4])
                insert_data.append({
                    "token_id": token_id,
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price
                })

            # Insert data into the database
            conn.execute(
                text('''
                    INSERT INTO Historical_Prices 
                    (token_id, timestamp, open, high, low, close)
                    VALUES (:token_id, :timestamp, :open, :high, :low, :close)
                    ON DUPLICATE KEY UPDATE
                        open = VALUES(open),
                        high = VALUES(high),
                        low = VALUES(low),
                        close = VALUES(close)
                '''),
                insert_data
            )
            
            # Explicitly commit the transaction
            conn.commit()
            #print(f"Transaction committed for {token_id}.")
        
        #print(f"Saved {len(insert_data)} OHLC records for {token_id}")
    except Exception as e:
        #print(f"Database save error: {str(e)}")
        import traceback
        #traceback.print_exc()
        pass
    finally:
        if 'conn' in locals(): conn.close()

def main():
    # 1. Fetch tokens from the database
    tokens = fetch_tokens_from_db()
    if not tokens:
        #print("No tokens found in the database. Exiting.")
        return

    # 2. Process each token
    for token_id, name in tokens.items():
        #print(f"\nProcessing token: {name} ({token_id})")

        # Fetch the latest timestamp from the database
        latest_timestamp = fetch_latest_timestamp_from_db(token_id)
        #if latest_timestamp:
        #    print(f"Latest timestamp in database for {name}: {latest_timestamp}")
        #else:
        #    print(f"No data found in database for {name}. Fetching last 180 days of data.")

        # Calculate the start time for the API request
        from_timestamp = latest_timestamp if latest_timestamp else int((datetime.now() - timedelta(days=180)).timestamp())
        #print(f"Fetching data from timestamp: {from_timestamp}")

        # Fetch OHLC data from the API
        ohlc_data = fetch_coingecko_ohlc(token_id, from_timestamp)
        if not ohlc_data:
            #print(f"No OHLC data found for {name}. Skipping.")
            continue

        # Save OHLC data to the database
        save_ohlc_to_db(token_id, ohlc_data)

if __name__ == "__main__":
    main()