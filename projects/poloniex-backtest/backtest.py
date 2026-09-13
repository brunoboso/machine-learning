"""
Main backtesting engine.
Coordinates pattern detection, position management, and trade execution.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from config import DEFAULT_CONFIG, ExitReason, RejectReason
from indicators import add_all_indicators
from patterns import scan_for_setups, Setup, setup_to_dict
from portfolio import Portfolio, Position


class Backtest:
    """Backtesting engine for 1-2-3 + HiLo Activator strategy."""
    
    def __init__(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        hilo_period: int = 30,
        hilo_variant: str = 'A',
        direction: str = 'BOTH',
        setup_expiration_bars: Optional[int] = None,
        config=None
    ):
        """
        Initialize backtest.
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading pair symbol
            timeframe: Timeframe string
            hilo_period: HiLo Activator period
            hilo_variant: 'A' (direction only) or 'B' (direction + slope)
            direction: 'LONG', 'SHORT', or 'BOTH'
            setup_expiration_bars: Setup expiration in bars (None = no expiration)
            config: BacktestConfig object
        """
        self.config = config or DEFAULT_CONFIG
        self.symbol = symbol
        self.timeframe = timeframe
        self.hilo_period = hilo_period
        self.hilo_variant = hilo_variant
        self.direction = direction
        self.setup_expiration_bars = setup_expiration_bars
        
        # Prepare data with indicators
        self.df = add_all_indicators(
            df.copy(),
            hilo_period=hilo_period,
            atr_period=self.config.strategy.atr_period
        )
        
        # Scan for all setups
        self.all_setups = scan_for_setups(
            self.df,
            direction=direction,
            max_stop_percent=self.config.strategy.max_stop_percent,
            hilo_variant=hilo_variant
        )
        
        # Portfolio
        self.portfolio = Portfolio(
            initial_capital=self.config.portfolio.initial_capital,
            max_position_size=self.config.portfolio.max_position_size,
            max_positions=self.config.portfolio.max_positions,
            min_cash_reserve_pct=self.config.portfolio.min_cash_reserve_pct,
            max_exposure_pct=self.config.portfolio.max_exposure_pct,
            maker_fee_pct=self.config.costs.maker_fee_pct,
            taker_fee_pct=self.config.costs.taker_fee_pct,
            slippage_pct=0.0  # Will be set per run
        )
        
        # Tracking
        self.pending_setups: List[Setup] = []
        self.rejected_setups: List[Setup] = []
        self.expired_setups: List[Setup] = []
        self.ambiguous_intrabar_count = 0
    
    def run(self, slippage_pct: float = 0.0) -> Dict:
        """
        Run the backtest.
        
        Args:
            slippage_pct: Slippage percentage (e.g., 0.0005 for 0.05%)
        
        Returns:
            Dictionary with backtest results
        """
        # Reset portfolio for this run
        self.portfolio = Portfolio(
            initial_capital=self.config.portfolio.initial_capital,
            max_position_size=self.config.portfolio.max_position_size,
            max_positions=self.config.portfolio.max_positions,
            min_cash_reserve_pct=self.config.portfolio.min_cash_reserve_pct,
            max_exposure_pct=self.config.portfolio.max_exposure_pct,
            maker_fee_pct=self.config.costs.maker_fee_pct,
            taker_fee_pct=self.config.costs.taker_fee_pct,
            slippage_pct=slippage_pct
        )
        
        self.pending_setups = []
        self.rejected_setups = []
        self.expired_setups = []
        self.ambiguous_intrabar_count = 0
        
        # Map setups by setup_idx for quick lookup
        setup_map = {setup.setup_idx: setup for setup in self.all_setups}
        
        # Main backtest loop
        for idx in range(len(self.df)):
            current_timestamp = self.df.iloc[idx]['timestamp']
            
            # Check for exits on existing positions
            closed_positions = self.portfolio.check_exits(idx, current_timestamp, self.df)
            
            # Count ambiguous exits
            for pos in closed_positions:
                if pos.exit_reason == ExitReason.AMBIGUOUS_STOP_FIRST:
                    self.ambiguous_intrabar_count += 1
            
            # Check if a new setup arms at this bar
            if idx in setup_map:
                new_setup = setup_map[idx]
                
                # Set expiration if applicable
                if self.setup_expiration_bars is not None:
                    new_setup.expiration_idx = idx + self.setup_expiration_bars
                
                self.pending_setups.append(new_setup)
            
            # Check pending setups for entry or expiration
            for setup in self.pending_setups[:]:  # Copy to allow modification
                # Check expiration
                if setup.expiration_idx is not None and idx > setup.expiration_idx:
                    setup.expired = True
                    self.expired_setups.append(setup)
                    self.pending_setups.remove(setup)
                    continue
                
                # Check for entry trigger (must be after setup bar)
                if idx <= setup.setup_idx:
                    continue
                
                row = self.df.iloc[idx]
                entry_triggered = False
                
                if setup.direction == 'LONG':
                    # Long: price breaks above high3
                    if row['high'] >= setup.entry_price:
                        entry_triggered = True
                elif setup.direction == 'SHORT':
                    # Short: price breaks below low3
                    if row['low'] <= setup.entry_price:
                        entry_triggered = True
                
                if entry_triggered:
                    # Calculate position size
                    position_size = self.portfolio.calculate_position_size(
                        risk_usdt=setup.risk_usdt,
                        risk_based=False
                    )
                    
                    # Try to open position
                    position = self.portfolio.open_position(
                        entry_idx=idx,
                        entry_timestamp=current_timestamp,
                        symbol=self.symbol,
                        timeframe=self.timeframe,
                        direction=setup.direction,
                        entry_price=setup.entry_price,
                        stop_price=setup.stop_price,
                        target_price=setup.target_price,
                        risk_usdt=setup.risk_usdt,
                        stop_percent=setup.stop_percent,
                        position_size=position_size,
                        hilo_period=self.hilo_period,
                        hilo_variant=self.hilo_variant,
                        hilo_value=setup.hilo_value,
                        hilo_slope=setup.hilo_slope,
                        volume_24h=setup.volume_24h,
                        atr_pct=setup.atr_pct
                    )
                    
                    if position:
                        # Successfully opened position
                        self.pending_setups.remove(setup)
                    else:
                        # Could not open (insufficient capital, position limit, etc.)
                        # Keep setup pending for now (could try again next bar)
                        pass
        
        # Close any remaining positions at end of data
        if len(self.portfolio.positions) > 0:
            self.portfolio.close_all_positions(
                exit_idx=len(self.df) - 1,
                exit_timestamp=self.df.iloc[-1]['timestamp'],
                df=self.df,
                exit_reason=ExitReason.END_OF_DATA
            )
        
        # Compile results
        results = {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'hilo_period': self.hilo_period,
            'hilo_variant': self.hilo_variant,
            'direction': self.direction,
            'setup_expiration_bars': self.setup_expiration_bars,
            'slippage_pct': slippage_pct,
            'total_setups_detected': len(self.all_setups),
            'expired_setups': len(self.expired_setups),
            'trades': len(self.portfolio.closed_positions),
            'ambiguous_intrabar_count': self.ambiguous_intrabar_count,
            'final_equity': self.portfolio.equity,
            'closed_positions': self.portfolio.closed_positions,
            'data_start': self.df.iloc[0]['timestamp'],
            'data_end': self.df.iloc[-1]['timestamp'],
            'total_bars': len(self.df)
        }
        
        return results
    
    def get_trade_log(self) -> pd.DataFrame:
        """
        Get detailed trade log.
        
        Returns:
            DataFrame with all closed trades
        """
        if not self.portfolio.closed_positions:
            return pd.DataFrame()
        
        trades = []
        for pos in self.portfolio.closed_positions:
            trades.append({
                'symbol': pos.symbol,
                'timeframe': pos.timeframe,
                'hilo_period': pos.hilo_period,
                'hilo_variant': pos.hilo_variant,
                'setup_timestamp': None,  # Not tracked in Position
                'entry_timestamp': pos.entry_timestamp,
                'exit_timestamp': pos.exit_timestamp,
                'direction': pos.direction,
                'entry_price': pos.entry_price,
                'stop_price': pos.stop_price,
                'target_price': pos.target_price,
                'exit_price': pos.exit_price,
                'stop_percent': pos.stop_percent,
                'risk_usdt': pos.risk_usdt,
                'position_usdt': pos.position_size_usdt,
                'fees': pos.entry_fee + pos.exit_fee,
                'slippage': pos.entry_slippage + pos.exit_slippage,
                'gross_pnl': pos.gross_pnl,
                'net_pnl': pos.net_pnl,
                'r_multiple': pos.r_multiple,
                'exit_reason': pos.exit_reason,
                'volume_24h': pos.volume_24h,
                'atr_pct': pos.atr_pct,
                'hilo_value': pos.hilo_value,
                'hilo_slope': pos.hilo_slope,
            })
        
        return pd.DataFrame(trades)
    
    def get_setup_log(self, max_setups: int = 20) -> pd.DataFrame:
        """
        Get log of first N setups for smoke testing.
        
        Args:
            max_setups: Maximum number of setups to return
        
        Returns:
            DataFrame with setup details
        """
        setups_to_log = self.all_setups[:max_setups]
        
        setup_dicts = [
            setup_to_dict(setup, self.df, self.symbol, self.timeframe)
            for setup in setups_to_log
        ]
        
        return pd.DataFrame(setup_dicts)


def run_single_backtest(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    hilo_period: int,
    hilo_variant: str,
    direction: str = 'BOTH',
    setup_expiration_bars: Optional[int] = None,
    slippage_pct: float = 0.0,
    config=None
) -> Tuple[Dict, pd.DataFrame]:
    """
    Run a single backtest configuration.
    
    Returns:
        (results_dict, trade_log_df)
    """
    backtest = Backtest(
        df=df,
        symbol=symbol,
        timeframe=timeframe,
        hilo_period=hilo_period,
        hilo_variant=hilo_variant,
        direction=direction,
        setup_expiration_bars=setup_expiration_bars,
        config=config
    )
    
    results = backtest.run(slippage_pct=slippage_pct)
    trade_log = backtest.get_trade_log()
    
    return results, trade_log


if __name__ == "__main__":
    # Test backtest engine with synthetic data
    from download_data import PoloniexDataDownloader
    from datetime import timedelta
    
    print("Testing backtest engine...")
    
    downloader = PoloniexDataDownloader()
    df = downloader.get_candles(
        symbol='BTC_USDT',
        timeframe='1h',
        start_time=datetime.now() - timedelta(days=30),
        force_download=False
    )
    
    if not df.empty:
        results, trade_log = run_single_backtest(
            df=df,
            symbol='BTC_USDT',
            timeframe='1h',
            hilo_period=30,
            hilo_variant='A',
            direction='BOTH',
            setup_expiration_bars=5,
            slippage_pct=0.0005
        )
        
        print(f"\nBacktest results:")
        print(f"  Setups detected: {results['total_setups_detected']}")
        print(f"  Trades executed: {results['trades']}")
        print(f"  Final equity: ${results['final_equity']:.2f}")
        print(f"\nFirst 5 trades:")
        print(trade_log.head())
