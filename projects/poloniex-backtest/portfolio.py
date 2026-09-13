"""
Portfolio management and position sizing.
Handles capital allocation, risk management, and position tracking.
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from config import DEFAULT_CONFIG


@dataclass
class Position:
    """Represents an open trading position."""
    entry_idx: int
    entry_timestamp: datetime
    symbol: str
    timeframe: str
    direction: str  # 'LONG' or 'SHORT'
    entry_price: float
    stop_price: float
    target_price: float
    position_size_usdt: float
    risk_usdt: float
    stop_percent: float
    
    # Costs
    entry_fee: float = 0.0
    entry_slippage: float = 0.0
    
    # Setup metadata
    hilo_period: Optional[int] = None
    hilo_variant: Optional[str] = None
    hilo_value: Optional[float] = None
    hilo_slope: Optional[float] = None
    volume_24h: Optional[float] = None
    atr_pct: Optional[float] = None
    
    # Exit tracking
    exit_idx: Optional[int] = None
    exit_timestamp: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    exit_fee: float = 0.0
    exit_slippage: float = 0.0
    
    # P&L
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    r_multiple: float = 0.0


@dataclass
class Portfolio:
    """Portfolio state and management."""
    initial_capital: float
    equity: float = field(init=False)
    cash: float = field(init=False)
    positions: List[Position] = field(default_factory=list)
    closed_positions: List[Position] = field(default_factory=list)
    
    # Configuration
    max_position_size: float = 10.0
    max_positions: int = 5
    min_cash_reserve_pct: float = 0.50
    max_exposure_pct: float = 0.50
    
    # Fees and slippage
    maker_fee_pct: float = 0.001
    taker_fee_pct: float = 0.002
    slippage_pct: float = 0.0
    
    def __post_init__(self):
        self.equity = self.initial_capital
        self.cash = self.initial_capital
    
    def get_total_exposure(self) -> float:
        """Calculate total exposure across all open positions."""
        return sum(pos.position_size_usdt for pos in self.positions)
    
    def get_available_capital(self) -> float:
        """Calculate available capital for new positions."""
        # Must maintain minimum cash reserve
        min_cash = self.equity * self.min_cash_reserve_pct
        available = self.cash - min_cash
        
        # Must not exceed maximum exposure
        current_exposure = self.get_total_exposure()
        max_total_exposure = self.equity * self.max_exposure_pct
        exposure_room = max_total_exposure - current_exposure
        
        return max(0, min(available, exposure_room))
    
    def can_open_position(self, position_size: float) -> bool:
        """Check if we can open a new position."""
        # Check position limit
        if len(self.positions) >= self.max_positions:
            return False
        
        # Check available capital
        available = self.get_available_capital()
        if position_size > available:
            return False
        
        # Check cash reserve after opening
        if (self.cash - position_size) < (self.equity * self.min_cash_reserve_pct):
            return False
        
        return True
    
    def calculate_position_size(
        self,
        risk_usdt: float,
        risk_based: bool = False,
        risk_pct: float = 0.01
    ) -> float:
        """
        Calculate position size.
        
        Args:
            risk_usdt: Risk per trade in USDT (entry - stop)
            risk_based: If True, size based on equity risk percentage
            risk_pct: Risk percentage of equity (for risk-based sizing)
        
        Returns:
            Position size in USDT
        """
        if risk_based:
            # Risk-based sizing: position = (equity * risk_pct) / risk_per_unit
            # This is simplified; in reality needs to account for actual units
            target_risk = self.equity * risk_pct
            size = min(target_risk / risk_usdt * 100, self.max_position_size) if risk_usdt > 0 else self.max_position_size
        else:
            # Fixed position size
            size = min(self.max_position_size, self.equity * 0.10)
        
        # Ensure we have capital available
        available = self.get_available_capital()
        size = min(size, available)
        
        return max(0, size)
    
    def open_position(
        self,
        entry_idx: int,
        entry_timestamp: datetime,
        symbol: str,
        timeframe: str,
        direction: str,
        entry_price: float,
        stop_price: float,
        target_price: float,
        risk_usdt: float,
        stop_percent: float,
        position_size: float,
        **kwargs
    ) -> Optional[Position]:
        """Open a new position."""
        # Check if we can open
        if not self.can_open_position(position_size):
            return None
        
        # Calculate fees and slippage (applied unfavorably)
        entry_fee = position_size * self.taker_fee_pct  # Assume taker fee on entry
        
        if direction == 'LONG':
            # Long: buy at higher price (unfavorable)
            slippage_adjusted_price = entry_price * (1 + self.slippage_pct)
        else:
            # Short: sell at lower price (unfavorable)
            slippage_adjusted_price = entry_price * (1 - self.slippage_pct)
        
        entry_slippage = abs(slippage_adjusted_price - entry_price) * (position_size / entry_price)
        
        # Deduct from cash
        total_cost = position_size + entry_fee + entry_slippage
        if total_cost > self.cash:
            return None
        
        self.cash -= total_cost
        
        # Create position
        position = Position(
            entry_idx=entry_idx,
            entry_timestamp=entry_timestamp,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            entry_price=slippage_adjusted_price,
            stop_price=stop_price,
            target_price=target_price,
            position_size_usdt=position_size,
            risk_usdt=risk_usdt,
            stop_percent=stop_percent,
            entry_fee=entry_fee,
            entry_slippage=entry_slippage,
            **kwargs
        )
        
        self.positions.append(position)
        
        return position
    
    def close_position(
        self,
        position: Position,
        exit_idx: int,
        exit_timestamp: datetime,
        exit_price: float,
        exit_reason: str
    ) -> Position:
        """Close an existing position."""
        # Calculate fees and slippage (applied unfavorably)
        exit_fee = position.position_size_usdt * self.taker_fee_pct
        
        if position.direction == 'LONG':
            # Long exit: sell at lower price (unfavorable)
            slippage_adjusted_price = exit_price * (1 - self.slippage_pct)
        else:
            # Short exit: buy at higher price (unfavorable)
            slippage_adjusted_price = exit_price * (1 + self.slippage_pct)
        
        exit_slippage = abs(slippage_adjusted_price - exit_price) * (position.position_size_usdt / exit_price)
        
        # Calculate P&L
        if position.direction == 'LONG':
            gross_pnl = (slippage_adjusted_price - position.entry_price) / position.entry_price * position.position_size_usdt
        else:  # SHORT
            gross_pnl = (position.entry_price - slippage_adjusted_price) / position.entry_price * position.position_size_usdt
        
        net_pnl = gross_pnl - position.entry_fee - position.entry_slippage - exit_fee - exit_slippage
        
        # R-multiple
        if position.risk_usdt > 0:
            r_multiple = net_pnl / (position.risk_usdt * position.position_size_usdt / position.entry_price)
        else:
            r_multiple = 0.0
        
        # Update position
        position.exit_idx = exit_idx
        position.exit_timestamp = exit_timestamp
        position.exit_price = slippage_adjusted_price
        position.exit_reason = exit_reason
        position.exit_fee = exit_fee
        position.exit_slippage = exit_slippage
        position.gross_pnl = gross_pnl
        position.net_pnl = net_pnl
        position.r_multiple = r_multiple
        
        # Update portfolio
        self.cash += position.position_size_usdt + net_pnl
        self.equity += net_pnl
        
        # Move to closed positions
        self.positions.remove(position)
        self.closed_positions.append(position)
        
        return position
    
    def check_exits(
        self,
        current_idx: int,
        current_timestamp: datetime,
        df: pd.DataFrame
    ) -> List[Position]:
        """
        Check all open positions for exit conditions.
        
        Returns:
            List of closed positions
        """
        closed = []
        
        for position in self.positions[:]:  # Copy list to allow modification
            row = df.iloc[current_idx]
            
            high = row['high']
            low = row['low']
            close = row['close']
            
            if position.direction == 'LONG':
                # Check stop and target
                # ASSUMPTION: If both hit in same bar, stop hits first (conservative)
                if low <= position.stop_price and high >= position.target_price:
                    # Ambiguous intrabar - stop wins
                    closed_pos = self.close_position(
                        position, current_idx, current_timestamp,
                        position.stop_price, 'AMBIGUOUS_STOP_FIRST'
                    )
                    closed.append(closed_pos)
                elif low <= position.stop_price:
                    # Stop hit
                    closed_pos = self.close_position(
                        position, current_idx, current_timestamp,
                        position.stop_price, 'STOP'
                    )
                    closed.append(closed_pos)
                elif high >= position.target_price:
                    # Target hit
                    closed_pos = self.close_position(
                        position, current_idx, current_timestamp,
                        position.target_price, 'TARGET_3R'
                    )
                    closed.append(closed_pos)
            
            else:  # SHORT
                # Check stop and target
                if high >= position.stop_price and low <= position.target_price:
                    # Ambiguous intrabar - stop wins
                    closed_pos = self.close_position(
                        position, current_idx, current_timestamp,
                        position.stop_price, 'AMBIGUOUS_STOP_FIRST'
                    )
                    closed.append(closed_pos)
                elif high >= position.stop_price:
                    # Stop hit
                    closed_pos = self.close_position(
                        position, current_idx, current_timestamp,
                        position.stop_price, 'STOP'
                    )
                    closed.append(closed_pos)
                elif low <= position.target_price:
                    # Target hit
                    closed_pos = self.close_position(
                        position, current_idx, current_timestamp,
                        position.target_price, 'TARGET_3R'
                    )
                    closed.append(closed_pos)
        
        return closed
    
    def close_all_positions(
        self,
        exit_idx: int,
        exit_timestamp: datetime,
        df: pd.DataFrame,
        exit_reason: str = 'END_OF_DATA'
    ):
        """Close all open positions (e.g., at end of backtest)."""
        for position in self.positions[:]:
            close_price = df.iloc[exit_idx]['close']
            self.close_position(position, exit_idx, exit_timestamp, close_price, exit_reason)
    
    def get_equity_curve(self) -> pd.DataFrame:
        """Generate equity curve from closed positions."""
        if not self.closed_positions:
            return pd.DataFrame({'timestamp': [], 'equity': []})
        
        equity_data = [{'timestamp': None, 'equity': self.initial_capital}]
        
        for pos in self.closed_positions:
            equity_data.append({
                'timestamp': pos.exit_timestamp,
                'equity': equity_data[-1]['equity'] + pos.net_pnl
            })
        
        return pd.DataFrame(equity_data[1:])  # Skip initial
