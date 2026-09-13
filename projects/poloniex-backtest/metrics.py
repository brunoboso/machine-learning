"""
Performance metrics and statistics for backtest evaluation.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from scipy import stats as scipy_stats


def calculate_metrics(trade_log: pd.DataFrame, initial_capital: float = 100.0) -> Dict:
    """
    Calculate comprehensive performance metrics from trade log.
    
    Args:
        trade_log: DataFrame with trade data
        initial_capital: Starting capital
    
    Returns:
        Dictionary of metrics
    """
    if trade_log.empty or len(trade_log) == 0:
        return {
            'trades': 0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'expectancy_r': 0.0,
            'expectancy_usdt': 0.0,
            'net_pnl': 0.0,
            'total_return_pct': 0.0,
            'max_drawdown_pct': 0.0,
            'avg_drawdown_pct': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'payoff_ratio': 0.0,
            'max_win_streak': 0,
            'max_loss_streak': 0,
            'targets_hit': 0,
            'stops_hit': 0,
            'avg_trade_duration_hours': 0.0,
            'median_trade_duration_hours': 0.0,
            'low_sample_size': True
        }
    
    # Basic stats
    total_trades = len(trade_log)
    
    # Wins and losses
    wins = trade_log[trade_log['net_pnl'] > 0]
    losses = trade_log[trade_log['net_pnl'] <= 0]
    
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    
    # P&L
    total_wins = wins['net_pnl'].sum() if len(wins) > 0 else 0.0
    total_losses = abs(losses['net_pnl'].sum()) if len(losses) > 0 else 0.0
    
    profit_factor = total_wins / total_losses if total_losses > 0 else (np.inf if total_wins > 0 else 0.0)
    
    net_pnl = trade_log['net_pnl'].sum()
    
    # Expectancy
    expectancy_usdt = net_pnl / total_trades if total_trades > 0 else 0.0
    expectancy_r = trade_log['r_multiple'].mean() if total_trades > 0 else 0.0
    
    # Returns
    total_return_pct = (net_pnl / initial_capital) * 100
    
    # Drawdown
    equity_curve = initial_capital + trade_log['net_pnl'].cumsum()
    running_max = equity_curve.expanding().max()
    drawdown = (equity_curve - running_max) / running_max * 100
    
    max_drawdown_pct = abs(drawdown.min()) if len(drawdown) > 0 else 0.0
    avg_drawdown_pct = abs(drawdown[drawdown < 0].mean()) if (drawdown < 0).any() else 0.0
    
    # Win/Loss statistics
    avg_win = wins['net_pnl'].mean() if len(wins) > 0 else 0.0
    avg_loss = losses['net_pnl'].mean() if len(losses) > 0 else 0.0
    
    payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else (np.inf if avg_win > 0 else 0.0)
    
    # Risk-adjusted metrics
    returns_series = trade_log['net_pnl'] / initial_capital
    
    if len(returns_series) > 1:
        mean_return = returns_series.mean()
        std_return = returns_series.std()
        
        # Sharpe ratio (annualized, assuming ~252 trading days)
        # Simplified: using per-trade returns
        sharpe_ratio = mean_return / std_return * np.sqrt(252) if std_return > 0 else 0.0
        
        # Sortino ratio (downside deviation only)
        downside_returns = returns_series[returns_series < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else std_return
        sortino_ratio = mean_return / downside_std * np.sqrt(252) if downside_std > 0 else 0.0
        
        # Calmar ratio (return / max drawdown)
        calmar_ratio = total_return_pct / max_drawdown_pct if max_drawdown_pct > 0 else 0.0
    else:
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        calmar_ratio = 0.0
    
    # Streaks
    win_mask = (trade_log['net_pnl'] > 0).astype(int)
    loss_mask = (trade_log['net_pnl'] <= 0).astype(int)
    
    max_win_streak = get_max_streak(win_mask)
    max_loss_streak = get_max_streak(loss_mask)
    
    # Exit reasons
    targets_hit = (trade_log['exit_reason'] == 'TARGET_3R').sum()
    stops_hit = (trade_log['exit_reason'].isin(['STOP', 'AMBIGUOUS_STOP_FIRST'])).sum()
    
    # Trade duration
    if 'entry_timestamp' in trade_log.columns and 'exit_timestamp' in trade_log.columns:
        durations = (trade_log['exit_timestamp'] - trade_log['entry_timestamp']).dt.total_seconds() / 3600
        avg_trade_duration_hours = durations.mean()
        median_trade_duration_hours = durations.median()
    else:
        avg_trade_duration_hours = 0.0
        median_trade_duration_hours = 0.0
    
    # Sample size warning
    low_sample_size = total_trades < 50
    
    metrics = {
        'trades': total_trades,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'expectancy_r': expectancy_r,
        'expectancy_usdt': expectancy_usdt,
        'net_pnl': net_pnl,
        'total_return_pct': total_return_pct,
        'max_drawdown_pct': max_drawdown_pct,
        'avg_drawdown_pct': avg_drawdown_pct,
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'calmar_ratio': calmar_ratio,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'payoff_ratio': payoff_ratio,
        'max_win_streak': max_win_streak,
        'max_loss_streak': max_loss_streak,
        'targets_hit': targets_hit,
        'stops_hit': stops_hit,
        'avg_trade_duration_hours': avg_trade_duration_hours,
        'median_trade_duration_hours': median_trade_duration_hours,
        'low_sample_size': low_sample_size
    }
    
    return metrics


def get_max_streak(binary_series: pd.Series) -> int:
    """Calculate maximum consecutive streak of 1s."""
    if len(binary_series) == 0:
        return 0
    
    max_streak = 0
    current_streak = 0
    
    for val in binary_series:
        if val == 1:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    
    return max_streak


def calculate_metrics_by_direction(trade_log: pd.DataFrame, initial_capital: float = 100.0) -> Dict:
    """Calculate separate metrics for LONG and SHORT trades."""
    long_trades = trade_log[trade_log['direction'] == 'LONG']
    short_trades = trade_log[trade_log['direction'] == 'SHORT']
    
    metrics = {
        'all': calculate_metrics(trade_log, initial_capital),
        'long': calculate_metrics(long_trades, initial_capital),
        'short': calculate_metrics(short_trades, initial_capital)
    }
    
    return metrics


def calculate_metrics_by_symbol(trade_log: pd.DataFrame, initial_capital: float = 100.0) -> Dict:
    """Calculate metrics grouped by symbol."""
    if 'symbol' not in trade_log.columns:
        return {}
    
    metrics_by_symbol = {}
    for symbol in trade_log['symbol'].unique():
        symbol_trades = trade_log[trade_log['symbol'] == symbol]
        metrics_by_symbol[symbol] = calculate_metrics(symbol_trades, initial_capital)
    
    return metrics_by_symbol


def calculate_metrics_by_month(trade_log: pd.DataFrame, initial_capital: float = 100.0) -> Dict:
    """Calculate metrics grouped by month."""
    if 'exit_timestamp' not in trade_log.columns:
        return {}
    
    trade_log = trade_log.copy()
    trade_log['month'] = trade_log['exit_timestamp'].dt.to_period('M')
    
    metrics_by_month = {}
    for month in trade_log['month'].unique():
        month_trades = trade_log[trade_log['month'] == month]
        metrics_by_month[str(month)] = calculate_metrics(month_trades, initial_capital)
    
    return metrics_by_month


def split_is_oos(
    trade_log: pd.DataFrame,
    is_split_pct: float = 0.70
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split trade log into in-sample and out-of-sample (chronological).
    
    Args:
        trade_log: Trade log DataFrame
        is_split_pct: In-sample percentage (e.g., 0.70 for 70%)
    
    Returns:
        (in_sample_df, out_of_sample_df)
    """
    if trade_log.empty:
        return trade_log, trade_log
    
    # Sort by entry timestamp
    trade_log = trade_log.sort_values('entry_timestamp')
    
    split_idx = int(len(trade_log) * is_split_pct)
    
    in_sample = trade_log.iloc[:split_idx].copy()
    out_of_sample = trade_log.iloc[split_idx:].copy()
    
    return in_sample, out_of_sample


def rank_configurations(results: List[Dict], initial_capital: float = 100.0) -> pd.DataFrame:
    """
    Rank backtest configurations by composite score.
    
    Prioritizes:
    - Positive expectancy (R and USDT)
    - High profit factor
    - Low drawdown
    - Sufficient trade count
    - Stability (not isolated peaks)
    
    Args:
        results: List of backtest result dictionaries
        initial_capital: Starting capital
    
    Returns:
        DataFrame sorted by composite score (descending)
    """
    if not results:
        return pd.DataFrame()
    
    ranking_data = []
    
    for result in results:
        # Extract key metrics
        trades = result.get('trades', 0)
        expectancy_r = result.get('expectancy_r', 0)
        expectancy_usdt = result.get('expectancy_usdt', 0)
        profit_factor = result.get('profit_factor', 0)
        max_dd = result.get('max_drawdown_pct', 100)
        win_rate = result.get('win_rate', 0)
        total_return = result.get('total_return_pct', 0)
        sharpe = result.get('sharpe_ratio', 0)
        
        # Composite score components
        # 1. Expectancy score (normalized)
        exp_score = expectancy_r * 10  # Scale up
        
        # 2. Profit factor score (capped)
        pf_score = min(profit_factor, 3) * 10
        
        # 3. Drawdown penalty (inverse)
        dd_score = max(0, 100 - max_dd)
        
        # 4. Trade count score (diminishing returns)
        trade_score = min(trades / 10, 10)  # Max score at 100 trades
        
        # 5. Return score
        return_score = total_return / 10
        
        # 6. Sample size penalty
        sample_penalty = 0.5 if trades < 50 else (0.8 if trades < 100 else 1.0)
        
        # Composite score (weighted sum)
        composite = (
            exp_score * 0.30 +
            pf_score * 0.25 +
            dd_score * 0.20 +
            trade_score * 0.10 +
            return_score * 0.15
        ) * sample_penalty
        
        ranking_data.append({
            'symbol': result.get('symbol', ''),
            'timeframe': result.get('timeframe', ''),
            'hilo_period': result.get('hilo_period', 0),
            'hilo_variant': result.get('hilo_variant', ''),
            'setup_expiration': result.get('setup_expiration_bars', None),
            'slippage_pct': result.get('slippage_pct', 0),
            'trades': trades,
            'expectancy_r': expectancy_r,
            'expectancy_usdt': expectancy_usdt,
            'profit_factor': profit_factor,
            'max_dd_pct': max_dd,
            'win_rate': win_rate,
            'return_pct': total_return,
            'sharpe': sharpe,
            'composite_score': composite
        })
    
    df = pd.DataFrame(ranking_data)
    df = df.sort_values('composite_score', ascending=False).reset_index(drop=True)
    
    return df


def generate_summary_stats(all_metrics: List[Dict]) -> Dict:
    """Generate summary statistics across all configurations."""
    if not all_metrics:
        return {}
    
    df = pd.DataFrame(all_metrics)
    
    summary = {
        'total_configs': len(df),
        'configs_with_trades': (df['trades'] > 0).sum(),
        'avg_trades': df['trades'].mean(),
        'avg_expectancy_r': df['expectancy_r'].mean(),
        'avg_profit_factor': df['profit_factor'].mean(),
        'best_expectancy_r': df['expectancy_r'].max(),
        'best_profit_factor': df['profit_factor'].max(),
        'worst_drawdown': df['max_drawdown_pct'].max(),
        'avg_drawdown': df['max_drawdown_pct'].mean(),
    }
    
    return summary


if __name__ == "__main__":
    # Test metrics calculation
    test_trades = pd.DataFrame({
        'entry_timestamp': pd.date_range('2023-01-01', periods=10, freq='1h'),
        'exit_timestamp': pd.date_range('2023-01-01', periods=10, freq='1h') + pd.Timedelta(hours=2),
        'direction': ['LONG', 'SHORT'] * 5,
        'net_pnl': [1.5, -0.8, 2.3, -0.5, 1.1, -0.9, 3.2, -1.2, 0.5, -0.4],
        'r_multiple': [1.5, -0.8, 2.3, -0.5, 1.1, -0.9, 3.2, -1.2, 0.5, -0.4],
        'exit_reason': ['TARGET_3R', 'STOP', 'TARGET_3R', 'STOP'] * 2 + ['TARGET_3R', 'STOP'],
        'symbol': ['BTC_USDT'] * 10,
    })
    
    metrics = calculate_metrics(test_trades, initial_capital=100.0)
    
    print("Test metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
