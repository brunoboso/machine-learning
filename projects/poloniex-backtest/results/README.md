# Backtest Results

## Files Generated

### Complete Results (Local Only - Too Large for GitHub)
- `all_trades.csv` - **1,089,827 trades** (382 MB) - Complete trade log
- `all_metrics.csv` - **1,680 configurations** (1.1 GB) - Full metrics per config

These files are available locally but excluded from Git due to size.

### Included in Repository
- ✅ `BACKTEST_REPORT.md` - Executive summary and findings
- ✅ `ranking.csv` - Top configurations ranked by composite score (309 KB)
- ✅ `is_oos_analysis.csv` - In-sample vs out-of-sample validation (205 KB)
- ✅ `all_trades_sample.csv` - First 1,000 trades as sample

## Key Findings

**Total Executed:** 1,089,827 trades across 1,680 configurations

**Top Configuration:**
- Symbol: LINK_USDT
- Timeframe: 1h  
- HiLo Period: 20
- Variant: A
- Expectancy: **0.385R**
- Profit Factor: **1.42**
- Return: **+82.7%**
- Max Drawdown: 20.8%
- Trades: 1,809

**Positive Edge:** 65 configurations showed positive expectancy after fees and 0.05% slippage

See `BACKTEST_REPORT.md` for complete analysis.
