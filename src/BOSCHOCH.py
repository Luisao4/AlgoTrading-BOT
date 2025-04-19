import numpy as np
import pandas as pd
from pandas import DataFrame, Series

class MarketStructure:
    @classmethod
    def swing_highs_lows(cls, ohlc: DataFrame, swing_length: int = 1) -> DataFrame:
        """
        Non-repainting swing highs and lows using only past data.
        """
        highs = ohlc["high"]
        lows = ohlc["low"]
        
        swing_highs = highs > highs.shift(1)
        swing_lows = lows < lows.shift(1)
        
        swing_highs_lows = np.where(
            swing_highs,
            1,
            np.where(
                swing_lows,
                -1,
                np.nan,
            ),
        )

        level = np.where(
            ~np.isnan(swing_highs_lows),
            np.where(swing_highs_lows == 1, highs, lows),
            np.nan,
        )

        return pd.concat(
            [
                pd.Series(swing_highs_lows, name="HighLow"),
                pd.Series(level, name="Level"),
            ],
            axis=1,
        )

    @classmethod
    def bos_choch(cls, ohlc: DataFrame, swing_highs_lows: DataFrame, close_break: bool = True) -> DataFrame:
        """
        Non-repainting CHOCH detection using only past data.
        - Bearish CHOCH (exit): High -> Lower Low, signal at the lower low.
        - Bullish CHOCH (re-entry): High -> Lower Low -> Higher High, signal at the higher high.
        """
        swingHighLow = swing_highs_lows.copy()
        choch = np.zeros(len(ohlc), dtype=np.float64)
        level = np.zeros(len(ohlc), dtype=np.float64)

        level_order = []
        highLow_order = []
        last_positions = []

        for i in range(len(ohlc)):
            if not np.isnan(swingHighLow["HighLow"][i]):
                level_order.append(swingHighLow["Level"][i])
                highLow_order.append(swingHighLow["HighLow"][i])
                last_positions.append(i)

                # Bearish CHOCH: High -> Lower Low, signal at the lower low
                if len(level_order) >= 2:
                    if (highLow_order[-2:] == [1, -1] and 
                        level_order[-1] < level_order[-2]):
                        choch[i] = -1  # Signal at the lower low
                        level[i] = level_order[-2]  # Level is the high

                # Bullish CHOCH: High -> Lower Low -> Higher High, signal at the higher high
                if len(level_order) >= 3:
                    if (highLow_order[-3:] == [1, -1, 1] and 
                        level_order[-2] < level_order[-3] and  # Lower low
                        level_order[-1] > level_order[-3]):    # Higher high
                        choch[i] = 1  # Signal at the higher high
                        level[i] = level_order[-2]  # Level is the lower low

        choch = np.where(choch != 0, choch, np.nan)
        level = np.where(level != 0, level, np.nan)

        return pd.concat(
            [
                pd.Series(np.nan, index=ohlc.index, name="BOS"),  # BOS not used
                pd.Series(choch, name="CHOCH"),
                pd.Series(level, name="Level"),
                pd.Series(np.nan, index=ohlc.index, name="BrokenIndex"),
            ],
            axis=1,
        )