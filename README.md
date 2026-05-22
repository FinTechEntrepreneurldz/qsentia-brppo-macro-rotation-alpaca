# QSentia BR-PPO Macro Rotation Alpaca

Paper-trading wrapper for the first credible QSentia BR-PPO macro-rotation Sharpe 2 research family.

This repo is intentionally production-shaped but paper-only by default. It freezes the research lead,
generates daily ETF target weights, builds Alpaca paper orders, writes dashboard-friendly logs, and
can run from GitHub Actions every weekday morning.

## Frozen Candidate

Research lead:

`macro_GLD_SMH_QQQ_XLK_XLE_UUP_TLT_IEF_ME_mom63_126_k2_tv0.1_floor-0.15_g0.75_goff0.35_u0.25_r0.25`

Research metrics from the 2026-05-22 snapshot:

- Train Sharpe: `0.72`
- Validation Sharpe: `0.51`
- OOS Sharpe: `2.06`
- OOS annual return: `17.05%`
- OOS max drawdown: `-3.57%`
- Pre-test fold positive rate: `100%`

This is still a live-paper candidate, not production proof.

## Strategy Universe

- Risk assets: `GLD`, `SMH`, `QQQ`, `XLK`, `XLE`, `UUP`, `TLT`, `IEF`
- Cash-like asset: `SGOV`
- Regime support tickers: `SPY`, `HYG`, `LQD`
- Macro inputs: FRED real yield, breakeven inflation, high-yield OAS, VIX, broad USD

## Local Dry Run

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
PYTHONPATH=src python scripts/run_paper_rebalance.py --equity 1000000
```

To dry-run from the existing local research cache:

```bash
PYTHONPATH=src python scripts/run_paper_rebalance.py \
  --price-file ../leveraged_etf_oos_gate_results/leveraged_etf_prices.parquet \
  --fred-csv ../qsentia-brppo-multiasset-regime-alpha/data/fred_macro.csv \
  --equity 1000000
```

## Alpaca Paper Trading

Set these secrets or environment variables:

```bash
export APCA_API_KEY_ID="..."
export APCA_API_SECRET_KEY="..."
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
export ALPACA_DATA_FEED="iex"
```

Submit to paper:

```bash
PYTHONPATH=src python scripts/run_paper_rebalance.py --submit
```

Without `--submit`, the script writes a plan and sends no orders.

## GitHub Actions

The included workflow runs at both `13:00` and `14:00` UTC Monday-Friday, then gates internally to
only continue during the 9 AM `America/New_York` window. This handles daylight saving time without
manual cron edits.

Add repository secrets:

- `APCA_API_KEY_ID`
- `APCA_API_SECRET_KEY`
- optional `APCA_API_BASE_URL`

## Outputs

Each run writes:

- `logs/latest_signal.json`
- `logs/latest_orders.csv`
- `logs/rebalance_<timestamp>.json`

## Safety Gates

- Dry-run by default.
- No shorting.
- Max single asset weight inherited from the frozen config.
- Max per-run trade notional cap.
- Min trade size and rebalance threshold.
- Paper base URL defaults to `https://paper-api.alpaca.markets`.
