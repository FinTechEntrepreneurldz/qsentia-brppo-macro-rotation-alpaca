from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .config import StrategyConfig


@dataclass(frozen=True)
class PlannedOrder:
    symbol: str
    side: str
    notional: float
    qty: float
    current_weight: float
    target_weight: float
    reason: str


def position_market_values(positions: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for position in positions:
        symbol = str(position["symbol"])
        values[symbol] = float(position.get("market_value") or 0.0)
    return values


def build_rebalance_plan(
    target_weights: dict[str, float],
    account_equity: float,
    positions: list[dict[str, Any]],
    latest_prices: pd.Series,
    cfg: StrategyConfig,
) -> tuple[list[PlannedOrder], list[str]]:
    warnings: list[str] = []
    current_values = position_market_values(positions)
    portfolio_scale = max(0.0, min(float(cfg.portfolio_scale), 1.0))
    effective_equity = float(account_equity) * portfolio_scale
    threshold = max(float(cfg.min_trade_notional), float(account_equity) * float(cfg.rebalance_threshold_bps) / 10000.0)
    max_trade_notional = float(account_equity) * float(cfg.max_trade_notional_pct)

    orders: list[PlannedOrder] = []
    symbols = sorted(set(target_weights) | set(current_values))
    allowed = set(target_weights)
    for symbol in symbols:
        if symbol not in allowed and abs(current_values.get(symbol, 0.0)) > threshold:
            warnings.append(f"Existing position {symbol} is outside the frozen strategy universe and was left untouched.")
            continue
        price = float(latest_prices.get(symbol, 0.0) or 0.0)
        if price <= 0:
            warnings.append(f"Skipping {symbol}: missing latest price.")
            continue
        current_value = float(current_values.get(symbol, 0.0))
        current_weight = current_value / float(account_equity) if account_equity > 0 else 0.0
        target_weight = min(max(float(target_weights.get(symbol, 0.0)), 0.0), float(cfg.max_asset_weight))
        target_value = effective_equity * target_weight
        delta = target_value - current_value
        if abs(delta) < threshold:
            continue
        notional = min(abs(delta), max_trade_notional)
        if delta < 0:
            notional = min(notional, abs(current_value))
        if notional < float(cfg.min_trade_notional):
            continue
        qty = notional / price
        orders.append(
            PlannedOrder(
                symbol=symbol,
                side="buy" if delta > 0 else "sell",
                notional=round(float(notional), 2),
                qty=round(float(qty), 6),
                current_weight=float(current_weight),
                target_weight=float(target_weight),
                reason="rebalance_to_target",
            )
        )
        if abs(delta) > max_trade_notional:
            warnings.append(f"Capped {symbol} trade from {abs(delta):.2f} to {max_trade_notional:.2f}.")
    return orders, warnings


def orders_to_frame(orders: list[PlannedOrder]) -> pd.DataFrame:
    return pd.DataFrame([order.__dict__ for order in orders])

