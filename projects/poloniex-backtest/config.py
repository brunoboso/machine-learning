"""
Configuration for Poloniex SPOT backtesting system.
All parameters, constraints, and market rules in one place.
"""
from typing import List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class MarketRules:
    """Market rules and constraints for Poloniex SPOT trading."""
    
    # Only USDT pairs on SPOT market
    quote_currency: str = "USDT"
    
    # Liquidity filter: minimum 24h quote volume in USDT
    # Applied historically when possible to avoid survivorship bias
    min_24h_volume_usdt: float = 10_000_000.0
    
    # Alternative volume thresholds for complementary analysis
    volume_thresholds: List[float] = field(default_factory=lambda: [10_000_000.0, 25_000_000.0, 50_000_000.0])
    
    # Initial historical data depth
    initial_history_months: int = 12
    
    # Supported timeframes
    timeframes: List[str] = field(default_factory=lambda: ["15m", "30m", "1h", "4h"])
    
    # Poloniex API endpoints
    api_base: str = "https://api.poloniex.com"
    candles_endpoint: str = "/markets/{symbol}/candles"
    ticker_endpoint: str = "/markets/{symbol}/ticker24h"
    markets_endpoint: str = "/markets"


@dataclass
class StrategyConfig:
    """HiLo Activator + 1-2-3 Pattern strategy configuration."""
    
    # HiLo Activator periods to test
    hilo_periods: List[int] = field(default_factory=lambda: [10, 15, 20, 25, 30, 40, 50])
    
    # HiLo benchmark period for smoke test
    hilo_benchmark_period: int = 30
    
    # HiLo variants:
    # A: Direction only (close > HiLo → long, close < HiLo → short)
    # B: Direction + slope (also require HiLo_t > HiLo_{t-1} for long, etc.)
    hilo_variants: List[str] = field(default_factory=lambda: ["A", "B"])
    
    # Pattern 1-2-3 stop loss limit (reject if > max_stop_percent)
    max_stop_percent: float = 5.0
    
    # Pattern 1-2-3 risk/reward ratio
    risk_reward_ratio: float = 3.0  # Target = entry + 3*risk
    
    # Setup expiration in bars (test multiple + no expiration)
    setup_expiration_bars: List[int] = field(default_factory=lambda: [3, 5, 10, None])
    
    # ATR period for optional analysis (not mandatory filter)
    atr_period: int = 14
    
    # Trade directions to test
    directions: List[str] = field(default_factory=lambda: ["LONG", "SHORT", "BOTH"])


@dataclass
class PortfolioConfig:
    """Portfolio and position sizing rules."""
    
    # Initial capital in USDT
    initial_capital: float = 100.0
    
    # Maximum position size per trade in USDT (for main test)
    max_position_size: float = 10.0
    
    # Maximum simultaneous positions
    max_positions: int = 5
    
    # Minimum cash reserve as percentage of equity
    min_cash_reserve_pct: float = 0.50  # 50%
    
    # Maximum total exposure as percentage of equity
    max_exposure_pct: float = 0.50  # 50%
    
    # Alternative risk-based sizing (for separate analysis)
    risk_per_trade_pct: List[float] = field(default_factory=lambda: [0.005, 0.01])  # 0.5%, 1%


@dataclass
class CostConfig:
    """Trading costs: fees and slippage."""
    
    # Poloniex fee structure (conservative estimates if API unavailable)
    maker_fee_pct: float = 0.0010  # 0.10%
    taker_fee_pct: float = 0.0020  # 0.20%
    
    # Slippage scenarios (applied unfavorably on entries and exits)
    slippage_scenarios: List[float] = field(default_factory=lambda: [0.0000, 0.0005, 0.0010])  # 0%, 0.05%, 0.10%


@dataclass
class ValidationConfig:
    """Validation and anti-overfitting rules."""
    
    # In-sample / Out-of-sample split (chronological, never shuffle)
    is_split_pct: float = 0.70  # 70% in-sample, 30% out-of-sample
    
    # Walk-forward parameters
    wf_train_months: int = 6
    wf_test_months: int = 2
    
    # Minimum trades threshold for reliability
    min_trades_threshold: int = 200
    
    # Trade count warning level
    low_sample_size_threshold: int = 50


@dataclass
class BacktestConfig:
    """Complete backtesting configuration."""
    
    market: MarketRules = field(default_factory=MarketRules)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    
    # Data storage paths
    data_raw_path: str = "data/raw"
    data_processed_path: str = "data/processed"
    results_trades_path: str = "results/trades"
    results_metrics_path: str = "results/metrics"
    results_charts_path: str = "results/charts"


# Global default configuration instance
DEFAULT_CONFIG = BacktestConfig()


# Timeframe to seconds mapping for Poloniex API
TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# Timeframe to Poloniex API interval format
TIMEFRAME_TO_POLONIEX = {
    "1m": "MINUTE_1",
    "5m": "MINUTE_5",
    "15m": "MINUTE_15",
    "30m": "MINUTE_30",
    "1h": "HOUR_1",
    "2h": "HOUR_2",
    "4h": "HOUR_4",
    "6h": "HOUR_6",
    "12h": "HOUR_12",
    "1d": "DAY_1",
}


# Exit reasons (for trade logging)
class ExitReason:
    TARGET_3R = "TARGET_3R"
    STOP = "STOP"
    END_OF_DATA = "END_OF_DATA"
    AMBIGUOUS_STOP_FIRST = "AMBIGUOUS_STOP_FIRST"  # Intrabar conflict, stop wins


# Setup rejection reasons
class RejectReason:
    REJECTED_STOP_TOO_WIDE = "REJECTED_STOP_TOO_WIDE"  # Stop > 5%
    EXPIRED_SETUP = "EXPIRED_SETUP"  # Setup expired before entry
