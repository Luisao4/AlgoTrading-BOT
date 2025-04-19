import pandas as pd
import numpy as np
# import plotly.graph_objects as go
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import RelativeStrength as RelativeStrength
import BOSCHOCH as BOSCHOCH
import pandas_ta as ta
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

# Database connection
db_connection_str = f'mysql+pymysql://{DB_CONFIG["user"]}:{DB_CONFIG["password"]}@{DB_CONFIG["host"]}/{DB_CONFIG["database"]}'
engine = create_engine(db_connection_str)

# Helper function for RMA
def ta_rma(series, length):
    return series.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()

# DEMA-DMI function
def dema_dmi(close, high, low, len_dema=5, adx_smoothing_len=3, di_len=5):
    demah = ta.dema(high, length=len_dema)
    demal = ta.dema(low, length=len_dema)
    u = np.diff(demah, prepend=np.nan)
    d = -np.diff(demal, prepend=np.nan)
    p = np.where((u > d) & (u > 0), u, 0)
    m = np.where((d > u) & (d > 0), d, 0)
    p = pd.Series(p, index=close.index)
    m = pd.Series(m, index=close.index)
    tr = ta.true_range(high, low, close)
    t = ta_rma(tr, di_len)
    plus = 100 * ta_rma(p, di_len) / t
    minus = 100 * ta_rma(m, di_len) / t
    plus = pd.Series(np.nan_to_num(plus), index=close.index)
    minus = pd.Series(np.nan_to_num(minus), index=close.index)
    sum_dm = plus + minus
    adx_numerator = np.abs(plus - minus) / np.where(sum_dm == 0, 1, sum_dm)
    adx_series = pd.Series(adx_numerator, index=close.index)
    adx = 100 * ta_rma(adx_series, adx_smoothing_len)
    adx_rising = adx > adx.shift(1)
    dmil = (plus > minus) & adx_rising
    dmis = minus > plus
    signal = np.where(dmil & ~dmis, 1, np.where(dmis, -1, np.nan))
    return pd.Series(signal, index=close.index).ffill()

# Relative strength function (unchanged)
def calculate_relative_strength_up_to_date(historical_data, end_timestamp):
    tokens = RelativeStrength.fetch_all_tokens()
    prices_df = pd.DataFrame()
    for token in tokens:
        df = historical_data[historical_data["token_id"] == token][["timestamp", "close"]]
        if not df.empty and len(df) >= 14:
            df.set_index("timestamp", inplace=True)
            df = df[df.index <= end_timestamp]
            prices_df[token] = df["close"]
    if prices_df.empty:
        return pd.DataFrame()
    ratio_data = {}
    ids = prices_df.columns
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            token1 = ids[i]
            token2 = ids[j]
            ratio_col = f'{token1}_to_{token2}'
            ratio_data[ratio_col] = prices_df[token1] / prices_df[token2]
    ratio_df = pd.DataFrame(ratio_data, index=prices_df.index)
    ratio_trend_data = {}
    for col in ratio_df.columns:
        ratio_prices = ratio_df[[col]].copy()
        ratio_prices.columns = ['close']
        ratio_prices['Signal'] = RelativeStrength.calculate_rsi_ema_trend(ratio_prices['close'])
        ratio_trend_data[col] = ratio_prices['Signal']
    ratio_trend_df = pd.DataFrame(ratio_trend_data, index=ratio_df.index).dropna(how='all')
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
    num_columns = relative_strength_df.shape[1]
    relative_strength_df = (relative_strength_df / num_columns) * 100
    return relative_strength_df.fillna(0).astype(int)

# Backtest function
def run_backtest():
    # Define backtest period: last 6 months ending March 22, 2025
    end_date = datetime(2025, 3, 22)
    start_date = end_date - timedelta(days=180)
    print(f"Backtesting from {start_date} to {end_date}")

    # Fetch all historical price data
    query = "SELECT token_id, timestamp, open, high, low, close FROM Historical_Prices"
    historical_data = pd.read_sql(query, engine)
    historical_data["timestamp"] = pd.to_datetime(historical_data["timestamp"], unit="s")

    # Fetch Bitcoin_PH data
    btc_query = "SELECT timestamp, close FROM Bitcoin_PH WHERE btc_id = 'bitcoin'"
    btc_data = pd.read_sql(btc_query, engine)
    btc_data["timestamp"] = pd.to_datetime(btc_data["timestamp"], unit="s")
    btc_data = btc_data[(btc_data["timestamp"].dt.date >= start_date.date()) & 
                        (btc_data["timestamp"].dt.date <= end_date.date())]
    btc_data = btc_data.sort_values("timestamp")

    # Calculate buy-and-hold Bitcoin equity
    initial_balance = 1000
    btc_equity_curve = []
    btc_timestamps = []
    if not btc_data.empty:
        btc_initial_price = btc_data["close"].iloc[0]
        btc_shares = initial_balance / btc_initial_price
        btc_equity_curve = [btc_shares * close for close in btc_data["close"]]
        btc_timestamps = btc_data["timestamp"]
    else:
        print("Warning: No Bitcoin_PH data available for the period.")

    # Get unique dates in the data
    unique_dates = sorted(historical_data["timestamp"].dt.date.unique())
    backtest_dates = [d for d in unique_dates if start_date.date() <= d <= end_date.date()]
    if not backtest_dates:
        raise ValueError("No data available for the backtest period.")

    # Initialize portfolio
    balance = initial_balance
    portfolio = {}  # token_id: {'shares': float, 'entry_price': float, 'entry_date': date}
    equity_curve = []
    timestamps = []
    MAX_POSITIONS = 3

    # Simulate day-by-day backtest
    for idx, current_date in enumerate(backtest_dates):
        current_timestamp = pd.Timestamp(current_date).replace(hour=23, minute=59, second=59)
        print(f"Processing {current_date}")

        # Step 1: Calculate pre-trade equity (using previous day's close)
        pre_trade_equity = balance
        if idx > 0:  # Skip first day as no previous data
            prev_timestamp = pd.Timestamp(backtest_dates[idx - 1]).replace(hour=23, minute=59, second=59)
            historical_prev = historical_data[historical_data["timestamp"] <= prev_timestamp]
            for token_id in portfolio:
                token_data = historical_prev[historical_prev["token_id"] == token_id]
                if not token_data.empty:
                    prev_close = token_data["close"].iloc[-1]
                    pre_trade_equity += portfolio[token_id]["shares"] * prev_close

        # Step 2: Calculate relative strength and get top 3 tokens
        historical_up_to_date = historical_data[historical_data["timestamp"] <= current_timestamp]
        if historical_up_to_date.empty:
            equity_curve.append(pre_trade_equity if idx > 0 else balance)
            timestamps.append(current_timestamp)
            continue

        rs_df = calculate_relative_strength_up_to_date(historical_up_to_date, current_timestamp)
        if rs_df.empty:
            equity_curve.append(pre_trade_equity if idx > 0 else balance)
            timestamps.append(current_timestamp)
            continue

        todays_data = rs_df.iloc[-1]
        top_tokens = todays_data.sort_values(ascending=False).head(MAX_POSITIONS).index.tolist()

        # Step 3: Close positions not in top 3 (swapping logic)
        current_positions = set(portfolio.keys())
        desired_positions = set(top_tokens)
        for token_id in current_positions - desired_positions:
            if token_id in portfolio:
                token_data = historical_up_to_date[historical_up_to_date["token_id"] == token_id]
                if not token_data.empty:
                    token_data = token_data.sort_values("timestamp").reset_index(drop=True)
                    exit_price = token_data["open"].iloc[-1]
                    shares = portfolio[token_id]["shares"]
                    balance += shares * exit_price
                    print(f"Swapped out {token_id} at ${exit_price:.8f} on {current_date}")
                    del portfolio[token_id]

        # Step 4: Evaluate signals and manage up to 3 positions
        entry_occurred = False
        for token_id in top_tokens:
            token_data = historical_up_to_date[historical_up_to_date["token_id"] == token_id]
            if token_data.empty or len(token_data) < 2:
                continue
            token_data = token_data.sort_values("timestamp").reset_index(drop=True)
            signal = dema_dmi(token_data["close"], token_data["high"], token_data["low"])
            i = len(token_data) - 1
            previous_signal = signal.iloc[i-1] if i > 0 else np.nan
            latest_close = token_data["close"].iloc[i]

            # Calculate CHOCH
            ohlc = token_data[["open", "high", "low", "close"]]
            swing_data = BOSCHOCH.MarketStructure.swing_highs_lows(ohlc, swing_length=1)
            choch_data = BOSCHOCH.MarketStructure.bos_choch(ohlc, swing_data, close_break=True)
            latest_choch = choch_data["CHOCH"].iloc[i]

            # Determine action
            if token_id in portfolio:
                if previous_signal == -1 or latest_choch == -1:
                    exit_price = token_data["open"].iloc[i]
                    shares = portfolio[token_id]["shares"]
                    balance += shares * exit_price
                    print(f"Exited {token_id} at ${exit_price:.8f} on {current_date} (Exit Signal)")
                    del portfolio[token_id]
            else:
                if (previous_signal == 1 and pd.isna(latest_choch)) or (latest_choch == 1 and previous_signal == 1):
                    if len(portfolio) < MAX_POSITIONS:
                        entry_price = token_data["open"].iloc[i]
                        shares = (balance / (MAX_POSITIONS - len(portfolio))) / entry_price
                        portfolio[token_id] = {
                            "shares": shares,
                            "entry_price": entry_price,
                            "entry_date": current_date
                        }
                        balance -= shares * entry_price
                        print(f"Entered {token_id} at ${entry_price:.8f} on {current_date}")
                        entry_occurred = True

        # Step 5: Update equity curve
        # On entry day, equity stays flat (pre-trade value); otherwise, use current day's close
        if entry_occurred and idx > 0:
            equity_curve.append(pre_trade_equity)
        else:
            daily_equity = balance
            for token_id in portfolio:
                token_data = historical_up_to_date[historical_up_to_date["token_id"] == token_id]
                if not token_data.empty:
                    latest_close = token_data["close"].iloc[-1]
                    daily_equity += portfolio[token_id]["shares"] * latest_close
            equity_curve.append(daily_equity if idx > 0 else balance)  # Use balance for first day
        timestamps.append(current_timestamp)

    # Final equity calculation
    final_balance = balance
    for token_id in portfolio:
        token_data = historical_data[historical_data["token_id"] == token_id]
        if not token_data.empty:
            final_price = token_data["close"].iloc[-1]
            final_balance += portfolio[token_id]["shares"] * final_price
    print(f"Final Portfolio Balance: ${final_balance:.2f}")

    # Plot equity curves
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=equity_curve,
        mode="lines",
        name="Base RS Strategy Equity (3 Positions)",
        line=dict(color="red")
    ))
    if btc_equity_curve:
        fig.add_trace(go.Scatter(
            x=btc_timestamps,
            y=btc_equity_curve,
            mode="lines",
            name="Buy-and-Hold Bitcoin",
            line=dict(color="orange")
        ))
    fig.update_layout(
        title="Equity Curve: Base Relative Strength Strategy (3 Positions) vs. Buy-and-Hold Bitcoin (Initial Balance: $1000)",
        xaxis_title="Date",
        yaxis_title="Equity ($)",
        xaxis_rangeslider_visible=False
    )
    fig.show()
    """

if __name__ == "__main__":
    run_backtest()