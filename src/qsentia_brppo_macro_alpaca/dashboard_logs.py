from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .rebalance import PlannedOrder
from .strategy import StrategySignal


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.exists() else "w"
    with path.open(mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if mode == "w":
            writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def _json_string(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _position_rows(positions: list[dict[str, Any]], timestamp_utc: str, date_key: str) -> list[dict[str, Any]]:
    return [
        {
            "timestamp_utc": timestamp_utc,
            "date": date_key,
            "symbol": position.get("symbol"),
            "qty": position.get("qty"),
            "market_value": position.get("market_value"),
            "current_price": position.get("current_price"),
            "unrealized_pl": position.get("unrealized_pl"),
            "side": position.get("side"),
        }
        for position in positions
    ]


def _planned_order_rows(
    orders: list[PlannedOrder],
    timestamp_utc: str,
    date_key: str,
    submitted: bool,
) -> list[dict[str, Any]]:
    return [
        {
            "timestamp_utc": timestamp_utc,
            "date": date_key,
            "symbol": order.symbol,
            "side": order.side,
            "notional": order.notional,
            "qty": order.qty,
            "current_weight": order.current_weight,
            "target_weight": order.target_weight,
            "reason": order.reason,
            "submitted": str(submitted).lower(),
        }
        for order in orders
    ]


def _submitted_order_rows(
    submitted_orders: list[dict[str, Any]],
    timestamp_utc: str,
    date_key: str,
) -> list[dict[str, Any]]:
    return [
        {
            "timestamp_utc": timestamp_utc,
            "date": date_key,
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "notional": order.get("notional"),
            "qty": order.get("qty"),
            "status": order.get("status"),
            "id": order.get("id"),
            "client_order_id": order.get("client_order_id"),
            "submitted": "true",
        }
        for order in submitted_orders
    ]


def write_dashboard_logs(
    out_dir: str | Path,
    payload: dict[str, Any],
    signal: StrategySignal,
    orders: list[PlannedOrder],
    submitted_orders: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    account: dict[str, Any] | None,
) -> None:
    out = Path(out_dir)
    timestamp_utc = str(payload["timestamp_utc"])
    date_key = str(payload["asof"])
    status = str(payload["status"])
    account_status = "connected" if status == "submitted" else status
    equity = float(payload["equity"])

    portfolio_row = {
        "timestamp_utc": timestamp_utc,
        "date": date_key,
        "net_liquidation": equity,
        "net_liquidation_value": equity,
        "portfolio_value": equity,
        "equity": equity,
        "cash": account.get("cash") if account else "",
        "buying_power": account.get("buying_power") if account else "",
        "account_status": account_status,
        "source": "alpaca_account_equity" if account else "dry_run_equity",
    }
    portfolio_fields = list(portfolio_row)
    _write_csv(out / "portfolio" / "portfolio.csv", [portfolio_row], portfolio_fields, append=True)

    target_rows = [
        {
            "timestamp_utc": timestamp_utc,
            "date": date_key,
            "ticker": ticker,
            "target_weight": weight,
            "score": signal.scores.get(ticker, ""),
            "selected": str(ticker in signal.selected_assets).lower(),
        }
        for ticker, weight in signal.target_weights.items()
    ]
    target_fields = ["timestamp_utc", "date", "ticker", "target_weight", "score", "selected"]
    _write_csv(out / "target_weights" / "latest_target_weights.csv", target_rows, target_fields)
    _write_csv(out / "target_weights" / "target_weights.csv", target_rows, target_fields, append=True)

    decision_row = {
        "timestamp_utc": timestamp_utc,
        "date": date_key,
        "action": status,
        "signal": "macro_rotation",
        "selected_assets": "|".join(signal.selected_assets),
        "target_weights_json": _json_string(signal.target_weights),
        "orders_count": len(orders),
        "submitted_order_count": len(submitted_orders),
        "portfolio_value": equity,
        "net_liquidation": equity,
        "account_status": account_status,
        "warnings": "|".join(str(w) for w in payload.get("warnings", [])),
    }
    decision_fields = list(decision_row)
    _write_csv(out / "decisions" / "latest_decision.csv", [decision_row], decision_fields)
    _write_csv(out / "decisions" / "decisions.csv", [decision_row], decision_fields, append=True)

    position_rows = _position_rows(positions, timestamp_utc, date_key)
    position_fields = ["timestamp_utc", "date", "symbol", "qty", "market_value", "current_price", "unrealized_pl", "side"]
    _write_csv(out / "positions" / "latest_positions.csv", position_rows, position_fields)

    planned_rows = _planned_order_rows(orders, timestamp_utc, date_key, status == "submitted")
    planned_fields = [
        "timestamp_utc",
        "date",
        "symbol",
        "side",
        "notional",
        "qty",
        "current_weight",
        "target_weight",
        "reason",
        "submitted",
    ]
    _write_csv(out / "orders" / "latest_planned_orders.csv", planned_rows, planned_fields)

    submitted_rows = _submitted_order_rows(submitted_orders, timestamp_utc, date_key)
    submitted_fields = ["timestamp_utc", "date", "symbol", "side", "notional", "qty", "status", "id", "client_order_id", "submitted"]
    _write_csv(out / "orders" / "latest_submitted_orders.csv", submitted_rows, submitted_fields)
    if submitted_rows:
        _write_csv(out / "orders" / "submitted_orders.csv", submitted_rows, submitted_fields, append=True)

    health = {
        "updated_at_utc": timestamp_utc,
        "date": date_key,
        "overall_status": account_status,
        "account_status": account_status,
        "net_liquidation": equity,
        "net_liquidation_value": equity,
        "portfolio_value": equity,
        "equity": equity,
        "source": "alpaca_account_equity" if account else "dry_run_equity",
        "selected_assets": signal.selected_assets,
        "target_weights": signal.target_weights,
        "submitted_order_count": len(submitted_orders),
        "paper_base_url": payload.get("paper_base_url"),
    }
    (out / "health").mkdir(parents=True, exist_ok=True)
    (out / "health" / "health_status.json").write_text(json.dumps(health, indent=2), encoding="utf-8")

    signal_row = {
        "timestamp_utc": timestamp_utc,
        "date": date_key,
        "account_status": account_status,
        "net_liquidation": equity,
        "portfolio_value": equity,
        "selected_assets": "|".join(signal.selected_assets),
        "predicted_vol": signal.predicted_vol,
        "target_weights_json": _json_string(signal.target_weights),
        "regime_json": _json_string(signal.regime),
    }
    signal_fields = list(signal_row)
    _write_csv(out / "health" / "signal_history.csv", [signal_row], signal_fields, append=True)
