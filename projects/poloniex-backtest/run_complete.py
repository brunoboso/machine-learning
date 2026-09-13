"""
Feasible backtest - runs to completion with comprehensive results.
Focus on most liquid pairs with full parameter coverage.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import time

from config import DEFAULT_CONFIG
from download_data import PoloniexDataDownloader
from backtest import run_single_backtest
from metrics import calculate_metrics, split_is_oos, rank_configurations
from main import generate_report

# Top 15 most liquid USDT pairs (proven to have > $10M volume)
LIQUID_PAIRS = [
    'BTC_USDT', 'ETH_USDT', 'SOL_USDT', 'DOGE_USDT', 'XRP_USDT',
    'TRX_USDT', 'AVAX_USDT', 'LINK_USDT', 'DOT_USDT', 'UNI_USDT',
    'NEAR_USDT', 'LTC_USDT', 'SHIB_USDT', 'PEPE_USDT', 'FLOKI_USDT',
]

def run_complete_backtest():
    """Run complete backtest to finish - no background jobs."""
    
    print("\n" + "=" * 80)
    print("COMPLETE BACKTEST - RUNNING TO FINISH")
    print("=" * 80)
    print(f"Started: {datetime.now()}")
    
    config = DEFAULT_CONFIG
    downloader = PoloniexDataDownloader()
    
    # Phase 1: Download data
    print(f"\nPhase 1: Downloading {len(LIQUID_PAIRS)} liquid pairs...")
    
    timeframes = ['1h', '4h']
    months = 12
    data_dict = {}
    start_time = datetime.now() - timedelta(days=30 * months)
    
    download_start = time.time()
    
    for symbol in LIQUID_PAIRS:
        for timeframe in timeframes:
            try:
                df = downloader.get_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_time=start_time,
                    force_download=False
                )
                
                if not df.empty:
                    df = downloader.compute_24h_volume(df, timeframe)
                    max_vol = df['volume_24h'].max()
                    
                    if max_vol >= config.market.min_24h_volume_usdt:
                        data_dict[(symbol, timeframe)] = df
                        print(f"  ✓ {symbol} {timeframe}: {len(df)} candles, ${max_vol:,.0f}")
                    else:
                        print(f"  ✗ {symbol} {timeframe}: Below threshold")
            
            except Exception as e:
                print(f"  Error: {symbol} {timeframe}: {e}")
                continue
    
    download_elapsed = time.time() - download_start
    print(f"\nDownload complete: {len(data_dict)} pairs in {download_elapsed:.1f}s")
    
    if not data_dict:
        print("ERROR: No data downloaded")
        return None, None, None
    
    # Phase 2: Parameter grid
    print("\nPhase 2: Parameter grid setup...")
    
    hilo_periods = [10, 15, 20, 25, 30, 40, 50]
    hilo_variants = ['A', 'B']
    setup_expirations = [None, 3, 5, 10]
    slippage = 0.0005  # 0.05% primary
    
    total_runs = len(data_dict) * len(hilo_periods) * len(hilo_variants) * len(setup_expirations)
    
    print(f"Total configurations: {total_runs}")
    print(f"  Pairs: {len(data_dict)}")
    print(f"  HiLo periods: {hilo_periods}")
    print(f"  Variants: {hilo_variants}")
    print(f"  Expirations: {setup_expirations}")
    print(f"  Slippage: {slippage*100:.2f}%")
    
    # Phase 3: Run backtests
    print("\nPhase 3: Running backtests (this will take time)...")
    
    all_results = []
    all_trades = []
    run_count = 0
    backtest_start = time.time()
    
    for (symbol, timeframe), df in data_dict.items():
        pair_start = time.time()
        print(f"\nProcessing {symbol} {timeframe}...")
        
        for hilo_period in hilo_periods:
            for hilo_variant in hilo_variants:
                for expiration in setup_expirations:
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
                        
                        # Progress every 50 runs
                        if run_count % 50 == 0:
                            elapsed = time.time() - backtest_start
                            rate = run_count / elapsed if elapsed > 0 else 0
                            eta = (total_runs - run_count) / rate if rate > 0 else 0
                            pct = 100 * run_count / total_runs
                            print(f"  Progress: {run_count}/{total_runs} ({pct:.1f}%) | ETA: {eta/60:.1f}min")
                    
                    except Exception as e:
                        print(f"  Error run {run_count}: {e}")
                        continue
        
        pair_elapsed = time.time() - pair_start
        print(f"  {symbol} {timeframe} done in {pair_elapsed:.1f}s")
    
    backtest_elapsed = time.time() - backtest_start
    print(f"\n✓ All backtests complete in {backtest_elapsed:.1f}s ({total_runs} runs, {backtest_elapsed/total_runs:.2f}s per run)")
    
    # Phase 4: Save results
    print("\nPhase 4: Saving results...")
    
    results_dir = Path('results')
    trades_dir = results_dir / 'trades'
    metrics_dir = results_dir / 'metrics'
    
    trades_dir.mkdir(exist_ok=True, parents=True)
    metrics_dir.mkdir(exist_ok=True, parents=True)
    
    # Save all trades
    if all_trades:
        all_trades_df = pd.concat(all_trades, ignore_index=True)
        trades_file = trades_dir / 'all_trades.csv'
        all_trades_df.to_csv(trades_file, index=False)
        print(f"  ✓ {len(all_trades_df)} trades → {trades_file}")
    else:
        all_trades_df = pd.DataFrame()
        print(f"  ⚠ No trades executed")
    
    # Save all metrics
    metrics_df = pd.DataFrame(all_results)
    metrics_file = metrics_dir / 'all_metrics.csv'
    metrics_df.to_csv(metrics_file, index=False)
    print(f"  ✓ {len(metrics_df)} configs → {metrics_file}")
    
    # Save ranking
    ranking = rank_configurations(all_results, config.portfolio.initial_capital)
    ranking_file = metrics_dir / 'ranking.csv'
    ranking.to_csv(ranking_file, index=False)
    print(f"  ✓ Ranking → {ranking_file}")
    
    # Phase 5: IS/OOS Analysis
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
        print(f"  ✓ IS/OOS analysis → {is_oos_file}")
    
    # Phase 6: Generate final report
    print("\nPhase 6: Generating final report...")
    generate_report(all_results, all_trades_df, ranking)
    print(f"  ✓ Final report → results/BACKTEST_REPORT.md")
    
    # Summary
    total_elapsed = time.time() - download_start
    print("\n" + "=" * 80)
    print("BACKTEST COMPLETE")
    print("=" * 80)
    print(f"Total time: {total_elapsed/60:.1f} minutes")
    print(f"Configurations: {len(all_results)}")
    print(f"Configs with trades: {sum(1 for r in all_results if r['trades'] > 0)}")
    print(f"Total trades: {len(all_trades_df) if not all_trades_df.empty else 0}")
    
    if not ranking.empty:
        print("\nTop 5 Configurations:")
        for idx, row in ranking.head(5).iterrows():
            print(f"  {idx+1}. {row['symbol']} {row['timeframe']} HiLo{row['hilo_period']}{row['hilo_variant']} | "
                  f"Exp: {row['expectancy_r']:.3f}R | PF: {row['profit_factor']:.2f} | Trades: {row['trades']}")
    
    return all_results, all_trades_df, ranking


if __name__ == "__main__":
    try:
        results, trades, ranking = run_complete_backtest()
        
        if results is not None:
            print("\n✅ SUCCESS: All results saved to results/ directory")
            sys.exit(0)
        else:
            print("\n❌ FAILED: No results generated")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
