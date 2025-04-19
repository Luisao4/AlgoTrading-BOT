## Overview
This Python script (`main.py`) is an algorithmic trading bot named RS-ALGOBOT. It automates trading decisions for up to three cryptocurrency tokens based on relative strength and technical indicators. The bot:
- Fetches token data from CoinGecko and OHLC (Open, High, Low, Close) prices.
- Identifies the top 3 tokens by relative strength daily.
- Allocates approximately 33% of the portfolio equity to each of the three positions dynamically.
- Uses DEMA-DMI and CHOCH signals to decide when to enter (LONG) or exit positions.
- Logs actions via console output and Telegram messages.
- Stores trade and portfolio data in a MySQL database.

Starting with an initial cash balance of $1000, the bot simulates trades and tracks portfolio equity over time.

## How It Functions
1. **Initialization**:
   - Connects to a MySQL database (`RS-ALGOBOT`) and Telegram for notifications.
   - Loads any existing open positions from the `Trades` table and calculates initial cash (`INITIAL_CASH - cash_spent`).

2. **Daily Process**:
   - **Step 1**: Reads yesterday’s top tokens from `src/top_tokens.txt` (if it exists).
   - **Step 2**: Fetches fresh data:
     - Token list from CoinGecko (`fetch_data.main()`).
     - Daily OHLC prices (`fetchOHLC.main()`).
     - Top 3 tokens by relative strength (`RelativeStrength.print_top_ranked_tokens()`), saved to `top_tokens.txt`.
   - **Step 3**: Compares today’s top tokens with yesterday’s, logging changes (added/removed tokens).
   - **Step 4**: Manages the portfolio:
     - Closes positions not in the top 3 at today’s opening price.
     - Evaluates signals for the top 3 tokens and opens new LONG positions if conditions are met.
   - **Step 5**: Updates portfolio equity and logs it.

3. **Trade Execution**:
   - Positions are opened with units calculated as `cash_per_position / entry_price`, where `cash_per_position` is 33% of the current portfolio equity.
   - Trades are recorded in the `Trades` table; portfolio updates go to the `Portfolio` table.

4. **Notifications**:
   - Prints detailed logs to the console and sends them via Telegram, including token signals, trade actions, and equity updates.

## Conditions for LONG and EXIT
The script uses two technical indicators from `src.criteria` to determine trading actions:

### 1. DEMA-DMI Signal
- **Calculation**: Combines Double Exponential Moving Average (DEMA) and Directional Movement Index (DMI) on close, high, and low prices (`criteria.dema_dmi()`).
- **Output**: Returns a signal series where:
  - `1` = Bullish (positive trend strength).
  - `-1` = Bearish (negative trend strength).
  - `0` = Neutral.
- **Usage**: Uses the previous day’s signal (`signal.iloc[-2]`) to assess trend direction.

### 2. CHOCH Signal (Change of Character)
- **Calculation**: Detects market structure shifts using `criteria.BOSCHOCH.MarketStructure.bos_choch()` with swing highs/lows (swing_length=1) and close_break=True.
- **Output**: Returns a CHOCH series where:
  - `1` = Bullish shift (potential reversal up).
  - `-1` = Bearish shift (potential reversal down).
  - `NaN` = No shift detected.
- **Usage**: Uses today’s CHOCH value (`CHOCH.iloc[-1]`) to confirm trend continuation or reversal.

### Trading Conditions
For each token in the top 3 (`top_tokens`):
- **LONG** (Enter a new position):
  - `previous_signal == 1 AND pd.isna(latest_choch)`: Bullish trend from yesterday with no reversal today.
  - `latest_choch == 1 AND previous_signal == 1`: Bullish reversal today confirming a prior bullish trend (re-entry).
  - Conditions checked only if fewer than 3 positions are open and cash is sufficient.
- **EXIT** (Close an existing position):
  - `latest_choch == -1`: Bearish reversal today (Bearish CHOCH).
  - `previous_signal == -1`: Bearish trend from yesterday.
- **NO POSITION**: Default if no LONG or EXIT condition is met (no action taken).

- **Entry**: Buys at today’s opening price (`latest_data['open']`).
- **Exit**: Sells at today’s opening price.

## Equity Curve Calculation
The equity curve represents the total portfolio value over time, stored in the `Portfolio` table and returned by `update_portfolio()`.

### Formula
**Equity = Cash + Positions_Value**

1. **Cash**:
   - Starts at `INITIAL_CASH = 1000`.
   - Decreases when opening a position: `cash -= units * entry_price`.
   - Increases when closing a position: `cash += exit_price * units`.

2. **Positions_Value**:
   - Sum of the current value of all open positions.
   - For each position: `current_price * units`.
   - `current_price` is today’s closing price (`close` from `Historical_Prices`) or the entry price if no close is available.

3. **Process**:
   - `initialize_portfolio()`: Calculates initial cash by subtracting the cost of open positions (`entry_price * units`) from `INITIAL_CASH`.
   - `update_portfolio()`: Updates equity daily:
     - Queries `Historical_Prices` for today’s closing prices of open positions.
     - Computes `positions_value` and adds it to `cash`.
     - Stores the result in the `Portfolio` table with the current timestamp.

### Notes
- **Units**: Dynamically calculated as `cash_per_position / entry_price`, where `cash_per_position = equity / 3`. For older trades without `units`, defaults to 100.
- **Equity Curve**: Plotting the `equity` column from the `Portfolio` table over time shows the portfolio’s performance.

## Requirements
- **Python Libraries**: `pandas`, `sqlalchemy`, `pymysql`, `requests`.
- **Database**: MySQL with tables:
  - `Trades`: Stores trade data (includes `units` column).
  - `Portfolio`: Stores equity history (add `id` as primary key to allow duplicate dates).
  - `Historical_Prices`: OHLC data.
  - `Base_tokens`: Token names.
- **Files**: `src/top_tokens.txt` generated daily.

## Setup
1. Install dependencies: `pip install pandas sqlalchemy pymysql requests`.
2. Ensure MySQL database `RS-ALGOBOT` is running with correct credentials.
3. Update `Portfolio` table: `ALTER TABLE Portfolio ADD COLUMN id INT AUTO_INCREMENT PRIMARY KEY;`.
4. Run: `python3 main.py`.

## Output
- Console and Telegram logs show data fetches, token changes, signal evaluations, trade actions, and equity updates.
Expected output:
![Screenshot](./response.png)
