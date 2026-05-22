from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests


FRED_SERIES = {
    "DFII10": "10-year real yield",
    "T10YIE": "10-year breakeven inflation",
    "DGS10": "10-year Treasury yield",
    "DTWEXBGS": "broad trade-weighted USD",
    "VIXCLS": "CBOE VIX",
    "BAMLH0A0HYM2": "US high-yield OAS",
}


def fetch_fred_macro() -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for series_id in FRED_SERIES:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        frame = pd.read_csv(url).rename(columns={"observation_date": "date"})
        frame["date"] = pd.to_datetime(frame["date"])
        frame[series_id] = pd.to_numeric(frame[series_id].replace(".", pd.NA), errors="coerce")
        frame = frame[["date", series_id]]
        merged = frame if merged is None else merged.merge(frame, on="date", how="outer")
    if merged is None:
        raise RuntimeError("No FRED data fetched.")
    merged = merged.sort_values("date").ffill().set_index("date")
    merged.index = pd.DatetimeIndex(merged.index).tz_localize(None)
    return merged


def load_or_fetch_fred(path: str | Path | None) -> pd.DataFrame:
    if path is not None and Path(path).exists():
        macro = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
        macro.index = pd.DatetimeIndex(macro.index).tz_localize(None)
        return macro.replace(".", pd.NA).apply(pd.to_numeric, errors="coerce").ffill()
    return fetch_fred_macro()


def read_price_file(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".parquet":
        frame = pd.read_parquet(p).sort_index()
        frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
        return frame.apply(pd.to_numeric, errors="coerce").ffill()
    frame = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
    return frame.apply(pd.to_numeric, errors="coerce").ffill()


def read_price_csv(path: str | Path) -> pd.DataFrame:
    return read_price_file(path)


def write_json(path: str | Path, payload: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")


def assert_http_ok(response: requests.Response) -> None:
    if response.ok:
        return
    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
