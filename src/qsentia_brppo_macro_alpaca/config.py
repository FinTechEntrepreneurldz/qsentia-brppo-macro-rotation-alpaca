from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "frozen_strategy.json"


@dataclass(frozen=True)
class StrategyConfig:
    strategy_id: str
    assets: tuple[str, ...]
    cash_asset: str
    regime_tickers: tuple[str, ...]
    momentum_windows: tuple[int, ...]
    vol_window: int
    top_k: int
    target_vol: float
    max_asset_weight: float
    score_floor: float
    risk_on_equity_bonus: float
    risk_off_equity_penalty: float
    gold_trend_bonus: float
    gold_risk_off_bonus: float
    usd_trend_bonus: float
    rates_trend_bonus: float
    min_trade_notional: float
    rebalance_threshold_bps: float
    max_trade_notional_pct: float
    portfolio_scale: float

    @property
    def required_price_symbols(self) -> tuple[str, ...]:
        symbols = list(self.assets) + [self.cash_asset] + list(self.regime_tickers)
        return tuple(dict.fromkeys(symbols))


def _tuple(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def load_strategy_config(path: str | Path = DEFAULT_CONFIG_PATH) -> StrategyConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return StrategyConfig(
        strategy_id=str(raw["strategy_id"]),
        assets=tuple(str(x) for x in _tuple(raw["assets"])),
        cash_asset=str(raw["cash_asset"]),
        regime_tickers=tuple(str(x) for x in _tuple(raw.get("regime_tickers", []))),
        momentum_windows=tuple(int(x) for x in _tuple(raw["momentum_windows"])),
        vol_window=int(raw["vol_window"]),
        top_k=int(raw["top_k"]),
        target_vol=float(raw["target_vol"]),
        max_asset_weight=float(raw["max_asset_weight"]),
        score_floor=float(raw["score_floor"]),
        risk_on_equity_bonus=float(raw["risk_on_equity_bonus"]),
        risk_off_equity_penalty=float(raw["risk_off_equity_penalty"]),
        gold_trend_bonus=float(raw["gold_trend_bonus"]),
        gold_risk_off_bonus=float(raw["gold_risk_off_bonus"]),
        usd_trend_bonus=float(raw["usd_trend_bonus"]),
        rates_trend_bonus=float(raw["rates_trend_bonus"]),
        min_trade_notional=float(os.getenv("QSENTIA_MIN_TRADE_NOTIONAL", raw["min_trade_notional"])),
        rebalance_threshold_bps=float(os.getenv("QSENTIA_REBALANCE_THRESHOLD_BPS", raw["rebalance_threshold_bps"])),
        max_trade_notional_pct=float(os.getenv("QSENTIA_MAX_TRADE_NOTIONAL_PCT", raw["max_trade_notional_pct"])),
        portfolio_scale=float(os.getenv("QSENTIA_PORTFOLIO_SCALE", raw["portfolio_scale"])),
    )

