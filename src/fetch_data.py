import json
import requests
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# CoinGecko API base URL
BASE_URL = "https://pro-api.coingecko.com/api/v3"

# API key
API_KEY = os.getenv("COINGECKO_API_KEY")

# MySQL database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

# Fetch coins in a specific category
def get_coins_in_category(category_id):
    if not API_KEY:
        print("CoinGecko API key missing. Skipping fetch.")
        return None
    url = f"{BASE_URL}/coins/markets"
    headers = {"x-cg-pro-api-key": API_KEY}
    params = {
        "vs_currency": "usd",  # Target currency
        "category": category_id,  # Filter by category
        "order": "market_cap_desc",  # Sort by market cap
        "per_page": 250,  # Max results per page
        "page": 1,  # Page number
        "sparkline": False  # Exclude sparkline data
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        return None

# Check if a token should be excluded based on its name or symbol
def should_exclude_token(token):
    # Keywords to exclude
    exclude_keywords = [
        "wrapped", "bridged", "restaked", "staked", "weth", "eth", "btc", "bitcoin", "clbtc", "ezeth", "usd", "euro", "eurc"
    ]
    
    # Check if any keyword is in the token's name or symbol (case-insensitive)
    for keyword in exclude_keywords:
        if keyword in token["name"].lower() or keyword in token["symbol"].lower():
            return True
    return False

# Save filtered tokens to the MySQL database
def save_filtered_tokens_to_db(tokens):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        for token in tokens:
            # Handle null ROI
            roi = token.get("roi")
            roi_json = json.dumps(roi) if roi else None

            cursor.execute('''
                INSERT INTO Base_tokens (
                    id, symbol, name, image, current_price, market_cap, market_cap_rank,
                    fully_diluted_valuation, total_volume, high_24h, low_24h,
                    price_change_24h, price_change_percentage_24h, market_cap_change_24h,
                    market_cap_change_percentage_24h, circulating_supply, total_supply,
                    max_supply, ath, ath_change_percentage, ath_date, atl, atl_change_percentage,
                    atl_date, roi, last_updated
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON DUPLICATE KEY UPDATE
                    symbol = VALUES(symbol),
                    name = VALUES(name),
                    image = VALUES(image),
                    current_price = VALUES(current_price),
                    market_cap = VALUES(market_cap),
                    market_cap_rank = VALUES(market_cap_rank),
                    fully_diluted_valuation = VALUES(fully_diluted_valuation),
                    total_volume = VALUES(total_volume),
                    high_24h = VALUES(high_24h),
                    low_24h = VALUES(low_24h),
                    price_change_24h = VALUES(price_change_24h),
                    price_change_percentage_24h = VALUES(price_change_percentage_24h),
                    market_cap_change_24h = VALUES(market_cap_change_24h),
                    market_cap_change_percentage_24h = VALUES(market_cap_change_percentage_24h),
                    circulating_supply = VALUES(circulating_supply),
                    total_supply = VALUES(total_supply),
                    max_supply = VALUES(max_supply),
                    ath = VALUES(ath),
                    ath_change_percentage = VALUES(ath_change_percentage),
                    ath_date = VALUES(ath_date),
                    atl = VALUES(atl),
                    atl_change_percentage = VALUES(atl_change_percentage),
                    atl_date = VALUES(atl_date),
                    roi = VALUES(roi),
                    last_updated = VALUES(last_updated)
            ''', (
                token["id"],
                token["symbol"],
                token["name"],
                token["image"],
                token["current_price"],
                token["market_cap"],
                token["market_cap_rank"],
                token["fully_diluted_valuation"],
                token["total_volume"],
                token["high_24h"],
                token["low_24h"],
                token["price_change_24h"],
                token["price_change_percentage_24h"],
                token["market_cap_change_24h"],
                token["market_cap_change_percentage_24h"],
                token["circulating_supply"],
                token["total_supply"],
                token["max_supply"],
                token["ath"],
                token["ath_change_percentage"],
                token["ath_date"],
                token["atl"],
                token["atl_change_percentage"],
                token["atl_date"],
                roi_json,
                token["last_updated"]
            ))
        
        conn.commit()
    except Exception as e:
        pass
    finally:
        conn.close()

# Main function
def main():
    base_ecosystem_id = "base-ecosystem"
    coins = get_coins_in_category(base_ecosystem_id)
    
    if coins:
        filtered_tokens = []
        for token in coins:
            if not should_exclude_token(token):
                filtered_tokens.append(token)
        save_filtered_tokens_to_db(filtered_tokens)

if __name__ == "__main__":
    main()