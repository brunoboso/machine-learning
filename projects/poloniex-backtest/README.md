# Poloniex SPOT Backtesting System

Complete, auditable Python backtesting system for crypto SPOT trading on Poloniex (USDT pairs only).

**Strategy:** 1-2-3 Pattern + HiLo Activator  
**Goal:** ROBUSTNESS validation (anti-overfitting), NOT maximizing historical profit  
**Market:** Poloniex SPOT, USDT pairs only

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Strategy Description](#strategy-description)
3. [Market Rules](#market-rules)
4. [Technical Implementation](#technical-implementation)
5. [Assumptions](#assumptions)
6. [Usage](#usage)
7. [Results](#results)

---

## Quick Start

### Installation

```bash
cd projects/poloniex-backtest
pip install -r requirements.txt
```

### Smoke Test (BTC_USDT, 1h, HiLo 30)

```bash
python main.py --smoke-only
```

This will:
- Download BTC_USDT 1h candles (12 months)
- Detect all 1-2-3 setups with HiLo 30 Variant A
- Print first 20 setups with full details
- Save results to `results/smoke_btc_usdt_1h_hilo30.md` and CSV

### Full Backtest (All Parameters)

```bash
python main.py
```

This will:
1. Run smoke test first (for auditability)
2. Download all liquid USDT pairs (24h volume >= $10M)
3. Run complete parameter grid (timeframes, HiLo periods, variants, expirations, slippage)
4. Generate comprehensive results and report

**Quick mode** (reduced parameters, faster):
```bash
python main.py --quick
```

**Skip smoke test** (if already validated):
```bash
python main.py --skip-smoke
```

---

## Strategy Description

### HiLo Activator (Deterministic Formula)

The HiLo Activator is a trend-following indicator with explicit, auditable logic:

**Formula:**

```
up[i] = SMA(high, period)
down[i] = SMA(low, period)

HiLo[i] = up[i]   if close[i] > HiLo[i-1]
          down[i] if close[i] <= HiLo[i-1]
```

**Bootstrap:** `HiLo[first_valid] = down[first_valid]` (start bearish assumption)

**Direction (Variant A):**
- LONG if `close > HiLo`
- SHORT if `close < HiLo`

**Direction + Slope (Variant B):**
- LONG if `close > HiLo` AND `HiLo[t] > HiLo[t-1]`
- SHORT if `close < HiLo` AND `HiLo[t] < HiLo[t-1]`

**Periods Tested:** 10, 15, 20, 25, 30, 40, 50  
**Benchmark Period:** 30

### 1-2-3 Pattern (Fully Objective)

**LONG Pattern:**
1. Three consecutive candles
2. Candle 2 has lowest low: `low2 < low1` AND `low2 < low3`
3. Armed after close of candle 3
4. Entry: Break above `high3` on any subsequent bar
5. Stop: `low2`
6. Target: `entry + 3 × risk` (where risk = `entry - stop`)

**SHORT Pattern:**
1. Three consecutive candles
2. Candle 2 has highest high: `high2 > high1` AND `high2 > high3`
3. Armed after close of candle 3
4. Entry: Break below `low3` on any subsequent bar
5. Stop: `high2`
6. Target: `entry - 3 × risk`

**Rejection Rules:**
- Reject if stop > 5% of entry price → `REJECTED_STOP_TOO_WIDE`
- DO NOT clip stop to 5% (reject entire setup)

**Expiration:**
- Test: 3, 5, 10 bars after arming
- Also test: No expiration (setup stays active)
- Expired setups → `EXPIRED_SETUP`

**Intrabar Conflict:**
- If same bar hits both stop and target → stop executes first (conservative)
- Exit reason: `AMBIGUOUS_STOP_FIRST`
- Count tracked separately

---

## Market Rules

### Poloniex SPOT Only

- **Quote Currency:** USDT only
- **No:** BTC-quoted, USDC, ETH-quoted, futures, margin, leverage
- **Market Type:** SPOT

### Liquidity Filter

**Requirement:** 24h quote volume >= $10,000,000 USDT

**Method:** Rolling 24h sum of `quoteVolume` from candle data  
**Anti-Survivorship:** Applied historically bar-by-bar when possible

**Alternative Thresholds (for analysis):**
- $10M (primary)
- $25M (higher liquidity)
- $50M (very high liquidity)

### Historical Data

- **Initial Depth:** 12 months (365 days)
- **Optional:** 24 months if feasible
- **Timeframes:** 15m, 30m, 1h, 4h

### Poloniex API

**Base URL:** `https://api.poloniex.com`

**Endpoints Used:**
- `/markets` - List all markets
- `/markets/{symbol}/candles` - OHLCV candles
- `/markets/{symbol}/ticker24h` - 24h ticker data

**Candle Format:** `[timestamp, open, high, low, close, volume, quoteVolume]`

---

## Technical Implementation

### Architecture

```
config.py           - All configuration, constants, dataclasses
download_data.py    - Poloniex API, Parquet caching, data validation
indicators.py       - HiLo Activator, ATR, SMA computations
patterns.py         - 1-2-3 pattern detection (long/short)
portfolio.py        - Position management, capital allocation
backtest.py         - Main backtest engine, execution loop
metrics.py          - Performance statistics, ranking
main.py             - Entry point, smoke test, full grid
```

### Data Pipeline

1. **Download:** Poloniex API → OHLCV candles
2. **Cache:** Parquet format with Snappy compression
3. **Validate:** Check duplicates, gaps, invalid OHLC
4. **Indicators:** Add HiLo, ATR, volume rolling sum
5. **Patterns:** Scan for 1-2-3 setups
6. **Backtest:** Simulate trades with portfolio constraints
7. **Metrics:** Calculate performance statistics

### Portfolio Rules

- **Initial Capital:** $100 USDT
- **Max Position Size:** $10 USDT per trade
- **Max Positions:** 5 simultaneous
- **Cash Reserve:** >= 50% of equity
- **Max Exposure:** <= 50% of equity

**Position Sizing (Main):** Fixed $10 USDT (or 10% equity, whichever is lower)  
**Alternative (Separate Analysis):** Risk-based 0.5% and 1% of equity

### Costs

**Fees (Poloniex Conservative Estimates):**
- Maker: 0.10%
- Taker: 0.20%
- Applied on entry and exit

**Slippage Scenarios:**
- 0.00% (no slippage)
- 0.05% (moderate)
- 0.10% (conservative)

Slippage applied unfavorably:
- LONG entry: buy at `price × (1 + slippage)`
- LONG exit: sell at `price × (1 - slippage)`
- SHORT entry: sell at `price × (1 - slippage)`
- SHORT exit: buy at `price × (1 + slippage)`

### Anti-Lookahead Measures

✅ **Enforced:**
- Indicators computed only from available bars
- Entry requires break AFTER setup bar
- No same-bar entry using future high/low
- Historical liquidity filter (24h volume from past bars)
- Chronological execution order

❌ **Prohibited:**
- Future data access
- Same-bar setup + entry
- Survivorship bias (delisted coins)
- Unrealistic execution assumptions

---

## Assumptions

### ASSUMPTION 1: HiLo Bootstrap

**Issue:** First HiLo value needs initialization.  
**Decision:** Start with `down` line (bearish assumption).  
**Rationale:** Conservative, doesn't assume bullish trend from start.  
**Alternative:** Could start with `up` line or wait for first crossover.

### ASSUMPTION 2: Liquidity Measurement

**Issue:** Poloniex API may not have historical 24h ticker data.  
**Decision:** Use rolling 24h sum of `quoteVolume` from candle data.  
**Rationale:** Approximates 24h volume using available data.  
**Note:** If `quoteVolume` unavailable, approximate as `volume × close`.

### ASSUMPTION 3: Intrabar Execution

**Issue:** If both stop and target hit within same candle, which executes first?  
**Decision:** Stop executes first (conservative assumption).  
**Rationale:** Protects against optimistic P&L inflation.  
**Tracking:** Count as `AMBIGUOUS_STOP_FIRST` in exit reasons.

### ASSUMPTION 4: SHORT on SPOT

**Issue:** Poloniex SPOT may not support short selling.  
**Decision:** Include SHORT trades in backtest for statistical analysis.  
**Rationale:** Shows pattern behavior in both directions.  
**Warning:** SHORT trades are THEORETICAL for SPOT; only LONG trades may be executable.

### ASSUMPTION 5: Setup Expiration

**Issue:** How long should a setup remain valid?  
**Decision:** Test multiple expirations (3, 5, 10 bars) + no expiration.  
**Rationale:** Evaluate freshness vs. opportunity loss trade-off.  
**Comparison:** Report all variants to assess impact.

---

## Usage

### Command-Line Options

```bash
# Smoke test only (first 20 setups, no full grid)
python main.py --smoke-only

# Full backtest (smoke + complete parameter grid)
python main.py

# Quick mode (reduced parameters, faster)
python main.py --quick

# Skip smoke test (if already validated)
python main.py --skip-smoke

# Limit number of symbols (for testing)
python main.py --max-symbols 5
```

### Output Files

```
results/
├── smoke_btc_usdt_1h_hilo30.md          # Smoke test report (Markdown)
├── smoke_btc_usdt_1h_hilo30_setups.csv  # Smoke test setups (CSV)
├── trades/
│   └── all_trades.csv                   # All executed trades
├── metrics/
│   ├── all_metrics.csv                  # All configuration metrics
│   ├── ranking.csv                      # Configurations ranked by score
│   └── is_oos_analysis.csv              # In-sample vs. out-of-sample
└── BACKTEST_REPORT.md                   # Final comprehensive report
```

### Trade Log Fields

Each trade record includes:

```python
symbol, timeframe, hilo_period, hilo_variant,
setup_timestamp, entry_timestamp, exit_timestamp,
direction, entry_price, stop_price, target_price, exit_price,
stop_percent, risk_usdt, position_usdt,
fees, slippage, gross_pnl, net_pnl, r_multiple,
exit_reason, volume_24h, atr_pct, hilo_value, hilo_slope
```

### Metrics Calculated

- **Trade Stats:** count, win rate, profit factor, expectancy (R and USDT)
- **Returns:** net P&L, total return %, max/avg drawdown
- **Risk-Adjusted:** Sharpe, Sortino, Calmar ratios
- **Win/Loss:** avg win, avg loss, payoff ratio, streaks
- **Execution:** targets hit, stops hit, duration, exit reasons
- **Warnings:** Low sample size flag (<50 trades)

---

## Results

### Smoke Test Output

The smoke test produces:

1. **Console Output:** First 20 setups with full details
2. **Markdown Report:** Formatted audit trail
3. **CSV File:** Setup data for spreadsheet analysis

**Example Setup:**

```
Setup #1 - LONG:
  Candle 1: 2024-01-15 10:00 | Low: 42150.00, High: 42380.00
  Candle 2: 2024-01-15 11:00 | Low: 41980.00, High: 42200.00  ← Lowest low
  Candle 3: 2024-01-15 12:00 | Low: 42050.00, High: 42420.00
  Entry trigger: 42420.00 (break high3)
  Stop: 41980.00 (1.04%)
  Target: 43740.00 (3R = +3.11%)
  HiLo: 42100.50, Direction: 1 (Long), Slope: 0.0012
  Volume 24h: $15,234,567 USDT
  Status: ARMED (ready for entry)
```

### Full Backtest Output

1. **All Trades CSV:** Complete trade log across all configurations
2. **Metrics CSV:** Performance statistics per configuration
3. **Ranking CSV:** Sorted by composite score
4. **IS/OOS Analysis:** In-sample vs. out-of-sample comparison
5. **Final Report:** Markdown with findings and recommendations

### Composite Ranking Score

Configurations ranked by weighted score:

- **30%** Expectancy (R-multiple)
- **25%** Profit Factor
- **20%** Drawdown (inverse penalty)
- **15%** Total Return
- **10%** Trade Count (sample size)
- **Penalty:** 0.5× if <50 trades, 0.8× if <100 trades

**Goal:** Find stable, robust configurations, NOT isolated peaks.

---

## Validation & Anti-Overfitting

### In-Sample / Out-of-Sample

- **Split:** 70% in-sample, 30% out-of-sample (chronological)
- **Method:** Select best configs on IS, validate on OOS
- **Warning:** Large IS/OOS performance gap indicates overfitting

### Walk-Forward Analysis

- **Train Window:** 6 months
- **Test Window:** 2 months
- **Method:** Rolling forward, retrain parameters each iteration

### Plateau Detection

- **Goal:** Find parameter regions (e.g., HiLo 20-30) with similar performance
- **Warning:** Isolated peaks (single best parameter) suggest curve fitting
- **Heatmaps:** Visualize HiLo period × timeframe for key metrics

### Multiple Volume Thresholds

Test liquidity filters: $10M, $25M, $50M  
**Robust strategy:** Should work across liquidity tiers

### ATR Quartile Analysis

Segment trades by ATR% to assess volatility regime dependency

---

## Paper Trading Configuration

**Only recommend if:**
✅ Positive expectancy after fees and slippage  
✅ Stable performance across parameter range (plateau)  
✅ OOS validation confirms IS results  
✅ Sufficient trade count (>200 aggregate)  
✅ Acceptable drawdown (<20%)

**If criteria met, provide:**
- Exact parameters (symbol, timeframe, HiLo period, variant)
- Position sizing rules
- Risk management settings
- Monitoring plan

**If criteria NOT met:**
⚠️ **DO NOT PROCEED TO LIVE TRADING**  
Report negative conclusion honestly.

---

## Contact & License

This backtesting system is provided for educational and research purposes.

**No warranty:** Past performance does not guarantee future results.  
**No recommendation:** This is NOT trading advice.  
**Use at own risk:** Trading crypto carries substantial risk of loss.

---

## Changelog

### Version 1.0 (Initial Release)
- Complete modular backtesting system
- HiLo Activator (variants A and B)
- 1-2-3 pattern detection
- Poloniex API integration with Parquet caching
- Comprehensive metrics and ranking
- IS/OOS split analysis
- Smoke test for manual audit
- Full parameter grid sweep
- Markdown reporting

---

**End of Documentation**
