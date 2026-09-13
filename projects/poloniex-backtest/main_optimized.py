"""
Optimized main script - focuses on major liquid pairs for faster execution.
"""
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

# Import from main
from config import DEFAULT_CONFIG
from download_data import PoloniexDataDownloader
from backtest import run_single_backtest
from metrics import calculate_metrics, split_is_oos, rank_configurations
from main import generate_report


# Major liquid USDT pairs on Poloniex (focus on top 20-30 by volume)
MAJOR_PAIRS = [
    'BTC_USDT', 'ETH_USDT', 'TRX_USDT', 'SOL_USDT',
    'DOGE_USDT', 'XRP_USDT', 'ADA_USDT', 'MATIC_USDT',
    'DOT_USDT', 'AVAX_USDT', 'LINK_USDT', 'UNI_USDT',
    'ATOM_USDT', 'LTC_USDT', 'ETC_USDT', 'NEAR_USDT',
    'FIL_USDT', 'APT_USDT', 'ARB_USDT', 'OP_USDT',
    'SHIB_USDT', 'PEPE_USDT', 'FLOKI_USDT', 'WIF_USDT',
    'STX_USDT', 'INJ_USDT', 'SEI_USDT', 'TIA_USDT',
    'SUI_USDT', 'TON_USDT',
]


def run_optimized_backtest():
    """Run optimized backtest on major liquid pairs only."""
    print("\n" + "=" * 80)
    print("OPTIMIZED FULL BACKTEST - Major Liquid Pairs Only")
    print("=" * 80)
    
    config = DEFAULT_CONFIG
    downloader = PoloniexDataDownloader()
    
    # Download major pairs
    print(f"\nPhase 1: Downloading {len(MAJOR_PAIRS)} major pairs...")
    
    timeframes = ['1h', '4h']  # Focus on most important timeframes
    months = 12  # Full 12 months
    
    data_dict = {}
    start_time = datetime.now() - timedelta(days=30 * months)
    
    for symbol in MAJOR_PAIRS:
        for timeframe in timeframes:
            try:
                df = downloader.get_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_time=start_time,
                    force_download=False
                )
                
                if not df.empty:
                    # Compute 24h volume
                    df = downloader.compute_24h_volume(df, timeframe)
                    
                    # Check volume
                    max_vol = df['volume_24h'].max()
                    if max_vol >= config.market.min_24h_volume_usdt:
                        data_dict[(symbol, timeframe)] = df
                        print(f"  ✓ {symbol} {timeframe}: {len(df)} candles, ${max_vol:,.0f}")
                    else:
                        print(f"  ✗ {symbol} {timeframe}: Below threshold (${max_vol:,.0f})")
                
            except Exception as e:
                print(f"  Error: {symbol} {timeframe}: {e}")
                continue
    
    print(f"\nData ready: {len(data_dict)} symbol-timeframe combinations")
    
    if not data_dict:
        print("ERROR: No data available")
        return
    
    # Parameter grid
    print("\nPhase 2: Parameter grid...")
    
    hilo_periods = [10, 15, 20, 25, 30, 40, 50]
    hilo_variants = ['A', 'B']
    setup_expirations = [None, 3, 5, 10]
    slippages = [0.0, 0.0005, 0.001]
    
    total_runs = len(data_dict) * len(hilo_periods) * len(hilo_variants) * len(setup_expirations) * len(slippages)
    
    print(f"Total runs: {total_runs}")
    print(f"  Pairs: {len(data_dict)}")
    print(f"  HiLo periods: {len(hilo_periods)}")
    print(f"  Variants: {len(hilo_variants)}")
    print(f"  Expirations: {len(setup_expirations)}")
    print(f"  Slippages: {len(slippages)}")
    
    # Run backtests
    print("\nPhase 3: Running backtests...")
    
    all_results = []
    all_trades = []
    run_count = 0
    start_backtest_time = time.time()
    
    for (symbol, timeframe), df in data_dict.items():
        print(f"\nProcessing {symbol} {timeframe}...")
        
        for hilo_period in hilo_periods:
            for hilo_variant in hilo_variants:
                for expiration in setup_expirations:
                    for slippage in slippages:
                        run_count += 1
                        
                        try:
                            results, trade_log = run_single_backtest(
                                df=df,
                                symbol=symbol,
                                timeframe=timeframe,
                                hilo_period=hilo_period,
                                hilo_variant=hilo_variant,
                                direction='BOTH',
                                setup_expiration_bars=expiration,
                                slippage_pct=slippage,
                                config=config
                            )
                            
                            metrics = calculate_metrics(trade_log, config.portfolio.initial_capital)
                            full_result = {**results, **metrics}
                            all_results.append(full_result)
                            
                            if not trade_log.empty:
                                trade_log['run_id'] = run_count
                                all_trades.append(trade_log)
                            
                            if run_count % 100 == 0:
                                elapsed = time.time() - start_backtest_time
                                rate = run_count / elapsed
                                eta = (total_runs - run_count) / rate
                                print(f"  Progress: {run_count}/{total_runs} ({100*run_count/total_runs:.1f}%) | ETA: {eta/60:.1f}min")
                        
                        except Exception as e:
                            print(f"  Error run {run_count}: {e}")
                            continue
    
    elapsed_total = time.time() - start_backtest_time
    print(f"\n✓ Complete in {elapsed_total:.1f}s ({total_runs} runs)")
    
    # Save results
    print("\nPhase 4: Saving results...")
    
    results_dir = Path('results')
    trades_dir = results_dir / 'trades'
    metrics_dir = results_dir / 'metrics'
    
    trades_dir.mkdir(exist_ok=True, parents=True)
    metrics_dir.mkdir(exist_ok=True, parents=True)
    
    if all_trades:
        all_trades_df = pd.concat(all_trades, ignore_index=True)
        trades_file = trades_dir / 'all_trades.csv'
        all_trades_df.to_csv(trades_file, index=False)
        print(f"  ✓ {len(all_trades_df)} trades → {trades_file}")
    else:
        all_trades_df = pd.DataFrame()
    
    metrics_df = pd.DataFrame(all_results)
    metrics_file = metrics_dir / 'all_metrics.csv'
    metrics_df.to_csv(metrics_file, index=False)
    print(f"  ✓ {len(metrics_df)} configs → {metrics_file}")
    
    ranking = rank_configurations(all_results, config.portfolio.initial_capital)
    ranking_file = metrics_dir / 'ranking.csv'
    ranking.to_csv(ranking_file, index=False)
    print(f"  ✓ Ranking → {ranking_file}")
    
    # IS/OOS analysis
    print("\nPhase 5: IS/OOS analysis...")
    
    is_oos_results = []
    
    for result in all_results:
        if result['trades'] < 10:
            continue
        
        run_trades = all_trades_df[
            (all_trades_df['symbol'] == result['symbol']) &
            (all_trades_df['timeframe'] == result['timeframe']) &
            (all_trades_df['hilo_period'] == result['hilo_period']) &
            (all_trades_df['hilo_variant'] == result['hilo_variant'])
        ]
        
        if run_trades.empty:
            continue
        
        is_trades, oos_trades = split_is_oos(run_trades, config.validation.is_split_pct)
        
        is_metrics = calculate_metrics(is_trades, config.portfolio.initial_capital)
        oos_metrics = calculate_metrics(oos_trades, config.portfolio.initial_capital)
        
        is_oos_results.append({
            'symbol': result['symbol'],
            'timeframe': result['timeframe'],
            'hilo_period': result['hilo_period'],
            'hilo_variant': result['hilo_variant'],
            'is_trades': is_metrics['trades'],
            'is_expectancy_r': is_metrics['expectancy_r'],
            'is_profit_factor': is_metrics['profit_factor'],
            'oos_trades': oos_metrics['trades'],
            'oos_expectancy_r': oos_metrics['expectancy_r'],
            'oos_profit_factor': oos_metrics['profit_factor'],
            'expectancy_gap': abs(is_metrics['expectancy_r'] - oos_metrics['expectancy_r']),
        })
    
    if is_oos_results:
        is_oos_df = pd.DataFrame(is_oos_results)
        is_oos_file = metrics_dir / 'is_oos_analysis.csv'
        is_oos_df.to_csv(is_oos_file, index=False)
        print(f"  ✓ IS/OOS → {is_oos_file}")
    
    # Generate report
    print("\nPhase 6: Generating report...")
    generate_report(all_results, all_trades_df, ranking)
    
    # Summary
    print("\n" + "=" * 80)
    print("BACKTEST COMPLETE")
    print("=" * 80)
    print(f"Configurations tested: {len(all_results)}")
    print(f"Configurations with trades: {sum(1 for r in all_results if r['trades'] > 0)}")
    print(f"Total trades: {len(all_trades_df) if not all_trades_df.empty else 0}")
    
    if not ranking.empty:
        print("\nTop 10 Configurations:")
        print("-" * 80)
        for idx, row in ranking.head(10).iterrows():
            print(f"{idx+1}. {row['symbol']} {row['timeframe']} | HiLo {row['hilo_period']}{row['hilo_variant']} | "
                  f"Exp: {row['expectancy_r']:.3f}R | PF: {row['profit_factor']:.2f} | Trades: {row['trades']}")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("POLONIEX SPOT BACKTESTING SYSTEM - OPTIMIZED")
    print("=" * 80)
    print(f"Started: {datetime.now()}")
    
    run_optimized_backtest()
    
    print(f"\nFinished: {datetime.now()}")
    print("Results in results/ directory")
