from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from qsentia_brppo_macro_alpaca.alpaca import AlpacaClient, AlpacaSettings
from qsentia_brppo_macro_alpaca.config import load_strategy_config
from qsentia_brppo_macro_alpaca.data import load_or_fetch_fred, read_price_file
from qsentia_brppo_macro_alpaca.dashboard_logs import write_dashboard_logs
from qsentia_brppo_macro_alpaca.rebalance import build_rebalance_plan, orders_to_frame
from qsentia_brppo_macro_alpaca.strategy import compute_signal


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value)}")


def _inside_market_time_gate(window_minutes: int) -> bool:
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    gate_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    gate_end = gate_start + timedelta(minutes=window_minutes)
    return gate_start <= now <= gate_end


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run QSentia BR-PPO macro rotation Alpaca paper rebalance.")
    parser.add_argument("--submit", action="store_true", help="Submit orders to Alpaca paper. Default is dry-run.")
    parser.add_argument("--price-file", help="Optional local price CSV/parquet with date index/column and ticker columns.")
    parser.add_argument("--price-csv", help="Backward-compatible alias for --price-file.")
    parser.add_argument("--fred-csv", help="Optional local FRED macro CSV with date column.")
    parser.add_argument("--out-dir", default="logs", help="Directory for JSON/CSV logs.")
    parser.add_argument("--equity", type=float, help="Dry-run equity when Alpaca credentials are not available.")
    parser.add_argument("--lookback-days", type=int, default=1500, help="Calendar lookback for Alpaca daily bars.")
    parser.add_argument("--market-time-gate", action="store_true", help="Skip unless running around 9 AM New York time.")
    parser.add_argument("--market-time-window-minutes", type=int, default=50, help="Allowed 9 AM gate window.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.market_time_gate and not _inside_market_time_gate(args.market_time_window_minutes):
        payload = {
            "status": "skipped",
            "reason": "outside 9 AM America/New_York market-time gate",
            "timestamp": datetime.now(ZoneInfo("America/New_York")).isoformat(),
        }
        (out_dir / "latest_signal.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 0

    cfg = load_strategy_config()
    client: AlpacaClient | None = None
    account: dict | None = None
    positions: list[dict] = []
    submit = bool(args.submit or os.getenv("QSENTIA_SUBMIT_ORDERS", "").lower() == "true")

    price_file = args.price_file or args.price_csv
    if price_file:
        prices = read_price_file(price_file)
    else:
        client = AlpacaClient(AlpacaSettings.from_env())
        end = datetime.now(ZoneInfo("America/New_York")).date()
        start = end - timedelta(days=int(args.lookback_days))
        prices = client.get_stock_bars(list(cfg.required_price_symbols), start=start, end=end)

    if client is not None:
        account = client.get_account()
        positions = client.get_positions()
        equity = float(account["equity"])
    else:
        equity = float(args.equity or 1_000_000.0)

    macro = load_or_fetch_fred(args.fred_csv)
    signal = compute_signal(prices=prices, macro_history=macro, cfg=cfg)
    latest_prices = prices.ffill().iloc[-1]
    orders, warnings = build_rebalance_plan(
        target_weights=signal.target_weights,
        account_equity=equity,
        positions=positions,
        latest_prices=latest_prices,
        cfg=cfg,
    )

    submitted_orders = []
    if submit:
        if client is None:
            raise RuntimeError("--submit requires Alpaca credentials and live Alpaca price fetch.")
        for index, order in enumerate(orders, start=1):
            client_order_id = f"{cfg.strategy_id}-{signal.asof}-{index}"
            submitted_orders.append(
                client.submit_market_order(
                    symbol=order.symbol,
                    side=order.side,
                    notional=order.notional,
                    client_order_id=client_order_id,
                )
            )

    order_frame = orders_to_frame(orders)
    order_frame.to_csv(out_dir / "latest_orders.csv", index=False)

    timestamp_ny = datetime.now(ZoneInfo("America/New_York"))
    timestamp_utc = datetime.now(ZoneInfo("UTC"))
    payload = {
        "status": "submitted" if submit else "dry_run",
        "strategy_id": cfg.strategy_id,
        "asof": signal.asof,
        "timestamp": timestamp_ny.isoformat(),
        "timestamp_utc": timestamp_utc.isoformat(),
        "equity": equity,
        "target_weights": signal.target_weights,
        "selected_assets": signal.selected_assets,
        "scores": signal.scores,
        "regime": signal.regime,
        "predicted_vol": signal.predicted_vol,
        "orders": [order.__dict__ for order in orders],
        "submitted_order_count": len(submitted_orders),
        "submitted_orders": submitted_orders,
        "warnings": warnings,
        "alpaca_account_id": account.get("id") if account else None,
        "paper_base_url": os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets"),
    }
    write_dashboard_logs(out_dir, payload, signal, orders, submitted_orders, positions, account)
    stamp = timestamp_ny.strftime("%Y%m%d_%H%M%S")
    (out_dir / "latest_signal.json").write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    (out_dir / f"rebalance_{stamp}.json").write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ["status", "asof", "equity", "target_weights", "submitted_order_count", "warnings"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
