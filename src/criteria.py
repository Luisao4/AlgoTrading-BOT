import pandas as pd
import pandas_ta as ta
import numpy as np
# import plotly.graph_objects as go
from sqlalchemy import create_engine
import src.BOSCHOCH as BOSCHOCH
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

# Fetch historical price data
query = "SELECT token_id, timestamp, open, high, low, close FROM Historical_Prices"
historical_data = pd.read_sql(query, engine)

# Fetch top tokens
with open("src/top_tokens.txt", "r") as file:
    top_tokens = file.read().splitlines()

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

# Process each token
for token_id in top_tokens:
    token_data = historical_data[historical_data["token_id"] == token_id].copy()
    token_data["timestamp"] = pd.to_datetime(token_data["timestamp"], unit="s")
    token_data = token_data.reset_index(drop=True)
    
    # Calculate DEMA-DMI signal
    token_data["signal"] = dema_dmi(token_data["close"], token_data["high"], token_data["low"])
    
    # Calculate Swing Highs/Lows and CHOCH
    ohlc = token_data[["open", "high", "low", "close"]]
    
    # Debug input data
    #print(f"\nToken {token_id} OHLC sample:")
    #print(ohlc.head(10))
    #print(f"High range: {ohlc['high'].min()} to {ohlc['high'].max()}")
    #print(f"Low range: {ohlc['low'].min()} to {ohlc['low'].max()}")
    
    # Use the MarketStructure class
    swing_data = BOSCHOCH.MarketStructure.swing_highs_lows(ohlc, swing_length=1)
    choch_data = BOSCHOCH.MarketStructure.bos_choch(ohlc, swing_data, close_break=True)
    
    # Filter CHOCH signals
    bearish_choch = choch_data[choch_data["CHOCH"] == -1]  # Exit signals
    bullish_choch = choch_data[choch_data["CHOCH"] == 1]  # Re-entry signals
    
    # Trading logic and equity curve calculation
    initial_balance = 1000  # Starting with $1000
    long_entries = []
    long_exits = []
    in_position = False
    balance = initial_balance
    shares = 0
    equity_curve = [initial_balance] * len(token_data)  # Active trading equity
    buy_hold_equity = [initial_balance] * len(token_data)  # Buy-and-hold equity

    # Buy-and-hold: Buy at first open, hold to end
    initial_price = token_data["open"].iloc[0]
    buy_hold_shares = initial_balance / initial_price
    for i in range(len(token_data)):
        buy_hold_equity[i] = buy_hold_shares * token_data["close"].iloc[i]

    # Active trading
    for i in range(len(token_data)):
        if i > 0:
            equity_curve[i] = equity_curve[i-1]  # Carry forward previous equity by default

        # Enter long on the NEXT candle after DMI signal
        if i > 0 and token_data["signal"].iloc[i-1] == 1 and not in_position:
            entry_price = token_data["open"].iloc[i]  # Enter at open of next candle
            shares = balance / entry_price
            long_entries.append((token_data["timestamp"].iloc[i], entry_price))
            in_position = True
            equity_curve[i] = balance  # Equity stays flat (cash) on entry day

        # Exit long on bearish CHOCH
        if in_position and i in bearish_choch.index:
            exit_price = token_data["open"].iloc[i]
            balance = shares * exit_price
            long_exits.append((token_data["timestamp"].iloc[i], exit_price))
            in_position = False
            equity_curve[i] = balance

        # Re-enter long on bullish CHOCH if DMI was long on previous candle
        if i > 0 and not in_position and i in bullish_choch.index and token_data["signal"].iloc[i-1] == 1:
            entry_price = token_data["open"].iloc[i]
            shares = balance / entry_price
            long_entries.append((token_data["timestamp"].iloc[i], entry_price))
            in_position = True
            equity_curve[i] = balance  # Equity stays flat on re-entry day

        # Update equity based on current close if in position (starting next candle)
        if in_position and i > 0:
            equity_curve[i] = shares * token_data["close"].iloc[i]

    # Final balance calculation
    final_balance = equity_curve[-1] if not in_position else shares * token_data["close"].iloc[-1]
    final_buy_hold = buy_hold_equity[-1]
    
    # Debugging
    #print(f"\nToken {token_id}:")
    #print(f"  Data length: {len(token_data)}")
    #print(f"  Swing points detected: {len(swing_data[~swing_data['HighLow'].isna()])}")
    #print(f"    Highs: {len(swing_data[swing_data['HighLow'] == 1])}, Lows: {len(swing_data[swing_data['HighLow'] == -1])}")
    #print(f"  Long Signals (DMI): {len(token_data[token_data['signal'] == 1])}")
    #print(f"  Bearish CHOCH: {len(bearish_choch)}")
    #if not bearish_choch.empty:
    #    print("  Bearish CHOCH indices:", bearish_choch.index.tolist())
    #print(f"  Bullish CHOCH: {len(bullish_choch)}")
    #if not bullish_choch.empty:
    #    print("  Bullish CHOCH indices:", bullish_choch.index.tolist())
    #print(f"  Long Entries: {len(long_entries)}")
    #print(f"  Long Exits: {len(long_exits)}")
    #print(f"  Final Active Trading Balance: ${final_balance:.2f}")
    #print(f"  Final Buy-and-Hold Balance: ${final_buy_hold:.2f}")
    
    # Plotting: Candlestick chart with signals
    """
    fig1 = go.Figure()
    fig1.add_trace(go.Candlestick(
        x=token_data["timestamp"],
        open=token_data["open"],
        high=token_data["high"],
        low=token_data["low"],
        close=token_data["close"],
        name="Candlesticks"
    ))
    
    # Green triangles up for long entries
    if long_entries:
        entry_times, entry_prices = zip(*long_entries)
        fig1.add_trace(go.Scatter(
            x=entry_times,
            y=entry_prices,
            mode="markers",
            marker=dict(symbol="triangle-up", size=10, color="green"),
            name="Long Entry"
        ))
    
    # Red triangles down for long exits
    if long_exits:
        exit_times, exit_prices = zip(*long_exits)
        fig1.add_trace(go.Scatter(
            x=exit_times,
            y=exit_prices,
            mode="markers",
            marker=dict(symbol="triangle-down", size=10, color="red"),
            name="Long Exit"
        ))
    
    fig1.update_layout(
        title=f"DEMA-DMI & CHOCH Trading Signals for Token {token_id}",
        xaxis_title="Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False
    )
    fig1.show()

    # Plotting: Equity curves
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=token_data["timestamp"],
        y=equity_curve,
        mode="lines",
        name="Active Trading Equity",
        line=dict(color="blue")
    ))
    fig2.add_trace(go.Scatter(
        x=token_data["timestamp"],
        y=buy_hold_equity,
        mode="lines",
        name="Buy-and-Hold Equity",
        line=dict(color="orange")
    ))
    
    fig2.update_layout(
        title=f"Equity Curves for Token {token_id} (Initial Balance: $1000)",
        xaxis_title="Time",
        yaxis_title="Equity ($)",
        xaxis_rangeslider_visible=False
    )
    fig2.show()
    """