from __future__ import annotations

import numpy as np
import pandas as pd

from qsentia_brppo_macro_alpaca.config import load_strategy_config
from qsentia_brppo_macro_alpaca.rebalance import build_rebalance_plan
from qsentia_brppo_macro_alpaca.strategy import compute_signal


def _prices() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    index = pd.bdate_range("2020-01-02", "2026-05-20")
    tickers = ["GLD", "SMH", "QQQ", "XLK", "XLE", "UUP", "TLT", "IEF", "SGOV", "SPY", "HYG", "LQD"]
    returns = pd.DataFrame(rng.normal(0.0002, 0.008, size=(len(index), len(tickers))), index=index, columns=tickers)
    returns["GLD"] += np.linspace(0.0, 0.0004, len(index))
    returns["SGOV"] = 0.00018
    return 100.0 * (1.0 + returns).cumprod()


def _macro(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "DFII10": np.linspace(1.8, 1.0, len(index)),
            "T10YIE": np.linspace(2.0, 2.4, len(index)),
            "BAMLH0A0HYM2": np.linspace(4.0, 3.0, len(index)),
            "VIXCLS": np.full(len(index), 16.0),
            "DTWEXBGS": np.linspace(120.0, 112.0, len(index)),
        },
        index=index,
    )


def test_compute_signal_returns_cash_filled_long_only_weights() -> None:
    prices = _prices()
    cfg = load_strategy_config()
    signal = compute_signal(prices, _macro(prices.index), cfg)

    assert signal.asof == "2026-05-20"
    assert 0.999 <= sum(signal.target_weights.values()) <= 1.001
    assert all(weight >= 0.0 for weight in signal.target_weights.values())
    assert set(signal.target_weights).issubset(set(cfg.assets) | {cfg.cash_asset})
    assert len([x for x in signal.selected_assets if x != cfg.cash_asset]) <= cfg.top_k


def test_build_rebalance_plan_uses_thresholds_and_caps() -> None:
    prices = _prices()
    cfg = load_strategy_config()
    signal = compute_signal(prices, _macro(prices.index), cfg)
    latest = prices.ffill().iloc[-1]

    orders, warnings = build_rebalance_plan(
        target_weights=signal.target_weights,
        account_equity=1_000_000.0,
        positions=[],
        latest_prices=latest,
        cfg=cfg,
    )

    assert orders
    assert all(order.side == "buy" for order in orders)
    assert all(order.notional <= 1_000_000.0 for order in orders)
    assert isinstance(warnings, list)
