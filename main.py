import src.fetch_data as fetch_data
import src.fetchOHLC as fetchOHLC
import src.RelativeStrength as RelativeStrength
import src.criteria as criteria
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

# Database connection
db_connection_str = f'mysql+pymysql://{DB_CONFIG["user"]}:{DB_CONFIG["password"]}@{DB_CONFIG["host"]}/{DB_CONFIG["database"]}'
engine = create_engine(db_connection_str)

# Forward testing variables
INITIAL_CASH = 1000
open_positions = {}
MAX_POSITIONS = 3

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration missing. Skipping message.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def initialize_portfolio():
    global open_positions
    query = "SELECT * FROM Trades WHERE status = 'OPEN'"
    with engine.connect() as conn:
        open_trades = pd.read_sql(query, conn)
    open_positions = {row['token_id']: row.to_dict() for _, row in open_trades.iterrows()}
    cash_spent = sum(row['entry_price'] * row.get('units', 100) for row in open_positions.values())  # Default to 100 if units missing
    return INITIAL_CASH - cash_spent

def update_portfolio(cash, today_date, today_datetime):
    positions_value = 0
    if open_positions:
        token_ids = ','.join(f"'{tid}'" for tid in open_positions.keys())
        query = f"SELECT token_id, close FROM Historical_Prices WHERE token_id IN ({token_ids}) AND DATE(timestamp) = '{today_date}'"
        with engine.connect() as conn:
            price_data = pd.read_sql(query, conn)
            price_dict = {row['token_id']: row['close'] for _, row in price_data.iterrows()}
        for token_id, trade in open_positions.items():
            current_price = price_dict.get(token_id, trade['entry_price'])
            units = trade.get('units', 100)  # Default to 100 if units missing
            positions_value += current_price * units
    equity = cash + positions_value
    portfolio_data = {'date': today_datetime, 'equity': equity, 'cash': cash, 'positions_value': positions_value}
    with engine.connect() as conn:
        try:
            pd.DataFrame([portfolio_data]).to_sql('Portfolio', conn, if_exists='append', index=False)
            conn.commit()
            print("Portfolio updated")
        except Exception as e:
            print(f"Error updating portfolio: {e}")
    return equity

def main():
    current_datetime = datetime.now()
    today_date = current_datetime.strftime('%Y-%m-%d')
    today_datetime = current_datetime.strftime('%Y-%m-%d %H:%M:%S')

    # Step 1: Read yesterday's top_tokens.txt
    yesterday_tokens = []
    top_tokens_file = "src/top_tokens.txt"
    if os.path.exists(top_tokens_file):
        with open(top_tokens_file, "r") as file:
            yesterday_tokens = file.read().splitlines()
    else:
        print("No previous top_tokens.txt found. Assuming first run.")
        send_telegram_message("No previous top_tokens.txt found. Assuming first run.")

    # Step 2: Fetch data and generate new top_tokens.txt
    steps = [
        ("Fetching tokens from CoinGecko...", fetch_data.main),
        ("Fetching OHLC data for today...", fetchOHLC.main),
        ("Calculating relative strength and identifying top 3 tokens...", RelativeStrength.print_top_ranked_tokens)
    ]
    for message, func in steps:
        print(message)
        send_telegram_message(message)
        func()

    # Step 3: Load today's top tokens
    try:
        with open(top_tokens_file, "r") as file:
            top_tokens = file.read().splitlines()[:MAX_POSITIONS]
    except FileNotFoundError:
        message = "Error: 'top_tokens.txt' not found. Ensure RelativeStrength.py has generated it."
        print(message)
        send_telegram_message(message)
        return

    # Step 4: Compare yesterday's and today's top tokens
    if yesterday_tokens:
        added = set(top_tokens) - set(yesterday_tokens)
        removed = set(yesterday_tokens) - set(top_tokens)
        if added or removed:
            message = f"Changes in top tokens:\nAdded: {', '.join(added)}\nRemoved: {', '.join(removed)}"
            print(message)
            send_telegram_message(message)
        else:
            message = "No changes in top tokens from yesterday."
            print(message)
            send_telegram_message(message)

    # Fetch historical data
    query = "SELECT token_id, timestamp, open, high, low, close FROM Historical_Prices"
    historical_data = pd.read_sql(query, engine)
    historical_data["timestamp"] = pd.to_datetime(historical_data["timestamp"], unit="s")

    # Evaluate trading signals and simulate trades
    message = "\nEvaluating trading signals and simulating trades for top 3 tokens..."
    print(message)
    send_telegram_message(message)

    cash = initialize_portfolio()
    equity = update_portfolio(cash, today_date, today_datetime)  # Get current equity
    cash_per_position = equity / MAX_POSITIONS  # Allocate 33% of current equity

    # Manage portfolio
    current_positions = set(open_positions.keys())
    desired_positions = set(top_tokens)

    # Close positions not in top_tokens
    with engine.connect() as conn:
        for token_id in current_positions - desired_positions:
            if token_id in open_positions:
                trade = open_positions[token_id]
                price_data = pd.read_sql(f"SELECT open, close FROM Historical_Prices WHERE token_id = '{token_id}' AND DATE(timestamp) = '{today_date}'", conn)
                if not price_data.empty:
                    exit_price = price_data['open'].iloc[-1]
                    units = trade.get('units', 100)  # Default to 100 if units missing
                    profit_loss = (exit_price - trade['entry_price']) * units
                    try:
                        conn.execute(
                            text("""
                                UPDATE Trades
                                SET exit_date = :exit_date, exit_price = :exit_price,
                                    profit_loss = :profit_loss, status = 'CLOSED'
                                WHERE trade_id = :trade_id
                            """),
                            {'exit_date': today_datetime, 'exit_price': exit_price,
                             'profit_loss': profit_loss, 'trade_id': trade['trade_id']}
                        )
                        conn.commit()
                        print(f"Trade closed for {token_id}")
                    except Exception as e:
                        print(f"Error closing trade for {token_id}: {e}")
                    cash += exit_price * units
                    del open_positions[token_id]
                    message = f"Closed LONG trade for {token_id}: Profit/Loss = ${profit_loss:.2f}\n"
                    print(message)
                    send_telegram_message(message)

    # Evaluate and open new positions
    with engine.connect() as conn:
        for token_id in top_tokens:
            token_data = historical_data[historical_data["token_id"] == token_id].copy()
            if token_data.empty or len(token_data) < 2:
                message = f"No data available for {token_id}. Skipping."
                print(message)
                send_telegram_message(message)
                continue

            token_data = token_data.sort_values("timestamp").reset_index(drop=True)
            latest_data = token_data.iloc[-1]
            previous_data = token_data.iloc[-2]

            latest_timestamp = latest_data['timestamp'].strftime('%Y-%m-%d %H:%M')
            signal = criteria.dema_dmi(token_data["close"], token_data["high"], token_data["low"])
            previous_signal = signal.iloc[-2]
            latest_choch = criteria.BOSCHOCH.MarketStructure.bos_choch(
                token_data[["open", "high", "low", "close"]], 
                criteria.BOSCHOCH.MarketStructure.swing_highs_lows(token_data[["open", "high", "low", "close"]], swing_length=1),
                close_break=True
            )["CHOCH"].iloc[-1]

            position = "NO POSITION"
            if previous_signal == 1 and pd.isna(latest_choch):
                position = "LONG"
            elif latest_choch == -1:
                position = "EXIT (Bearish CHOCH)"
            elif latest_choch == 1 and previous_signal == 1:
                position = "LONG (Bullish CHOCH Re-entry)"
            elif previous_signal == -1:
                position = "EXIT"

            token_name = pd.read_sql(f"SELECT name FROM Base_tokens WHERE id = '{token_id}'", conn)["name"].iloc[0] if not pd.read_sql(f"SELECT name FROM Base_tokens WHERE id = '{token_id}'", conn).empty else token_id

            trade_message = ""
            if token_id in open_positions:
                if position.startswith("EXIT"):
                    trade = open_positions[token_id]
                    exit_price = latest_data['open']
                    units = trade.get('units', 100)  # Default to 100 if units missing
                    profit_loss = (exit_price - trade['entry_price']) * units
                    try:
                        conn.execute(
                            text("""
                                UPDATE Trades
                                SET exit_date = :exit_date, exit_price = :exit_price,
                                    profit_loss = :profit_loss, status = 'CLOSED'
                                WHERE trade_id = :trade_id
                            """),
                            {'exit_date': today_datetime, 'exit_price': exit_price,
                             'profit_loss': profit_loss, 'trade_id': trade['trade_id']}
                        )
                        conn.commit()
                        print(f"Trade closed for {token_id}")
                    except Exception as e:
                        print(f"Error closing trade for {token_id}: {e}")
                    cash += exit_price * units
                    del open_positions[token_id]
                    trade_message = f"Closed LONG trade: Profit/Loss = ${profit_loss:.2f}\n"
            elif position == "LONG" and len(open_positions) < MAX_POSITIONS:
                entry_price = latest_data['open']
                units = cash_per_position / entry_price  # Allocate 33% of equity
                if cash >= units * entry_price:
                    trade_data = {
                        'token_id': token_id, 'entry_date': today_datetime,
                        'entry_price': entry_price, 'position_type': 'LONG', 'status': 'OPEN',
                        'units': units  # Store dynamic units
                    }
                    try:
                        pd.DataFrame([trade_data]).to_sql('Trades', conn, if_exists='append', index=False)
                        conn.commit()
                        print(f"Trade inserted for {token_id}")
                    except Exception as e:
                        print(f"Error inserting trade for {token_id}: {e}")
                    trade_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
                    trade_data['trade_id'] = trade_id
                    open_positions[token_id] = trade_data
                    cash -= units * entry_price
                    trade_message = f"Opened LONG trade at ${entry_price:.8f} with {units:.2f} units\n"

            message = (
                f"----------------- // -----------------\n"
                f"\nToken: {token_name} ({token_id})\n"
                f"  Timestamp: {latest_timestamp}\n"
                f"  Latest Close: ${latest_data['close']:.8f}\n"
                f"  DEMA-DMI Signal (Previous Day): {previous_signal}\n"
                f"  CHOCH Signal (Today): {latest_choch}\n"
                f"  Recommended Position: {position}\n"
                f"  Trade Action: {trade_message if trade_message else 'No trade action taken'}\n"
            )
            print(message)
            send_telegram_message(message)

    # Update portfolio
    equity = update_portfolio(cash, today_date, today_datetime)
    message = f"Portfolio Equity at {today_datetime}: ${equity:.2f}"
    print(message)
    send_telegram_message(message)

if __name__ == "__main__":
    message = (
        f"----------------- // // // // // -----------------\n"
        f"\nHello boss! Here is your daily analysis:\n"
        f"Running daily script on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(message)
    send_telegram_message(message)
    main()