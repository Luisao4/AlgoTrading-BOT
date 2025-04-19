import pandas as pd
import numpy as np
import talib as ta
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Database configuration
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

# Fetch historical price data from the database
def fetch_historical_prices(token_id):
    """Fetch historical prices for a token from the database"""
    engine = create_db_engine()
    query = text('''
        SELECT timestamp, close 
        FROM Historical_Prices 
        WHERE token_id = :token_id 
        ORDER BY timestamp
    ''')
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"token_id": token_id})
    return df

# Fetch the latest timestamp for each token
def fetch_latest_timestamps():
    """Fetch the latest timestamp for each token from the database"""
    engine = create_db_engine()
    query = text('''
        SELECT token_id, MAX(timestamp) as latest_timestamp 
        FROM Historical_Prices 
        GROUP BY token_id
    ''')
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df.set_index('token_id')['latest_timestamp'].to_dict()

# Calculate RSI and EMA trend
def calculate_rsi_ema_trend(prices):
    """Calculate RSI and EMA trend for a given price series"""
    close_array = np.asarray(prices)
    rsi = ta.RSI(close_array, timeperiod=14)
    rsi_ema = ta.EMA(rsi, timeperiod=3)
    score = np.full_like(rsi_ema, np.nan, dtype=np.float32)
    score[rsi_ema > 50] = 1
    score[rsi_ema < 50] = 0
    return score

# Fetch all tokens from the database
def fetch_all_tokens():
    """Fetch all tokens from the database"""
    engine = create_db_engine()
    query = "SELECT id, name FROM Base_tokens"
    df = pd.read_sql(query, engine)
    return df['id'].tolist()

def calculate_relative_strength():
    """Calculate relative strength for all tokens"""
    tokens = fetch_all_tokens()
    latest_timestamps = fetch_latest_timestamps()
    prices_df = pd.DataFrame()

    # Fetch historical prices for all tokens
    for token in tokens:
        df = fetch_historical_prices(token)
        if not df.empty and len(df) >= 14:  # Ensure at least 14 days of data
            df.set_index('timestamp', inplace=True)
            # Filter data up to the latest timestamp for the token
            latest_timestamp = latest_timestamps.get(token)
            if latest_timestamp:
                df = df[df.index <= latest_timestamp]
            prices_df[token] = df['close']
        #else:
        #    print(f"Skipping token {token}: insufficient data")

    # Calculate pairwise ratios
    ratio_data = {}
    ids = prices_df.columns
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            token1 = ids[i]
            token2 = ids[j]
            ratio_col = f'{token1}_to_{token2}'
            ratio_data[ratio_col] = prices_df[token1] / prices_df[token2]

    ratio_df = pd.DataFrame(ratio_data, index=prices_df.index)

    # Calculate RSI and EMA trend for each ratio
    ratio_trend_data = {}
    for col in ratio_df.columns:
        ratio_prices = ratio_df[[col]].copy()
        ratio_prices.columns = ['close']
        ratio_prices['Signal'] = calculate_rsi_ema_trend(ratio_prices['close'])
        ratio_trend_data[col] = ratio_prices['Signal']

    ratio_trend_df = pd.DataFrame(ratio_trend_data, index=ratio_df.index).dropna(how='all')

    # Split trend data into individual token contributions
    split_trend_data = {}
    i = 0
    for col in ratio_trend_df.columns:
        token1, token2 = col.split('_to_')
        split_trend_data[f'{token1}_{i}'] = ratio_trend_df[col]
        split_trend_data[f'{token2}_{i}'] = np.where(
            ratio_trend_df[col].isna(), np.nan, np.where(ratio_trend_df[col] == 0, 1, 0)
        )
        i += 1

    split_trend_df = pd.DataFrame(split_trend_data, index=ratio_trend_df.index)

    # Calculate relative strength for each token
    relative_strength_data = {}
    grouped_columns = {}

    for col in split_trend_df.columns:
        base_name = '_'.join(col.split('_')[:-1])
        if base_name not in grouped_columns:
            grouped_columns[base_name] = []
        grouped_columns[base_name].append(col)

    for base_name, cols in grouped_columns.items():
        relative_strength_data[base_name] = split_trend_df[cols].sum(axis=1, min_count=1)

    relative_strength_df = pd.DataFrame(relative_strength_data, index=split_trend_df.index)

    # Normalize relative strength to a percentage
    num_columns = relative_strength_df.shape[1]
    relative_strength_df = (relative_strength_df / num_columns) * 100
    relative_strength_df = relative_strength_df.fillna(0).astype(int)

    return relative_strength_df

# Print the top-ranked tokens based on relative strength and save top 5 token IDs to a file
def print_top_ranked_tokens():
    """Print the top-ranked tokens based on relative strength and save top 5 token IDs to a file"""
    relative_strength_df = calculate_relative_strength()
    todays_data = relative_strength_df.iloc[-1]
    todays_top_tokens = todays_data.sort_values(ascending=False).head(3)

    # Fetch token names from the database
    engine = create_db_engine()
    query = "SELECT id, name FROM Base_tokens"
    tokens_df = pd.read_sql(query, engine)

    # Merge token names with relative strength data
    todays_top_tokens_df = pd.DataFrame(todays_top_tokens).reset_index()
    todays_top_tokens_df.columns = ['Token', 'Relative Strength %']
    todays_top_tokens_df = todays_top_tokens_df.merge(tokens_df, left_on='Token', right_on='id', how='left')
    todays_top_tokens_df = todays_top_tokens_df[['name', 'Relative Strength %']]
    todays_top_tokens_df.columns = ['Token', 'Relative Strength %']

    print("Top Ranked Tokens by Relative Strength:")
    print(todays_top_tokens_df.to_string(index=False))

    # Save the top 5 token IDs to a file
    top_5_tokens = todays_top_tokens.head(5).index.tolist()
    with open('src/top_tokens.txt', 'w') as f:
        for token_id in top_5_tokens:
            f.write(f"{token_id}\n")

    #print("Top 5 token IDs saved to 'top_tokens.txt'")

# Main execution
if __name__ == "__main__":
    print_top_ranked_tokens()