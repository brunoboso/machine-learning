"""
Technical indicators for backtesting.
Primary: HiLo Activator (deterministic implementation)
"""
import pandas as pd
import numpy as np


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period, min_periods=period).mean()


def compute_hilo_activator(
    df: pd.DataFrame,
    period: int = 30
) -> pd.DataFrame:
    """
    Compute HiLo Activator indicator (deterministic, auditable).
    
    Formula:
    - up = SMA(high, period)
    - down = SMA(low, period)
    - HiLo[i] = up[i] if close[i] > HiLo[i-1] else down[i]
    
    Bootstrap: HiLo[first_valid] = down[first_valid] (ASSUMPTION: start bearish)
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        period: HiLo period
    
    Returns:
        DataFrame with added columns: 'hilo', 'hilo_up', 'hilo_down'
    """
    df = df.copy()
    
    # Compute up and down lines
    df['hilo_up'] = compute_sma(df['high'], period)
    df['hilo_down'] = compute_sma(df['low'], period)
    
    # Initialize HiLo series
    hilo = pd.Series(index=df.index, dtype=float)
    
    # Find first valid index (where both up and down are available)
    first_valid_idx = df[['hilo_up', 'hilo_down']].notna().all(axis=1).idxmax()
    
    if pd.isna(first_valid_idx) or not df.loc[first_valid_idx, 'hilo_up']:
        # No valid data
        df['hilo'] = np.nan
        return df
    
    # Bootstrap: Start with down line (ASSUMPTION documented in README)
    hilo.iloc[first_valid_idx] = df.loc[first_valid_idx, 'hilo_down']
    
    # Compute HiLo for subsequent bars
    for i in range(first_valid_idx + 1, len(df)):
        prev_hilo = hilo.iloc[i - 1]
        close = df.loc[df.index[i], 'close']
        up = df.loc[df.index[i], 'hilo_up']
        down = df.loc[df.index[i], 'hilo_down']
        
        if pd.isna(up) or pd.isna(down):
            hilo.iloc[i] = np.nan
            continue
        
        # Core logic: if close > previous HiLo, use up line; else use down line
        if close > prev_hilo:
            hilo.iloc[i] = up
        else:
            hilo.iloc[i] = down
    
    df['hilo'] = hilo
    
    return df


def compute_hilo_slope(df: pd.DataFrame, lookback: int = 1) -> pd.DataFrame:
    """
    Compute HiLo slope for Variant B filtering.
    
    Args:
        df: DataFrame with 'hilo' column
        lookback: Bars to look back for slope (default 1)
    
    Returns:
        DataFrame with 'hilo_slope' and 'hilo_slope_norm' columns
    """
    df = df.copy()
    
    # Simple slope: HiLo_t - HiLo_{t-lookback}
    df['hilo_slope'] = df['hilo'] - df['hilo'].shift(lookback)
    
    # Normalized slope (percentage change)
    df['hilo_slope_norm'] = df['hilo'].pct_change(lookback)
    
    return df


def compute_hilo_direction(df: pd.DataFrame) -> pd.DataFrame:
    """
    Determine HiLo direction (Variant A).
    
    Returns:
        DataFrame with 'hilo_direction' column: 1 (long), -1 (short), 0 (undefined)
    """
    df = df.copy()
    
    # Long if close > HiLo, short if close < HiLo
    df['hilo_direction'] = 0
    df.loc[df['close'] > df['hilo'], 'hilo_direction'] = 1
    df.loc[df['close'] < df['hilo'], 'hilo_direction'] = -1
    
    return df


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Compute Average True Range (ATR) for optional analysis.
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        period: ATR period
    
    Returns:
        DataFrame with 'atr' and 'atr_pct' columns
    """
    df = df.copy()
    
    # True Range components
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift(1)).abs()
    low_close = (df['low'] - df['close'].shift(1)).abs()
    
    # True Range = max of the three
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    # ATR = moving average of True Range
    df['atr'] = true_range.rolling(window=period, min_periods=period).mean()
    
    # ATR as percentage of close
    df['atr_pct'] = (df['atr'] / df['close']) * 100
    
    return df


def add_all_indicators(
    df: pd.DataFrame,
    hilo_period: int = 30,
    atr_period: int = 14
) -> pd.DataFrame:
    """
    Add all indicators to DataFrame.
    
    Args:
        df: DataFrame with OHLCV data
        hilo_period: HiLo Activator period
        atr_period: ATR period
    
    Returns:
        DataFrame with all indicator columns
    """
    df = compute_hilo_activator(df, period=hilo_period)
    df = compute_hilo_slope(df, lookback=1)
    df = compute_hilo_direction(df)
    df = compute_atr(df, period=atr_period)
    
    return df


if __name__ == "__main__":
    # Test with sample data
    np.random.seed(42)
    n = 100
    
    test_df = pd.DataFrame({
        'timestamp': pd.date_range('2023-01-01', periods=n, freq='1h'),
        'open': 50000 + np.random.randn(n).cumsum() * 100,
        'high': 50000 + np.random.randn(n).cumsum() * 100 + 100,
        'low': 50000 + np.random.randn(n).cumsum() * 100 - 100,
        'close': 50000 + np.random.randn(n).cumsum() * 100,
        'volume': np.random.rand(n) * 1000000,
    })
    
    # Ensure high >= low and close within range
    test_df['high'] = test_df[['open', 'close']].max(axis=1) + abs(np.random.randn(n)) * 50
    test_df['low'] = test_df[['open', 'close']].min(axis=1) - abs(np.random.randn(n)) * 50
    
    result = add_all_indicators(test_df, hilo_period=30)
    
    print("HiLo Activator test:")
    print(result[['timestamp', 'close', 'hilo', 'hilo_direction', 'hilo_slope']].tail(10))
    print(f"\nNon-null HiLo values: {result['hilo'].notna().sum()}/{len(result)}")
