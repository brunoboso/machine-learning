"""
Main entry point for Poloniex backtesting system.
Runs smoke test and full parameter grid.
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from typing import List, Dict
import json

from config import DEFAULT_CONFIG
from download_data import PoloniexDataDownloader, download_all_pairs
from backtest import Backtest, run_single_backtest
from metrics import (
    calculate_metrics, calculate_metrics_by_direction,
    calculate_metrics_by_symbol, split_is_oos, rank_configurations
)


def run_smoke_test():
    """
    Run smoke test: BTC_USDT, 1h, HiLo 30, Variant A.
    Print and save first 20 setups for manual audit.
    """
    print("\n" + "=" * 80)
    print("SMOKE TEST: BTC_USDT, 1h, HiLo period 30, Variant A")
    print("=" * 80)
    
    # Download BTC_USDT data
    downloader = PoloniexDataDownloader()
    
    start_time = datetime.now() - timedelta(days=365)  # 12 months
    
    df = downloader.get_candles(
        symbol='BTC_USDT',
        timeframe='1h',
        start_time=start_time,
        force_download=False
    )
    
    if df.empty:
        print("ERROR: Failed to download BTC_USDT data")
        return False
    
    print(f"\nData loaded: {len(df)} candles from {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    # Add 24h volume
    df = downloader.compute_24h_volume(df, '1h')
    
    # Run backtest
    backtest = Backtest(
        df=df,
        symbol='BTC_USDT',
        timeframe='1h',
        hilo_period=30,
        hilo_variant='A',
        direction='BOTH',
        setup_expiration_bars=None  # No expiration for smoke test
    )
    
    # Get first 20 setups
    setup_log = backtest.get_setup_log(max_setups=20)
    
    print(f"\nTotal setups detected: {len(backtest.all_setups)}")
    print(f"\nFirst 20 setups for manual audit:")
    print("-" * 80)
    
    # Display setup details
    for idx, row in setup_log.iterrows():
        print(f"\nSetup #{idx + 1} - {row['direction']}:")
        print(f"  Candle 1: {row['candle1_timestamp']} | Low: {row['low1']:.2f}, High: {row['high1']:.2f}")
        print(f"  Candle 2: {row['candle2_timestamp']} | Low: {row['low2']:.2f}, High: {row['high2']:.2f}")
        print(f"  Candle 3: {row['candle3_timestamp']} | Low: {row['low3']:.2f}, High: {row['high3']:.2f}")
        print(f"  Entry trigger: {row['entry_price']:.2f}")
        print(f"  Stop: {row['stop_price']:.2f} ({row['stop_percent']:.2f}%)")
        print(f"  Target: {row['target_price']:.2f} (3R)")
        print(f"  HiLo: {row['hilo_value']:.2f}, Direction: {row['hilo_direction']}, Slope: {row['hilo_slope']:.4f}")
        print(f"  Volume 24h: ${row['volume_24h']:,.0f}")
        
        # Accept/Reject reason
        if row['expired']:
            print(f"  Status: EXPIRED")
        else:
            print(f"  Status: ARMED (ready for entry)")
    
    # Save to files
    results_dir = Path('results')
    results_dir.mkdir(exist_ok=True)
    
    # Save setup log as CSV
    setup_csv = results_dir / 'smoke_btc_usdt_1h_hilo30_setups.csv'
    setup_log.to_csv(setup_csv, index=False)
    print(f"\n✓ Setup log saved to {setup_csv}")
    
    # Save setup log as Markdown
    smoke_md = results_dir / 'smoke_btc_usdt_1h_hilo30.md'
    with open(smoke_md, 'w') as f:
        f.write("# Smoke Test: BTC_USDT 1h HiLo 30 Variant A\n\n")
        f.write(f"**Generated:** {datetime.now()}\n\n")
        f.write(f"**Data Range:** {df['timestamp'].min()} to {df['timestamp'].max()}\n")
        f.write(f"**Total Candles:** {len(df)}\n")
        f.write(f"**Total Setups Detected:** {len(backtest.all_setups)}\n\n")
        f.write("## First 20 Setups (Manual Audit)\n\n")
        
        for idx, row in setup_log.iterrows():
            f.write(f"### Setup #{idx + 1} - {row['direction']}\n\n")
            f.write(f"- **Candle 1:** {row['candle1_timestamp']} | Low: {row['low1']:.2f}, High: {row['high1']:.2f}\n")
            f.write(f"- **Candle 2:** {row['candle2_timestamp']} | Low: {row['low2']:.2f}, High: {row['high2']:.2f}\n")
            f.write(f"- **Candle 3:** {row['candle3_timestamp']} | Low: {row['low3']:.2f}, High: {row['high3']:.2f}\n")
            f.write(f"- **Entry Trigger:** {row['entry_price']:.2f}\n")
            f.write(f"- **Stop Loss:** {row['stop_price']:.2f} ({row['stop_percent']:.2f}%)\n")
            f.write(f"- **Target:** {row['target_price']:.2f} (3R = +{row['stop_percent'] * 3:.2f}%)\n")
            f.write(f"- **HiLo Value:** {row['hilo_value']:.2f}\n")
            f.write(f"- **HiLo Direction:** {row['hilo_direction']} (1=Long, -1=Short)\n")
            f.write(f"- **HiLo Slope:** {row['hilo_slope']:.4f}\n")
            f.write(f"- **24h Volume:** ${row['volume_24h']:,.0f} USDT\n")
            
            if row['expired']:
                f.write(f"- **Status:** ⚠️ EXPIRED\n")
            else:
                f.write(f"- **Status:** ✓ ARMED (ready for entry)\n")
            
            f.write("\n")
    
    print(f"✓ Smoke test report saved to {smoke_md}")
    
    print("\n" + "=" * 80)
    print("SMOKE TEST COMPLETE - Proceeding to full backtest...")
    print("=" * 80)
    
    return True


def run_full_backtest(
    max_symbols: int = None,
    quick_mode: bool = False
):
    """
    Run full parameter grid backtest.
    
    Args:
        max_symbols: Limit number of symbols (for testing)
        quick_mode: If True, run reduced parameter set
    """
    print("\n" + "=" * 80)
    print("FULL BACKTEST: Parameter Grid Sweep")
    print("=" * 80)
    
    config = DEFAULT_CONFIG
    
    # Download all USDT pairs
    print("\nPhase 1: Downloading market data...")
    
    if quick_mode:
        timeframes = ['1h', '4h']
        months = 6
    else:
        timeframes = config.market.timeframes
        months = config.market.initial_history_months
    
    data_dict = download_all_pairs(
        timeframes=timeframes,
        months_history=months,
        force_download=False,
        min_volume=config.market.min_24h_volume_usdt
    )
    
    if not data_dict:
        print("ERROR: No data downloaded")
        return
    
    # Limit symbols if requested
    if max_symbols:
        data_dict = dict(list(data_dict.items())[:max_symbols * len(timeframes)])
    
    print(f"\nData ready: {len(data_dict)} symbol-timeframe combinations")
    
    # Parameter grid
    print("\nPhase 2: Setting up parameter grid...")
    
    if quick_mode:
        hilo_periods = [20, 30, 40]
        hilo_variants = ['A']
        setup_expirations = [None, 5]
        slippages = [0.0, 0.0005]
    else:
        hilo_periods = config.strategy.hilo_periods
        hilo_variants = config.strategy.hilo_variants
        setup_expirations = [None] + config.strategy.setup_expiration_bars
        slippages = config.costs.slippage_scenarios
    
    # Generate all combinations
    total_runs = 0
    for (symbol, timeframe), df in data_dict.items():
        for hilo_period in hilo_periods:
            for hilo_variant in hilo_variants:
                for expiration in setup_expirations:
                    for slippage in slippages:
                        total_runs += 1
    
    print(f"Total backtest runs: {total_runs}")
    print(f"  Symbols: {len(set(s for s, t in data_dict.keys()))}")
    print(f"  Timeframes: {len(timeframes)}")
    print(f"  HiLo periods: {hilo_periods}")
    print(f"  Variants: {hilo_variants}")
    print(f"  Expirations: {setup_expirations}")
    print(f"  Slippages: {slippages}")
    
    # Run backtests
    print("\nPhase 3: Running backtests...")
    
    all_results = []
    all_trades = []
    
    run_count = 0
    start_time = time.time()
    
    for (symbol, timeframe), df in data_dict.items():
        print(f"\nProcessing {symbol} {timeframe}...")
        
        for hilo_period in hilo_periods:
            for hilo_variant in hilo_variants:
                for expiration in setup_expirations:
                    for slippage in slippages:
                        run_count += 1
                        
                        try:
                            # Run backtest
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
                            
                            # Calculate metrics
                            metrics = calculate_metrics(trade_log, config.portfolio.initial_capital)
                            
                            # Merge results and metrics
                            full_result = {**results, **metrics}
                            all_results.append(full_result)
                            
                            # Store trades
                            if not trade_log.empty:
                                trade_log['run_id'] = run_count
                                all_trades.append(trade_log)
                            
                            # Progress
                            if run_count % 50 == 0:
                                elapsed = time.time() - start_time
                                rate = run_count / elapsed
                                eta = (total_runs - run_count) / rate
                                print(f"  Progress: {run_count}/{total_runs} ({100*run_count/total_runs:.1f}%) "
                                      f"| ETA: {eta/60:.1f} min")
                        
                        except Exception as e:
                            print(f"  Error in run {run_count}: {e}")
                            continue
    
    elapsed_total = time.time() - start_time
    print(f"\n✓ Backtests complete in {elapsed_total:.1f}s ({total_runs} runs)")
    
    # Combine all trades
    if all_trades:
        all_trades_df = pd.concat(all_trades, ignore_index=True)
    else:
        all_trades_df = pd.DataFrame()
    
    # Save results
    print("\nPhase 4: Saving results...")
    
    results_dir = Path('results')
    trades_dir = results_dir / 'trades'
    metrics_dir = results_dir / 'metrics'
    
    trades_dir.mkdir(exist_ok=True, parents=True)
    metrics_dir.mkdir(exist_ok=True, parents=True)
    
    # Save all trades
    if not all_trades_df.empty:
        trades_file = trades_dir / 'all_trades.csv'
        all_trades_df.to_csv(trades_file, index=False)
        print(f"  ✓ Saved {len(all_trades_df)} trades to {trades_file}")
    
    # Save all metrics
    metrics_df = pd.DataFrame(all_results)
    metrics_file = metrics_dir / 'all_metrics.csv'
    metrics_df.to_csv(metrics_file, index=False)
    print(f"  ✓ Saved {len(metrics_df)} metrics to {metrics_file}")
    
    # Rank configurations
    ranking = rank_configurations(all_results, config.portfolio.initial_capital)
    ranking_file = metrics_dir / 'ranking.csv'
    ranking.to_csv(ranking_file, index=False)
    print(f"  ✓ Saved ranking to {ranking_file}")
    
    # IS/OOS analysis
    print("\nPhase 5: In-Sample / Out-of-Sample analysis...")
    
    is_oos_results = []
    
    for result in all_results:
        if result['trades'] == 0:
            continue
        
        # Find corresponding trades
        run_trades = all_trades_df[
            (all_trades_df['symbol'] == result['symbol']) &
            (all_trades_df['timeframe'] == result['timeframe']) &
            (all_trades_df['hilo_period'] == result['hilo_period']) &
            (all_trades_df['hilo_variant'] == result['hilo_variant'])
        ]
        
        if run_trades.empty:
            continue
        
        # Split IS/OOS
        is_trades, oos_trades = split_is_oos(run_trades, config.validation.is_split_pct)
        
        # Calculate metrics
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
        print(f"  ✓ Saved IS/OOS analysis to {is_oos_file}")
    
    print("\n✓ Full backtest complete!")
    print(f"  Total configurations tested: {len(all_results)}")
    print(f"  Configurations with trades: {sum(1 for r in all_results if r['trades'] > 0)}")
    print(f"  Total trades executed: {len(all_trades_df) if not all_trades_df.empty else 0}")
    
    # Top 10 configurations
    print("\nTop 10 Configurations by Composite Score:")
    print("-" * 80)
    top10 = ranking.head(10)
    for idx, row in top10.iterrows():
        print(f"{idx + 1}. {row['symbol']} {row['timeframe']} | "
              f"HiLo {row['hilo_period']} {row['hilo_variant']} | "
              f"Exp: {row['expectancy_r']:.3f}R | PF: {row['profit_factor']:.2f} | "
              f"DD: {row['max_dd_pct']:.1f}% | Trades: {row['trades']}")
    
    return all_results, all_trades_df, ranking


def generate_report(all_results: List[Dict], all_trades: pd.DataFrame, ranking: pd.DataFrame):
    """Generate comprehensive Markdown report."""
    print("\nGenerating final report...")
    
    report_path = Path('results') / 'BACKTEST_REPORT.md'
    
    with open(report_path, 'w') as f:
        f.write("# Poloniex Spot Backtest Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
        f.write("---\n\n")
        
        # Executive Summary
        f.write("## Executive Summary\n\n")
        
        total_configs = len(all_results)
        configs_with_trades = sum(1 for r in all_results if r['trades'] > 0)
        total_trades = len(all_trades) if not all_trades.empty else 0
        
        f.write(f"- **Total Configurations Tested:** {total_configs}\n")
        f.write(f"- **Configurations with Trades:** {configs_with_trades}\n")
        f.write(f"- **Total Trades Executed:** {total_trades}\n\n")
        
        if not ranking.empty:
            best = ranking.iloc[0]
            f.write("### Best Configuration\n\n")
            f.write(f"- **Symbol:** {best['symbol']}\n")
            f.write(f"- **Timeframe:** {best['timeframe']}\n")
            f.write(f"- **HiLo Period:** {best['hilo_period']}\n")
            f.write(f"- **HiLo Variant:** {best['hilo_variant']}\n")
            f.write(f"- **Trades:** {best['trades']}\n")
            f.write(f"- **Expectancy:** {best['expectancy_r']:.3f}R\n")
            f.write(f"- **Profit Factor:** {best['profit_factor']:.2f}\n")
            f.write(f"- **Max Drawdown:** {best['max_dd_pct']:.1f}%\n")
            f.write(f"- **Win Rate:** {best['win_rate']*100:.1f}%\n")
            f.write(f"- **Return:** {best['return_pct']:.1f}%\n\n")
        
        # Top 20 Rankings
        f.write("## Top 20 Configurations\n\n")
        f.write("| Rank | Symbol | TF | HiLo | Var | Trades | Exp(R) | PF | DD% | WR% | Return% |\n")
        f.write("|------|--------|-------|------|-----|--------|--------|-----|-----|-----|----------|\n")
        
        for idx, row in ranking.head(20).iterrows():
            f.write(f"| {idx+1} | {row['symbol']} | {row['timeframe']} | {row['hilo_period']} | "
                   f"{row['hilo_variant']} | {row['trades']} | {row['expectancy_r']:.3f} | "
                   f"{row['profit_factor']:.2f} | {row['max_dd_pct']:.1f} | "
                   f"{row['win_rate']*100:.1f} | {row['return_pct']:.1f} |\n")
        
        f.write("\n")
        
        # Conclusion
        f.write("## Conclusion\n\n")
        
        positive_configs = sum(1 for r in all_results if r.get('expectancy_r', 0) > 0)
        
        if positive_configs > 0:
            f.write(f"Found {positive_configs} configurations with positive expectancy.\n\n")
            f.write("**Robustness Assessment:**\n\n")
            f.write("- Review top configurations for parameter stability (plateaus vs. isolated peaks)\n")
            f.write("- Compare IS/OOS performance gaps\n")
            f.write("- Verify edge survives realistic fees and slippage\n")
            f.write("- Check for single-coin dependence\n\n")
            f.write("**Next Steps:**\n\n")
            f.write("- Walk-forward validation on top configurations\n")
            f.write("- Forward testing in paper trading environment\n")
            f.write("- Monitor for regime changes\n\n")
        else:
            f.write("**No configurations showed positive expectancy after costs.**\n\n")
            f.write("The 1-2-3 + HiLo Activator strategy does not appear to have a reliable edge "
                   "on Poloniex USDT pairs under the tested parameters and historical period.\n\n")
            f.write("**Recommendations:**\n\n")
            f.write("- Do NOT proceed to live trading\n")
            f.write("- Consider alternative patterns or market conditions\n")
            f.write("- Analyze trade distribution for insights\n\n")
        
        # Assumptions
        f.write("## Assumptions & Disclaimers\n\n")
        f.write("1. **HiLo Activator Bootstrap:** First valid HiLo value starts with down line\n")
        f.write("2. **Liquidity Filter:** 24h volume calculated as rolling sum of quoteVolume\n")
        f.write("3. **Intrabar Conflict:** If both stop and target hit same bar, stop executes first\n")
        f.write("4. **SHORT Trades:** Theoretical (Poloniex SPOT may not support short selling)\n")
        f.write("5. **Fees:** Conservative maker/taker estimates used\n")
        f.write("6. **No Lookahead:** All indicators and decisions use only historical data\n\n")
    
    print(f"✓ Report saved to {report_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Poloniex Spot Backtesting System')
    parser.add_argument('--smoke-only', action='store_true', help='Run only smoke test')
    parser.add_argument('--quick', action='store_true', help='Quick mode (reduced parameters)')
    parser.add_argument('--max-symbols', type=int, help='Limit number of symbols')
    parser.add_argument('--skip-smoke', action='store_true', help='Skip smoke test')
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("POLONIEX SPOT BACKTESTING SYSTEM")
    print("=" * 80)
    print(f"Started: {datetime.now()}")
    
    # Run smoke test (unless skipped)
    if not args.skip_smoke:
        smoke_success = run_smoke_test()
        if not smoke_success:
            print("\nSmoke test failed. Exiting.")
            return 1
    
    # If smoke-only, stop here
    if args.smoke_only:
        print("\n✓ Smoke test complete. Use --full for complete backtest.")
        return 0
    
    # Run full backtest
    all_results, all_trades, ranking = run_full_backtest(
        max_symbols=args.max_symbols,
        quick_mode=args.quick
    )
    
    # Generate report
    generate_report(all_results, all_trades, ranking)
    
    print("\n" + "=" * 80)
    print("BACKTEST COMPLETE")
    print("=" * 80)
    print(f"Finished: {datetime.now()}")
    print("\nResults available in results/ directory")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
