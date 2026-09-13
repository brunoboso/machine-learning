"""
Poloniex data download and caching module.
Handles candle data retrieval, Parquet caching, and data validation.
"""
import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple
import pyarrow as pa
import pyarrow.parquet as pq

from config import DEFAULT_CONFIG, TIMEFRAME_SECONDS, TIMEFRAME_TO_POLONIEX


class PoloniexDataDownloader:
    """Download and cache Poloniex SPOT market data."""
    
    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG
        self.api_base = self.config.market.api_base
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PoloniexBacktester/1.0'
        })
        
        # Ensure data directories exist
        Path(self.config.data_raw_path).mkdir(parents=True, exist_ok=True)
        Path(self.config.data_processed_path).mkdir(parents=True, exist_ok=True)
    
    def get_usdt_pairs(self) -> List[str]:
        """Fetch all active USDT pairs from Poloniex."""
        try:
            url = f"{self.api_base}/markets"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            markets = response.json()
            
            # Filter for USDT pairs only (SPOT market)
            usdt_pairs = []
            for market in markets:
                symbol = market.get('symbol', '')
                # Poloniex format: BTC_USDT
                if '_USDT' in symbol and market.get('state') == 'NORMAL':
                    usdt_pairs.append(symbol)
            
            print(f"Found {len(usdt_pairs)} active USDT pairs")
            return sorted(usdt_pairs)
        
        except Exception as e:
            print(f"Error fetching USDT pairs: {e}")
            # Fallback to common pairs if API fails
            return [
                'BTC_USDT', 'ETH_USDT', 'TRX_USDT', 'SOL_USDT', 
                'DOGE_USDT', 'XRP_USDT', 'ADA_USDT', 'MATIC_USDT'
            ]
    
    def download_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        max_retries: int = 3
    ) -> pd.DataFrame:
        """
        Download OHLCV candles from Poloniex.
        
        Args:
            symbol: Trading pair (e.g., 'BTC_USDT')
            timeframe: Candle timeframe (e.g., '1h', '4h')
            start_time: Start datetime (default: 12 months ago)
            end_time: End datetime (default: now)
            max_retries: Maximum retry attempts
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume, quoteVolume
        """
        if start_time is None:
            start_time = datetime.now() - timedelta(days=365)  # 12 months default
        if end_time is None:
            end_time = datetime.now()
        
        # Convert timeframe to seconds and Poloniex format
        interval_seconds = TIMEFRAME_SECONDS.get(timeframe)
        if interval_seconds is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        
        poloniex_interval = TIMEFRAME_TO_POLONIEX.get(timeframe)
        if poloniex_interval is None:
            raise ValueError(f"Unsupported Poloniex interval: {timeframe}")
        
        # Poloniex API: /markets/{symbol}/candles?interval={interval}&startTime={start}&endTime={end}
        url = f"{self.api_base}/markets/{symbol}/candles"
        
        all_candles = []
        current_start = int(start_time.timestamp())
        final_end = int(end_time.timestamp())
        
        # Poloniex may limit candles per request, fetch in chunks
        chunk_size = 500  # Conservative chunk size
        
        while current_start < final_end:
            chunk_end = min(current_start + (chunk_size * interval_seconds), final_end)
            
            params = {
                'interval': poloniex_interval,  # Use Poloniex format (e.g., HOUR_1)
                'startTime': current_start * 1000,  # Milliseconds
                'endTime': chunk_end * 1000,
                'limit': 500  # Maximum allowed
            }
            
            for attempt in range(max_retries):
                try:
                    response = self.session.get(url, params=params, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if isinstance(data, list) and len(data) > 0:
                            all_candles.extend(data)
                            print(f"  Downloaded {len(data)} candles for {symbol} {timeframe} "
                                  f"({datetime.fromtimestamp(current_start)} to {datetime.fromtimestamp(chunk_end)})")
                        
                        # Move to next chunk
                        current_start = chunk_end
                        time.sleep(0.2)  # Rate limiting
                        break
                    
                    elif response.status_code == 429:  # Rate limit
                        wait_time = 2 ** attempt
                        print(f"  Rate limited, waiting {wait_time}s...")
                        time.sleep(wait_time)
                    
                    else:
                        print(f"  Error {response.status_code}: {response.text}")
                        if attempt == max_retries - 1:
                            current_start = chunk_end  # Skip this chunk
                        time.sleep(1)
                
                except Exception as e:
                    print(f"  Request error (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:
                        current_start = chunk_end  # Skip this chunk
                    time.sleep(1)
        
        if not all_candles:
            print(f"Warning: No candles downloaded for {symbol} {timeframe}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        # Poloniex format: [low, high, open, close, amount, quantity, buyTakerAmount, buyTakerQuantity, tradeCount, ts, weightedAverage, interval, startTime, closeTime]
        # We need: timestamp, open, high, low, close, volume, quoteVolume
        df = pd.DataFrame(all_candles)
        
        # Check if response is in expected format
        if len(df.columns) >= 14:
            # Map columns correctly:
            # 0=low, 1=high, 2=open, 3=close, 4=amount(quoteVolume), 5=quantity(volume), 12=startTime
            df_clean = pd.DataFrame({
                'timestamp': df.iloc[:, 12],  # startTime
                'open': df.iloc[:, 2],
                'high': df.iloc[:, 1],
                'low': df.iloc[:, 0],
                'close': df.iloc[:, 3],
                'volume': df.iloc[:, 5],  # quantity (base currency)
                'quoteVolume': df.iloc[:, 4]  # amount (quote currency)
            })
            df = df_clean
        else:
            # Fallback if format is different
            print(f"  Warning: Unexpected response format ({len(df.columns)} columns)")
            return pd.DataFrame()
        
        # Convert types
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        for col in ['open', 'high', 'low', 'close', 'volume', 'quoteVolume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Remove duplicates
        df = df.drop_duplicates(subset=['timestamp'], keep='last')
        
        return df
    
    def validate_candles(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Tuple[pd.DataFrame, dict]:
        """
        Validate candle data and report issues.
        
        Returns:
            (cleaned_df, validation_report)
        """
        report = {
            'symbol': symbol,
            'timeframe': timeframe,
            'total_rows': len(df),
            'duplicates_removed': 0,
            'invalid_ohlc_removed': 0,
            'gaps_detected': 0,
            'missing_values': 0
        }
        
        if df.empty:
            return df, report
        
        original_len = len(df)
        
        # Check for missing values
        report['missing_values'] = df.isnull().sum().sum()
        
        # Remove rows with invalid OHLC (high < low, close outside [low, high], etc.)
        invalid_mask = (
            (df['high'] < df['low']) |
            (df['close'] > df['high']) |
            (df['close'] < df['low']) |
            (df['open'] > df['high']) |
            (df['open'] < df['low']) |
            (df['high'] <= 0) |
            (df['low'] <= 0)
        )
        
        df = df[~invalid_mask].copy()
        report['invalid_ohlc_removed'] = invalid_mask.sum()
        
        # Check for gaps in timestamps
        if len(df) > 1:
            interval_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
            time_diffs = df['timestamp'].diff().dt.total_seconds()
            expected_diff = interval_seconds
            gaps = time_diffs[time_diffs > expected_diff * 1.5]  # Allow 50% tolerance
            report['gaps_detected'] = len(gaps)
            
            if len(gaps) > 0:
                print(f"  Warning: {len(gaps)} gaps detected in {symbol} {timeframe} data")
        
        report['final_rows'] = len(df)
        
        return df, report
    
    def save_to_parquet(self, df: pd.DataFrame, symbol: str, timeframe: str) -> str:
        """Save candle data to Parquet format."""
        filename = f"{symbol}_{timeframe}.parquet"
        filepath = os.path.join(self.config.data_raw_path, filename)
        
        # Add metadata
        df = df.copy()
        df.attrs['symbol'] = symbol
        df.attrs['timeframe'] = timeframe
        df.attrs['downloaded_at'] = datetime.now().isoformat()
        
        # Save with compression
        df.to_parquet(filepath, engine='pyarrow', compression='snappy', index=False)
        
        print(f"  Saved to {filepath}")
        return filepath
    
    def load_from_parquet(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load candle data from Parquet cache."""
        filename = f"{symbol}_{timeframe}.parquet"
        filepath = os.path.join(self.config.data_raw_path, filename)
        
        if not os.path.exists(filepath):
            return None
        
        try:
            df = pd.read_parquet(filepath, engine='pyarrow')
            print(f"  Loaded from cache: {filepath}")
            return df
        except Exception as e:
            print(f"  Error loading cache: {e}")
            return None
    
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        force_download: bool = False
    ) -> pd.DataFrame:
        """
        Get candles (from cache or download).
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            start_time: Start datetime
            end_time: End datetime
            force_download: Force re-download even if cached
        
        Returns:
            DataFrame with validated candle data
        """
        print(f"\nFetching {symbol} {timeframe}...")
        
        # Try cache first
        if not force_download:
            df = self.load_from_parquet(symbol, timeframe)
            if df is not None and len(df) > 0:
                # Check if cache covers requested range
                cache_start = df['timestamp'].min()
                cache_end = df['timestamp'].max()
                
                if start_time is None or cache_start <= start_time:
                    if end_time is None or cache_end >= end_time:
                        print(f"  Using cached data ({len(df)} candles)")
                        return df
        
        # Download fresh data
        df = self.download_candles(symbol, timeframe, start_time, end_time)
        
        if df.empty:
            return df
        
        # Validate
        df, report = self.validate_candles(df, symbol, timeframe)
        
        # Save to cache
        if len(df) > 0:
            self.save_to_parquet(df, symbol, timeframe)
        
        return df
    
    def compute_24h_volume(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        Compute rolling 24h quote volume for liquidity filtering.
        
        ASSUMPTION: Uses rolling sum of quoteVolume over 24h worth of bars.
        If quoteVolume not available, approximates as volume * close.
        """
        df = df.copy()
        
        # Determine number of bars in 24h
        interval_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
        bars_per_24h = int(86400 / interval_seconds)
        
        # Use quoteVolume if available, else approximate
        if 'quoteVolume' in df.columns and df['quoteVolume'].notna().any():
            volume_col = df['quoteVolume']
        else:
            print(f"  Warning: quoteVolume not available, approximating as volume * close")
            volume_col = df['volume'] * df['close']
        
        # Rolling 24h sum
        df['volume_24h'] = volume_col.rolling(window=bars_per_24h, min_periods=1).sum()
        
        return df


def download_all_pairs(
    timeframes: List[str],
    months_history: int = 12,
    force_download: bool = False,
    min_volume: float = 10_000_000.0
) -> dict:
    """
    Download all USDT pairs for specified timeframes.
    
    Returns:
        dict mapping (symbol, timeframe) -> DataFrame
    """
    downloader = PoloniexDataDownloader()
    
    # Get all USDT pairs
    pairs = downloader.get_usdt_pairs()
    print(f"\nDownloading {len(pairs)} USDT pairs for {len(timeframes)} timeframes...")
    print(f"History: {months_history} months")
    
    start_time = datetime.now() - timedelta(days=30 * months_history)
    end_time = datetime.now()
    
    data_dict = {}
    
    for symbol in pairs:
        for timeframe in timeframes:
            try:
                df = downloader.get_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_time=start_time,
                    end_time=end_time,
                    force_download=force_download
                )
                
                if not df.empty:
                    # Compute 24h volume for liquidity filtering
                    df = downloader.compute_24h_volume(df, timeframe)
                    
                    # Check if meets minimum volume requirement
                    max_volume_24h = df['volume_24h'].max()
                    
                    if max_volume_24h >= min_volume:
                        data_dict[(symbol, timeframe)] = df
                        print(f"  ✓ {symbol} {timeframe}: {len(df)} candles, max 24h volume: ${max_volume_24h:,.0f}")
                    else:
                        print(f"  ✗ {symbol} {timeframe}: Below volume threshold (${max_volume_24h:,.0f} < ${min_volume:,.0f})")
                
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                print(f"  Error downloading {symbol} {timeframe}: {e}")
                continue
    
    print(f"\nSuccessfully downloaded {len(data_dict)} symbol-timeframe combinations")
    return data_dict


if __name__ == "__main__":
    # Test download for BTC_USDT
    downloader = PoloniexDataDownloader()
    
    df = downloader.get_candles(
        symbol='BTC_USDT',
        timeframe='1h',
        start_time=datetime.now() - timedelta(days=365),
        force_download=False
    )
    
    print(f"\nBTC_USDT 1h data:")
    print(f"  Rows: {len(df)}")
    print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"\nFirst 5 rows:")
    print(df.head())
    print(f"\nLast 5 rows:")
    print(df.tail())
