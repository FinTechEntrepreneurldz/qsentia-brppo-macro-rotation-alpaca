from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .config import StrategyConfig


TRADING_DAYS = 252


@dataclass(frozen=True)
class StrategySignal:
    asof: str
    target_weights: dict[str, float]
    scores: dict[str, float]
    selected_assets: list[str]
    regime: dict[str, bool]
    predicted_vol: float


def _diagonal_portfolio_vol(asset_vol: pd.Series, weights: pd.Series) -> float:
    if weights.empty or float(weights.abs().sum()) <= 0:
        return 0.20
    vol = asset_vol.reindex(weights.index).replace([np.inf, -np.inf], np.nan).fillna(0.20).clip(lower=0.01)
    diagonal = float(np.sqrt(np.square(weights.to_numpy(dtype=float) * vol.to_numpy(dtype=float)).sum()))
    return diagonal * 1.45


def _trend(prices: pd.DataFrame, ticker: str, ma_window: int = 100, mom_window: int = 126) -> pd.Series:
    if ticker not in prices:
        return pd.Series(False, index=prices.index)
    return (prices[ticker] > prices[ticker].rolling(ma_window).mean()) & (prices[ticker].pct_change(mom_window) > 0)


def risk_regime(prices: pd.DataFrame) -> pd.DataFrame:
    idx = prices.index
    spy = prices["SPY"] if "SPY" in prices else prices.iloc[:, 0]
    risk_on = spy > spy.rolling(200).mean()
    if {"HYG", "LQD"}.issubset(prices.columns):
        credit = (prices["HYG"] / prices["LQD"]).pct_change(63)
        risk_on &= credit > -0.03
    shock = (spy.pct_change(21) < -0.08) | (spy < spy.rolling(50).mean() * 0.92)
    return pd.DataFrame({"risk_on": risk_on.fillna(False), "shock": shock.fillna(False)}, index=idx)


def macro_regime(prices: pd.DataFrame, macro_history: pd.DataFrame | None) -> pd.DataFrame:
    idx = prices.index
    credit_ok = pd.Series(False, index=idx)
    if {"HYG", "LQD"}.issubset(prices.columns):
        credit_ok = (prices["HYG"] / prices["LQD"]).pct_change(63) > 0

    frame = pd.DataFrame(
        {
            "gold_trend": _trend(prices, "GLD"),
            "usd_trend": _trend(prices, "UUP"),
            "rates_trend": _trend(prices, "TLT") | _trend(prices, "IEF"),
            "semis_trend": _trend(prices, "SMH") | _trend(prices, "QQQ"),
            "credit_ok": credit_ok.fillna(False),
        },
        index=idx,
    ).fillna(False)

    for column in [
        "real_yield_down",
        "real_yield_up",
        "breakeven_up",
        "macro_credit_stress",
        "vix_stress",
        "broad_usd_up",
        "broad_usd_down",
    ]:
        frame[column] = False

    if macro_history is None or macro_history.empty:
        return frame

    macro = macro_history.reindex(idx).ffill()
    if "DFII10" in macro:
        real_yield_delta = macro["DFII10"].diff(63)
        frame["real_yield_down"] = (real_yield_delta < -0.20).fillna(False)
        frame["real_yield_up"] = (real_yield_delta > 0.20).fillna(False)
    if "T10YIE" in macro:
        frame["breakeven_up"] = (macro["T10YIE"].diff(63) > 0.15).fillna(False)
    if "BAMLH0A0HYM2" in macro:
        hy_spread = macro["BAMLH0A0HYM2"]
        frame["macro_credit_stress"] = ((hy_spread.diff(63) > 0.75) | (hy_spread > hy_spread.rolling(504).quantile(0.80))).fillna(False)
    if "VIXCLS" in macro:
        frame["vix_stress"] = ((macro["VIXCLS"] > 24.0) | (macro["VIXCLS"].pct_change(21) > 0.35)).fillna(False)
    if "DTWEXBGS" in macro:
        usd_delta = macro["DTWEXBGS"].pct_change(126)
        frame["broad_usd_up"] = (usd_delta > 0.03).fillna(False)
        frame["broad_usd_down"] = (usd_delta < -0.03).fillna(False)
    return frame


def compute_signal(
    prices: pd.DataFrame,
    macro_history: pd.DataFrame | None,
    cfg: StrategyConfig,
    asof: str | pd.Timestamp | None = None,
) -> StrategySignal:
    clean_prices = prices.sort_index().ffill()
    clean_prices.index = pd.DatetimeIndex(clean_prices.index).tz_localize(None)
    dt = clean_prices.index.max() if asof is None else clean_prices.index[clean_prices.index.searchsorted(pd.Timestamp(asof), side="right") - 1]
    available_assets = [x for x in cfg.assets if x in clean_prices.columns]

    returns = clean_prices.pct_change().fillna(0.0)
    score = pd.Series(0.0, index=available_assets)
    for window in cfg.momentum_windows:
        momentum = clean_prices[available_assets].pct_change(window).loc[dt]
        vol = returns[available_assets].rolling(cfg.vol_window).std().mul(np.sqrt(TRADING_DAYS)).loc[dt]
        score = score.add(momentum / vol.replace(0, np.nan), fill_value=0.0)
    score = (score / max(len(cfg.momentum_windows), 1)).replace([np.inf, -np.inf], np.nan).dropna()

    risk = risk_regime(clean_prices).reindex(clean_prices.index).fillna(False)
    macro = macro_regime(clean_prices, macro_history).reindex(clean_prices.index).fillna(False)
    flags = {**risk.loc[dt].astype(bool).to_dict(), **macro.loc[dt].astype(bool).to_dict()}
    macro_risk_off = bool(flags["macro_credit_stress"] or flags["vix_stress"])

    equity_assets = {"SPY", "QQQ", "SMH", "XLK", "XLE", "XLF", "IWM", "XBI"}
    rates_assets = {"TLT", "IEF", "UBT", "TMF"}
    for asset in score.index:
        if asset in equity_assets:
            if flags["risk_on"] and flags["credit_ok"] and not macro_risk_off:
                score.loc[asset] += cfg.risk_on_equity_bonus
            else:
                score.loc[asset] -= cfg.risk_off_equity_penalty
            if asset in {"SMH", "QQQ", "XLK"} and flags["semis_trend"] and flags["risk_on"] and not macro_risk_off:
                score.loc[asset] += cfg.risk_on_equity_bonus * 0.5
        elif asset == "GLD":
            if flags["gold_trend"]:
                score.loc[asset] += cfg.gold_trend_bonus
            if flags["real_yield_down"] or flags["breakeven_up"]:
                score.loc[asset] += cfg.gold_trend_bonus * 0.75
            if flags["real_yield_up"] and not flags["breakeven_up"]:
                score.loc[asset] -= cfg.gold_trend_bonus * 0.5
            if flags["broad_usd_down"]:
                score.loc[asset] += cfg.gold_trend_bonus * 0.25
            if (not flags["risk_on"]) or flags["shock"] or macro_risk_off:
                score.loc[asset] += cfg.gold_risk_off_bonus
        elif asset == "UUP":
            if flags["usd_trend"] or flags["broad_usd_up"]:
                score.loc[asset] += cfg.usd_trend_bonus
            if flags["broad_usd_down"]:
                score.loc[asset] -= cfg.usd_trend_bonus * 0.5
            if flags["shock"] or macro_risk_off:
                score.loc[asset] += cfg.usd_trend_bonus * 0.5
        elif asset in rates_assets:
            if flags["rates_trend"] or flags["real_yield_down"]:
                score.loc[asset] += cfg.rates_trend_bonus
            if flags["real_yield_up"]:
                score.loc[asset] -= cfg.rates_trend_bonus * 0.5

    score = score[score > cfg.score_floor]
    selected = score.sort_values(ascending=False).head(cfg.top_k).index.tolist()
    universe = sorted(set(available_assets + [cfg.cash_asset]))
    weights = pd.Series(0.0, index=universe)
    predicted_vol = 0.0
    if selected:
        vol = returns[selected].rolling(cfg.vol_window).std().mul(np.sqrt(TRADING_DAYS)).loc[dt].replace(0, np.nan)
        inv_vol = (1.0 / vol).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        raw = inv_vol / float(inv_vol.sum()) if float(inv_vol.sum()) > 0 else pd.Series(1.0 / len(selected), index=selected)
        weights.loc[selected] = raw
        asset_vol = returns[weights.index].rolling(cfg.vol_window).std().mul(np.sqrt(TRADING_DAYS)).loc[dt]
        predicted_vol = _diagonal_portfolio_vol(asset_vol, weights[weights > 0])
        weights *= min(1.0, cfg.target_vol / max(predicted_vol, 1e-6))

    weights = weights.clip(lower=0.0, upper=cfg.max_asset_weight)
    if cfg.cash_asset in weights.index and float(weights.sum()) < 1.0:
        weights.loc[cfg.cash_asset] += 1.0 - float(weights.sum())
    weights = weights[weights.abs() > 1e-10].sort_values(ascending=False)

    return StrategySignal(
        asof=str(pd.Timestamp(dt).date()),
        target_weights={k: float(v) for k, v in weights.items()},
        scores={k: float(v) for k, v in score.sort_values(ascending=False).items()},
        selected_assets=selected,
        regime={k: bool(v) for k, v in flags.items()},
        predicted_vol=float(predicted_vol),
    )

