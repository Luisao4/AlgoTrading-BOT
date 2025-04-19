Base Ecosystem Relative Strength Trading Bot
This project implements a trading bot that analyzes the relative strength of tokens in the Base ecosystem, using CoinGecko data and technical indicators (DEMA-DMI, CHOCH). It simulates trades, tracks portfolio performance, and sends updates via Telegram.
Features

Fetches token data from CoinGecko for the Base ecosystem.
Calculates relative strength using RSI and EMA trends.
Applies DEMA-DMI and CHOCH signals for trading decisions.
Simulates trading with a portfolio of up to 3 positions.
Stores data in a MySQL database.
Sends trading updates to Telegram.
Includes a backtest script to evaluate strategy performance.

Prerequisites

Python 3.8+
MySQL database
CoinGecko Pro API key
Telegram bot token and chat ID (optional, for notifications)

Setup

Clone the Repository
git clone https://github.com/yourusername/your-repo.git
cd your-repo


Install DependenciesCreate a virtual environment and install required packages:
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

Required packages:
pandas
numpy
sqlalchemy
mysql-connector-python
requests
python-dotenv
pandas_ta
talib


Configure Environment VariablesCreate a .env file in the project root and add the following:
COINGECKO_API_KEY=your_coingecko_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
DB_HOST=localhost
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
DB_NAME=RS-ALGOBOT

See .env.example for reference. Do not commit the .env file to GitHub.

Set Up MySQL Database

Create a MySQL database named RS-ALGOBOT.
Create the necessary tables (Base_tokens, Historical_Prices, Trades, Portfolio, Bitcoin_PH). Schema definitions are assumed to match the queries in the code.
Ensure your MySQL user has appropriate permissions.


Run the BotExecute the main script:
python src/main.py

To run the backtest:
python src/backtest.py



Project Structure

src/main.py: Main script for running the trading bot.
src/RelativeStrength.py: Calculates relative strength for tokens.
src/fetchOHLC.py: Fetches OHLC data from CoinGecko.
src/fetch_data.py: Fetches token metadata from CoinGecko.
src/criteria.py: Applies DEMA-DMI and CHOCH trading signals.
src/BOSCHOCH.py: Implements market structure analysis (swing highs/lows, CHOCH).
src/backtest.py: Backtests the strategy over a 6-month period.
.env.example: Template for environment variables.
.gitignore: Excludes sensitive files.

Notes

The bot fetches data for the Base ecosystem (base-ecosystem category on CoinGecko).
Ensure your CoinGecko API key supports the Pro API endpoints.
Telegram notifications are optional; the bot will skip them if credentials are missing.
Plotting code (using Plotly) is commented out but can be enabled for visualization.
The backtest compares the strategy against a buy-and-hold Bitcoin benchmark.

Contributing
Feel free to open issues or submit pull requests for improvements.
License
MIT License
