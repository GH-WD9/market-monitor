"""
calculator.py — Return and spread calculations
Phase 2b: adds FX direction adjustment, commodity and REIT returns
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from config import (
    RETURN_PERIODS, FX_FRED, FX_YFINANCE,
    COMMODITY_YFINANCE,
    REIT_TICKERS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _latest(s: pd.Series):
    """Return (date, value) for the most recent non-NaN observation."""
    if s is None or s.empty:
        return None, None
    s = s.dropna()
    if s.empty:
        return None, None
    return s.index[-1], float(s.iloc[-1])


def _offset_value(s: pd.Series, trading_days: int):
    """
    Return the value trading_days ago from the last observation.
    Uses iloc offset from the tail — standard for equity return calculations.
    """
    s = s.dropna()
    if s.empty or len(s) < 2:
        return None
    idx = -(trading_days + 1)
    if abs(idx) > len(s):
        return None
    return float(s.iloc[idx])


def _pct_return(current, prior) -> float | None:
    """Percentage return between two values."""
    if current is None or prior is None or prior == 0:
        return None
    return (current - prior) / abs(prior)


def _bps_change(current, prior) -> float | None:
    """Absolute basis-point change (values in percent, e.g. 4.50 → 450bps)."""
    if current is None or prior is None:
        return None
    return (current - prior) * 100  # percentage points → bps


# ---------------------------------------------------------------------------
# Equity / REIT / Commodity return stats
# ---------------------------------------------------------------------------

def price_stats(s: pd.Series) -> dict:
    """
    Compute level and all return periods for a price series.
    Returns dict: {period: pct_return, ..., 'level': float, 'date': date, 'error': str|None}
    """
    s = s.dropna()
    if s.empty:
        return {"level": None, "date": None, "error": "no data"}

    date, level = _latest(s)
    result = {"level": level, "date": date, "error": None}

    for label, days in RETURN_PERIODS.items():
        prior = _offset_value(s, days)
        result[label] = _pct_return(level, prior)

    return result


def price_stats_multi(data: dict) -> dict:
    """Apply price_stats to a dict of {key: pd.Series}. Returns {key: stats_dict}."""
    return {k: price_stats(v) for k, v in data.items()}


# ---------------------------------------------------------------------------
# Bond / rate bps stats
# ---------------------------------------------------------------------------

def rate_stats(s: pd.Series) -> dict:
    """
    Compute current level and 1M/3M/1Y bps changes for a rate series (values in %).
    Returns dict: {'level': float, '1M_bps': float, '3M_bps': float, '1Y_bps': float,
                   'date': date, 'is_monthly': bool, 'error': str|None}
    """
    s = s.dropna()
    if s.empty:
        return {"level": None, "date": None, "is_monthly": False, "error": "no data"}

    date, level = _latest(s)
    is_monthly = _detect_monthly(s)
    result = {
        "level": level,
        "date": date,
        "is_monthly": is_monthly,
        "error": None,
    }

    # Index-based offset for daily series; date-based for monthly/sparse (e.g. ECB DFR, OECD monthly)
    if is_monthly:
        lookback_map = {"1M_bps": 35, "3M_bps": 100, "1Y_bps": 380}
        for label, cal_days in lookback_map.items():
            prior = _date_based_offset(s, cal_days)
            result[label] = _bps_change(level, prior)
    else:
        bps_periods = {"1M_bps": 21, "3M_bps": 63, "1Y_bps": 252}
        for label, days in bps_periods.items():
            prior = _offset_value(s, days)
            result[label] = _bps_change(level, prior)

    return result


def _detect_monthly(s: pd.Series) -> bool:
    """Heuristic: if median gap between observations > 20 days → monthly or sparse."""
    if len(s) < 3:
        return False
    gaps = pd.Series(s.index).diff().dropna().dt.days
    return float(gaps.median()) > 20


def _date_based_offset(s: pd.Series, calendar_days: int):
    """
    Get the value approximately calendar_days before the last observation (date-based).
    Used for sparse or monthly series where index-based offset fails.
    Finds the most recent observation at or before (last_date - calendar_days).
    """
    s = s.dropna()
    if s.empty:
        return None
    last_date = s.index[-1]
    target = last_date - pd.Timedelta(days=calendar_days)
    before = s[s.index <= target]
    if before.empty:
        return None
    return float(before.iloc[-1])


def spread_bps(s_long: pd.Series, s_short: pd.Series) -> dict:
    """
    Compute current spread (long - short) and 1M/3M bps changes.
    Aligns series by date before computing.
    """
    try:
        df = pd.concat([s_long.rename("long"), s_short.rename("short")], axis=1).dropna()
    except Exception:
        return {"level": None, "1M_bps": None, "3M_bps": None, "date": None, "error": "alignment failed"}

    if df.empty:
        return {"level": None, "1M_bps": None, "3M_bps": None, "date": None, "error": "no overlapping data"}

    spread = (df["long"] - df["short"]) * 100   # percent → bps
    date, level = _latest(spread)

    bps_periods = {"1M_bps": 21, "3M_bps": 63}
    result = {"level": level, "date": date, "error": None}
    for label, days in bps_periods.items():
        prior = _offset_value(spread, days)
        result[label] = _bps_change(level / 100, prior / 100) if (level is not None and prior is not None) else None
    return result


# ---------------------------------------------------------------------------
# Credit OAS stats
# ---------------------------------------------------------------------------

def oas_stats(s: pd.Series) -> dict:
    """
    Compute OAS level (bps) and changes for a FRED OAS series.
    FRED OAS values are in percent (e.g. 0.92 = 92bps).
    Colour convention: widening=red, tightening=green (inverted vs yields).
    """
    s = s.dropna()
    if s.empty:
        return {"level": None, "date": None, "error": "no data"}

    # Convert from percent to bps
    s_bps = s * 100

    date, level = _latest(s_bps)
    result = {"level": level, "date": date, "error": None}

    bps_periods = {"1M_bps": 21, "3M_bps": 63, "1Y_bps": 252}
    for label, days in bps_periods.items():
        prior = _offset_value(s_bps, days)
        # level and prior are already in bps — subtract directly
        result[label] = round(level - prior, 1) if (level is not None and prior is not None) else None
    return result


# ---------------------------------------------------------------------------
# FX return stats — with direction adjustment
# ---------------------------------------------------------------------------

def fx_stats(data_raw: dict) -> dict:
    """
    Compute FX return stats for all series.
    Applies direction inversion for pairs where natural=False.
    All output expressed as "USD per 1 unit of foreign currency":
      positive % = foreign currency strengthened vs USD.

    Args:
        data_raw: {series_id_or_ticker: pd.Series} from data_fetcher.fetch_fx_data()

    Returns:
        {ccy: stats_dict with all RETURN_PERIODS and is_crypto flag}
    """
    results = {}

    # FRED pairs
    for series_id, meta in FX_FRED.items():
        raw = data_raw.get(series_id)
        if raw is None or raw.empty:
            results[meta["ccy"]] = {"level": None, "date": None, "error": "no data", "ccy": meta["ccy"]}
            continue

        # Direction adjustment: if natural=False, the raw value is X per USD → invert to USD per X
        if meta["natural"]:
            s = raw.dropna()
        else:
            s = (1.0 / raw.dropna())

        stats = price_stats(s)
        stats["ccy"] = meta["ccy"]
        stats["pair"] = meta["pair"]
        stats["is_crypto"] = False
        results[meta["ccy"]] = stats

    # Crypto (yfinance)
    for ticker, meta in FX_YFINANCE.items():
        raw = data_raw.get(ticker)
        if raw is None or raw.empty:
            results[meta["ccy"]] = {"level": None, "date": None, "error": "no data", "ccy": meta["ccy"]}
            continue
        stats = price_stats(raw.dropna())
        stats["ccy"] = meta["ccy"]
        stats["pair"] = meta["pair"]
        stats["is_crypto"] = True
        results[meta["ccy"]] = stats

    return results


# ---------------------------------------------------------------------------
# Commodity return stats
# ---------------------------------------------------------------------------

def commodity_stats(data_raw: dict) -> dict:
    """
    Compute return stats for all commodity series.
    Returns {ticker: stats_dict with name and unit from config}.
    Phase 2k: COMMODITY_FRED retired — all commodities via COMMODITY_YFINANCE.
    """
    from config import COMMODITY_YFINANCE

    results = {}
    for ticker, meta in COMMODITY_YFINANCE.items():
        s = data_raw.get(ticker)
        stats = price_stats(s) if s is not None and not s.empty else {"level": None, "date": None, "error": "no data"}
        stats["name"] = meta["name"]
        stats["unit"] = meta["unit"]
        stats["note"] = meta.get("note", "")
        results[ticker] = stats

    return results


# ---------------------------------------------------------------------------
# REIT return stats
# ---------------------------------------------------------------------------

def reit_stats(data_raw: dict) -> dict:
    """Returns {ticker: stats_dict} for REIT ETFs."""
    results = {}
    for ticker, name in REIT_TICKERS.items():
        s = data_raw.get(ticker)
        stats = price_stats(s) if s is not None and not s.empty else {"level": None, "date": None, "error": "no data"}
        stats["name"] = name
        results[ticker] = stats
    return results
