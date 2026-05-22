# Expansion And Paper Gate

The Sharpe 2 research lead should be expanded as a family, not promoted as a single magic config.

## Expansion Path

1. Freeze the current leader as `v1`.
2. Track the six all-fold-positive Sharpe 2 research leads side by side in paper.
3. Add a small ensemble mode only after paper evidence exists: equal weight, validation-score weight, and minimum-turnover weight.
4. Add live-paper diagnostics before any live capital decision:
   - realized versus target weights
   - submitted versus filled notional
   - slippage versus prior close and next open
   - rejected orders
   - turnover and tax-lot churn
   - stale macro data warnings
   - market holiday skips
5. Require a minimum paper observation window before live:
   - 60 trading days minimum
   - no unresolved order failures
   - realized drawdown within the research envelope
   - no persistent signal drift from the frozen backtest implementation

## Current Paper Candidate

`macro_GLD_SMH_QQQ_XLK_XLE_UUP_TLT_IEF_ME_mom63_126_k2_tv0.1_floor-0.15_g0.75_goff0.35_u0.25_r0.25`

The portfolio is long-only and cash-filled with `SGOV`. It uses daily bars, FRED macro features,
monthly-style research logic, and a daily paper gate. Daily execution does not imply daily turnover;
the order builder only trades when drift exceeds the configured threshold.

## Alpaca Paper Notes

- Paper endpoint: `https://paper-api.alpaca.markets`
- Data endpoint: `https://data.alpaca.markets`
- Historical daily stock bars endpoint: `/v2/stocks/bars`
- Orders endpoint: `/v2/orders`
- Market orders submitted at 9 AM New York time may queue for the regular session open. A production
  variant can switch to 9:35 AM or limit orders if open-auction behavior looks noisy in paper.

## Promotion Rule

This repo is allowed to submit paper orders. It should not submit live orders until a separate live
trading repo or branch adds account-specific limits, approvals, and live-only risk controls.

