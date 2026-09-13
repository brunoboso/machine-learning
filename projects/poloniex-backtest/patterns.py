"""
Pattern detection for backtesting.
Primary: 1-2-3 pattern (fully objective, auditable)
"""
import pandas as pd
import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class Setup:
    """Represents an armed 1-2-3 setup ready for entry."""
    setup_idx: int  # Index where setup armed (end of candle 3)
    direction: str  # 'LONG' or 'SHORT'
    candle1_idx: int
    candle2_idx: int
    candle3_idx: int
    entry_price: float  # Trigger price (high3 for long, low3 for short)
    stop_price: float  # Stop loss (low2 for long, high2 for short)
    target_price: float  # Target (entry + 3R for long, entry - 3R for short)
    stop_percent: float  # Abs(entry - stop) / entry * 100
    risk_usdt: float  # Abs(entry - stop)
    hilo_value: Optional[float] = None  # HiLo value at setup
    hilo_direction: Optional[int] = None  # HiLo direction at setup
    hilo_slope: Optional[float] = None  # HiLo slope at setup
    volume_24h: Optional[float] = None  # 24h volume at setup
    atr_pct: Optional[float] = None  # ATR% at setup
    
    # For expiration tracking
    expiration_idx: Optional[int] = None  # Bar index when setup expires
    expired: bool = False


def detect_123_long_setup(
    df: pd.DataFrame,
    idx: int,
    max_stop_percent: float = 5.0
) -> Optional[Setup]:
    """
    Detect LONG 1-2-3 setup at given index.
    
    Pattern: Three consecutive candles where candle2 has the lowest low.
    - low2 < low1 AND low2 < low3
    - Armed after close of candle3
    - Entry trigger = high3
    - Stop = low2
    
    Args:
        df: DataFrame with OHLCV and indicator data
        idx: Current index (candle 3)
        max_stop_percent: Maximum stop loss percentage (reject if exceeded)
    
    Returns:
        Setup object if valid pattern found, else None
    """
    # Need at least 3 candles
    if idx < 2:
        return None
    
    idx1 = idx - 2
    idx2 = idx - 1
    idx3 = idx
    
    # Get candle data
    low1 = df.loc[df.index[idx1], 'low']
    low2 = df.loc[df.index[idx2], 'low']
    low3 = df.loc[df.index[idx3], 'low']
    high3 = df.loc[df.index[idx3], 'high']
    
    # Check pattern: low2 must be lowest
    if not (low2 < low1 and low2 < low3):
        return None
    
    # Entry and stop
    entry_price = high3
    stop_price = low2
    
    # Calculate risk
    risk_usdt = abs(entry_price - stop_price)
    stop_percent = (risk_usdt / entry_price) * 100
    
    # Reject if stop too wide
    if stop_percent > max_stop_percent:
        return None
    
    # Target = entry + 3R
    target_price = entry_price + (3 * risk_usdt)
    
    # Get indicator values at setup
    hilo_value = df.loc[df.index[idx3], 'hilo'] if 'hilo' in df.columns else None
    hilo_direction = df.loc[df.index[idx3], 'hilo_direction'] if 'hilo_direction' in df.columns else None
    hilo_slope = df.loc[df.index[idx3], 'hilo_slope'] if 'hilo_slope' in df.columns else None
    volume_24h = df.loc[df.index[idx3], 'volume_24h'] if 'volume_24h' in df.columns else None
    atr_pct = df.loc[df.index[idx3], 'atr_pct'] if 'atr_pct' in df.columns else None
    
    setup = Setup(
        setup_idx=idx3,
        direction='LONG',
        candle1_idx=idx1,
        candle2_idx=idx2,
        candle3_idx=idx3,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        stop_percent=stop_percent,
        risk_usdt=risk_usdt,
        hilo_value=hilo_value,
        hilo_direction=hilo_direction,
        hilo_slope=hilo_slope,
        volume_24h=volume_24h,
        atr_pct=atr_pct
    )
    
    return setup


def detect_123_short_setup(
    df: pd.DataFrame,
    idx: int,
    max_stop_percent: float = 5.0
) -> Optional[Setup]:
    """
    Detect SHORT 1-2-3 setup at given index.
    
    Pattern: Three consecutive candles where candle2 has the highest high.
    - high2 > high1 AND high2 > high3
    - Armed after close of candle3
    - Entry trigger = low3
    - Stop = high2
    
    Args:
        df: DataFrame with OHLCV and indicator data
        idx: Current index (candle 3)
        max_stop_percent: Maximum stop loss percentage (reject if exceeded)
    
    Returns:
        Setup object if valid pattern found, else None
    """
    # Need at least 3 candles
    if idx < 2:
        return None
    
    idx1 = idx - 2
    idx2 = idx - 1
    idx3 = idx
    
    # Get candle data
    high1 = df.loc[df.index[idx1], 'high']
    high2 = df.loc[df.index[idx2], 'high']
    high3 = df.loc[df.index[idx3], 'high']
    low3 = df.loc[df.index[idx3], 'low']
    
    # Check pattern: high2 must be highest
    if not (high2 > high1 and high2 > high3):
        return None
    
    # Entry and stop
    entry_price = low3
    stop_price = high2
    
    # Calculate risk
    risk_usdt = abs(entry_price - stop_price)
    stop_percent = (risk_usdt / entry_price) * 100
    
    # Reject if stop too wide
    if stop_percent > max_stop_percent:
        return None
    
    # Target = entry - 3R
    target_price = entry_price - (3 * risk_usdt)
    
    # Get indicator values at setup
    hilo_value = df.loc[df.index[idx3], 'hilo'] if 'hilo' in df.columns else None
    hilo_direction = df.loc[df.index[idx3], 'hilo_direction'] if 'hilo_direction' in df.columns else None
    hilo_slope = df.loc[df.index[idx3], 'hilo_slope'] if 'hilo_slope' in df.columns else None
    volume_24h = df.loc[df.index[idx3], 'volume_24h'] if 'volume_24h' in df.columns else None
    atr_pct = df.loc[df.index[idx3], 'atr_pct'] if 'atr_pct' in df.columns else None
    
    setup = Setup(
        setup_idx=idx3,
        direction='SHORT',
        candle1_idx=idx1,
        candle2_idx=idx2,
        candle3_idx=idx3,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        stop_percent=stop_percent,
        risk_usdt=risk_usdt,
        hilo_value=hilo_value,
        hilo_direction=hilo_direction,
        hilo_slope=hilo_slope,
        volume_24h=volume_24h,
        atr_pct=atr_pct
    )
    
    return setup


def scan_for_setups(
    df: pd.DataFrame,
    direction: str = 'BOTH',
    max_stop_percent: float = 5.0,
    hilo_variant: str = 'A'
) -> List[Setup]:
    """
    Scan entire DataFrame for 1-2-3 setups.
    
    Args:
        df: DataFrame with OHLCV and indicator data
        direction: 'LONG', 'SHORT', or 'BOTH'
        max_stop_percent: Maximum stop loss percentage
        hilo_variant: 'A' (direction only) or 'B' (direction + slope)
    
    Returns:
        List of Setup objects
    """
    setups = []
    
    # Start from index 2 (need 3 candles for pattern)
    for idx in range(2, len(df)):
        # Detect LONG setups
        if direction in ['LONG', 'BOTH']:
            setup = detect_123_long_setup(df, idx, max_stop_percent)
            if setup:
                # Apply HiLo filter
                if hilo_variant == 'A':
                    # Variant A: direction only (must be long)
                    if setup.hilo_direction == 1:
                        setups.append(setup)
                elif hilo_variant == 'B':
                    # Variant B: direction + slope (must be long and rising)
                    if setup.hilo_direction == 1 and setup.hilo_slope > 0:
                        setups.append(setup)
                else:
                    # No HiLo filter
                    setups.append(setup)
        
        # Detect SHORT setups
        if direction in ['SHORT', 'BOTH']:
            setup = detect_123_short_setup(df, idx, max_stop_percent)
            if setup:
                # Apply HiLo filter
                if hilo_variant == 'A':
                    # Variant A: direction only (must be short)
                    if setup.hilo_direction == -1:
                        setups.append(setup)
                elif hilo_variant == 'B':
                    # Variant B: direction + slope (must be short and falling)
                    if setup.hilo_direction == -1 and setup.hilo_slope < 0:
                        setups.append(setup)
                else:
                    # No HiLo filter
                    setups.append(setup)
    
    return setups


def setup_to_dict(setup: Setup, df: pd.DataFrame, symbol: str = '', timeframe: str = '') -> dict:
    """Convert Setup object to dictionary for logging/analysis."""
    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'setup_timestamp': df.loc[df.index[setup.setup_idx], 'timestamp'] if 'timestamp' in df.columns else None,
        'candle1_timestamp': df.loc[df.index[setup.candle1_idx], 'timestamp'] if 'timestamp' in df.columns else None,
        'candle2_timestamp': df.loc[df.index[setup.candle2_idx], 'timestamp'] if 'timestamp' in df.columns else None,
        'candle3_timestamp': df.loc[df.index[setup.candle3_idx], 'timestamp'] if 'timestamp' in df.columns else None,
        'low1': df.loc[df.index[setup.candle1_idx], 'low'],
        'low2': df.loc[df.index[setup.candle2_idx], 'low'],
        'low3': df.loc[df.index[setup.candle3_idx], 'low'],
        'high1': df.loc[df.index[setup.candle1_idx], 'high'],
        'high2': df.loc[df.index[setup.candle2_idx], 'high'],
        'high3': df.loc[df.index[setup.candle3_idx], 'high'],
        'direction': setup.direction,
        'entry_price': setup.entry_price,
        'stop_price': setup.stop_price,
        'target_price': setup.target_price,
        'stop_percent': setup.stop_percent,
        'risk_usdt': setup.risk_usdt,
        'hilo_value': setup.hilo_value,
        'hilo_direction': setup.hilo_direction,
        'hilo_slope': setup.hilo_slope,
        'volume_24h': setup.volume_24h,
        'atr_pct': setup.atr_pct,
        'expired': setup.expired
    }


if __name__ == "__main__":
    # Test pattern detection
    test_data = {
        'timestamp': pd.date_range('2023-01-01', periods=10, freq='1h'),
        'open': [100, 105, 102, 98, 103, 107, 105, 110, 108, 112],
        'high': [106, 108, 103, 100, 105, 109, 108, 112, 111, 115],
        'low': [99, 104, 100, 96, 101, 105, 103, 108, 106, 110],
        'close': [105, 107, 101, 99, 104, 108, 106, 111, 109, 113],
        'hilo': [102, 103, 102, 101, 102, 104, 105, 106, 107, 108],
        'hilo_direction': [1, 1, -1, -1, 1, 1, 1, 1, 1, 1],
        'hilo_slope': [0.5, 0.3, -0.2, -0.5, 0.3, 0.5, 0.4, 0.3, 0.2, 0.1],
        'volume_24h': [1e7] * 10,
        'atr_pct': [2.0] * 10,
    }
    
    test_df = pd.DataFrame(test_data)
    
    # Scan for setups
    setups = scan_for_setups(test_df, direction='BOTH', hilo_variant='A')
    
    print(f"Found {len(setups)} setups:")
    for setup in setups:
        print(f"  {setup.direction} setup at idx {setup.setup_idx}: "
              f"entry={setup.entry_price:.2f}, stop={setup.stop_price:.2f}, "
              f"target={setup.target_price:.2f}, stop%={setup.stop_percent:.2f}")
