"""
validator.py — Data quality validation rules
Phase 2b: all geographies, OAS, FX, crypto outlier thresholds
Phase 2k: commodity stale threshold split from FX — STALE_DAYS_COMMODITY=2 (yfinance daily)
"""

import logging
from datetime import datetime, date, timedelta

import pandas as pd

from config import (
    STALE_DAYS, STALE_DAYS_WEEKLY, STALE_DAYS_COMMODITY,
    OUTLIER_EQUITY, OUTLIER_YIELD, OUTLIER_OAS, OUTLIER_BTC,
    EQUITY_INDICES, STRESS_TICKERS, REIT_TICKERS,
    COMMODITY_YFINANCE,
    FX_FRED, FX_YFINANCE,
    CREDIT_FRED_SERIES,
    now_report, today_report,   # Phase 4f: report timezone, never the runner's clock
)
from holidays_calendar import get_holiday_name
from market_sessions import (
    CONTINUOUS, expected_session_date, series_venue,
    venue_closed as _venue_closed,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flag types
# ---------------------------------------------------------------------------
FLAG_STALE   = "⚠️ STALE"
FLAG_HOLIDAY = "ℹ️ CLOSED"
FLAG_OUTLIER = "⚠️ VERIFY"
FLAG_MISSING = "N/A"
FLAG_UNAVAIL = "DATA UNAVAILABLE"


# ---------------------------------------------------------------------------
# Core check functions
# ---------------------------------------------------------------------------

def check_staleness(s: pd.Series, geography: str = "global", max_days: int = None) -> str | None:
    """Return FLAG_STALE string if data is older than max_days calendar days."""
    threshold = max_days if max_days is not None else STALE_DAYS
    if s is None or s.empty:
        return None
    last_date = s.dropna().index[-1].date() if not s.dropna().empty else None
    if last_date is None:
        return None
    age = (today_report() - last_date).days
    if age > threshold:
        return f"{FLAG_STALE} — last updated {last_date}"
    return None


def last_observation_date(s: pd.Series) -> date | None:
    """Date of the newest non-null observation, or None."""
    if s is None or not isinstance(s, pd.Series) or s.empty:
        return None
    clean = s.dropna()
    if clean.empty:
        return None
    return clean.index[-1].date()


def check_session_staleness(s: pd.Series, ticker: str) -> str | None:
    """
    Phase 4g (G-9): flag when a series has NOT advanced to the most recent
    session its venue has actually completed.

    This is the instrument `check_staleness()` is not. That one asks how many
    calendar days old the newest row is, and so stays silent for the whole
    threshold window (5 days for equities) while a dead feed is reused. This
    one asks whether the newest row is the session that SHOULD exist by now,
    so a feed that stops advancing is caught on the very next run.

    Returns None — deliberately, not a flag — when there is no expectation to
    test against: an unmapped ticker, a continuous instrument, or a venue whose
    session cannot be resolved. A guess would be worse than a gap, and the
    calendar-day threshold still backstops those series.

    GRADED, because the holiday calendars are hand-maintained and demonstrably
    incomplete (the 2026 Japan table was missing every holiday from May onward
    until Phase 4g; China's 2026 table still looks thin). An unlisted holiday
    looks EXACTLY like a series one session behind — so:

        1 session behind   -> VERIFY (soft): genuinely ambiguous between a
                              stale feed and a holiday we have not listed.
        2+ sessions behind -> STALE (hard): two consecutive missed sessions is
                              not plausibly a single calendar omission.

    This keeps same-run visibility for the G-9 case without training the reader
    to ignore flags — which is the same failure mode G-9 itself represents.
    """
    if ticker in CONTINUOUS:
        return None
    venue = series_venue(ticker)
    if venue is None:
        return None
    expected = expected_session_date(venue)
    if expected is None:
        return None
    last = last_observation_date(s)
    if last is None or last >= expected:
        return None

    # Count venue sessions actually missed, not calendar days.
    missed = 0
    probe = expected
    while probe > last and missed < 10:
        if not _venue_closed(venue, probe):
            missed += 1
        probe -= timedelta(days=1)

    if missed <= 1:
        return (f"{FLAG_OUTLIER} — newest print {last}, but {venue} has closed "
                f"{expected}: one session behind (stale feed, or a market "
                f"holiday not in our calendar)")
    return (f"{FLAG_STALE} — newest print {last}, but {venue} has closed "
            f"{expected}: {missed} sessions behind")


def check_market_holiday(check_date: date | None = None, market: str = None) -> str | None:
    """
    Return FLAG_HOLIDAY string if check_date is a known holiday for the given market.
    Defaults to today.
    """
    if check_date is None:
        check_date = today_report()
    holiday_matches = get_holiday_name(check_date, market=market)
    if holiday_matches:
        markets = ", ".join(f"{m}: {n}" for m, n in holiday_matches.items())
        return f"{FLAG_HOLIDAY} — {check_date} ({markets})"
    return None


def check_us_market_holiday(check_date: date | None = None) -> str | None:
    """Backward-compatible US-only holiday check."""
    return check_market_holiday(check_date, market="US")


def check_outlier(s: pd.Series, threshold: float = OUTLIER_EQUITY, is_rate: bool = False) -> str | None:
    """
    Check if the most recent day's move exceeds the outlier threshold.
    is_rate=True → threshold applied to absolute level change (percent points), not pct return.
    """
    s = s.dropna()
    if len(s) < 2:
        return None
    last = float(s.iloc[-1])
    prev = float(s.iloc[-2])
    if is_rate:
        move = abs(last - prev)            # percentage points
        thresh = threshold / 100           # convert bps → pct pts
        if move > thresh:
            return f"{FLAG_OUTLIER} — unusual move ({move*100:.1f}bps in one day)"
    else:
        if prev == 0:
            return None
        pct = abs(last - prev) / abs(prev)
        if pct > threshold:
            return f"{FLAG_OUTLIER} — unusual move ({pct*100:.1f}% in one day)"
    return None


# ---------------------------------------------------------------------------
# Aggregate validation
# ---------------------------------------------------------------------------

def run_all(
    equity_data: dict | None = None,
    rate_data: dict | None = None,
    credit_data: dict | None = None,
    reit_data: dict | None = None,
    commodity_data: dict | None = None,
    fx_data: dict | None = None,
) -> dict:
    """
    Run all validation checks. Returns {section: [flag_strings]}.
    """
    flags = {}
    today = today_report()

    # -- Market holiday checks ----------------------------------------------
    holiday_flags = []
    for market in ["US", "UK", "Eurozone", "Japan", "Singapore", "Australia", "Canada"]:
        flag = check_market_holiday(today, market=market)
        if flag:
            holiday_flags.append(flag)
    if holiday_flags:
        flags["holidays"] = holiday_flags

    # -- Equity staleness + outlier -----------------------------------------
    if equity_data:
        eq_flags = []
        for ticker, s in equity_data.items():
            if s is None or s.empty:
                eq_flags.append(f"{FLAG_UNAVAIL} — {ticker}")
                continue
            stale = check_staleness(s, geography=EQUITY_INDICES.get(ticker, {}).get("geo", ""))
            if stale:
                eq_flags.append(f"{ticker}: {stale}")
            session = check_session_staleness(s, ticker)      # Phase 4g (G-9)
            if session:
                eq_flags.append(f"{ticker}: {session}")
            outlier = check_outlier(s, threshold=OUTLIER_EQUITY)
            if outlier:
                eq_flags.append(f"{ticker}: {outlier}")
        if eq_flags:
            flags["equity"] = eq_flags

    # -- Rate staleness: SKIP — policy rates are sparse by design (ECB DFR only
    #    updates on meeting dates); monthly OECD series lag by ~45 days by design.
    #    Only flag API failures (empty series), not staleness.
    if rate_data:
        rate_flags = []
        for geo, geo_data in rate_data.items():
            for key, s in geo_data.items():
                if isinstance(s, bool) or s is None:
                    continue
                if isinstance(s, pd.Series):
                    if s.empty:
                        rate_flags.append(f"{FLAG_UNAVAIL} — {geo} {key}")
                        continue
                    # Yield outlier check (daily series only — skip monthly)
                    from calculator import _detect_monthly
                    if not _detect_monthly(s) and ("rate" in key or "y" in key):
                        outlier = check_outlier(s, threshold=OUTLIER_YIELD * 100, is_rate=True)
                        if outlier:
                            rate_flags.append(f"{geo} {key}: {outlier}")
        if rate_flags:
            flags["rates"] = rate_flags

    # -- Credit OAS staleness + outlier (skip monthly series) ---------------
    if credit_data:
        credit_flags = []
        for label, s in credit_data.items():
            if s is None or (isinstance(s, pd.Series) and s.empty):
                continue
            if isinstance(s, pd.Series):
                from calculator import _detect_monthly
                if not _detect_monthly(s):
                    stale = check_staleness(s, max_days=STALE_DAYS)
                    if stale:
                        credit_flags.append(f"{label}: {stale}")
                outlier = check_outlier(s, threshold=OUTLIER_OAS * 100, is_rate=True)
                if outlier:
                    credit_flags.append(f"{label}: {outlier}")
        if credit_flags:
            flags["credit"] = credit_flags

    # -- REIT staleness + outlier -------------------------------------------
    if reit_data:
        reit_flags = []
        for ticker, s in reit_data.items():
            if s is None or (isinstance(s, pd.Series) and s.empty):
                reit_flags.append(f"{FLAG_UNAVAIL} — {ticker}")
                continue
            stale = check_staleness(s, max_days=STALE_DAYS)
            if stale:
                reit_flags.append(f"{ticker}: {stale}")
            session = check_session_staleness(s, ticker)      # Phase 4g (G-9)
            if session:
                reit_flags.append(f"{ticker}: {session}")
            outlier = check_outlier(s, threshold=OUTLIER_EQUITY)
            if outlier:
                reit_flags.append(f"{ticker}: {outlier}")
        if reit_flags:
            flags["reits"] = reit_flags

    # -- Commodity staleness: yfinance daily — flag if >1 trading day old (Phase 2k) -----
    if commodity_data:
        comm_flags = []
        for key, s in commodity_data.items():
            if s is None or (isinstance(s, pd.Series) and s.empty):
                comm_flags.append(f"{FLAG_UNAVAIL} — {key}")
                continue
            stale = check_staleness(s, max_days=STALE_DAYS_COMMODITY)
            if stale:
                comm_flags.append(f"{key}: {stale}")
            session = check_session_staleness(s, key)         # Phase 4g (G-9)
            if session:
                comm_flags.append(f"{key}: {session}")
            outlier = check_outlier(s, threshold=OUTLIER_EQUITY)
            if outlier:
                comm_flags.append(f"{key}: {outlier}")
        if comm_flags:
            flags["commodities"] = comm_flags

    # -- FX staleness: use WEEKLY threshold (FRED H.10 publishes weekly Mon) -
    if fx_data:
        fx_flags = []
        for key, s in fx_data.items():
            if s is None or (isinstance(s, pd.Series) and s.empty):
                continue
            meta = FX_YFINANCE.get(key)
            is_crypto = meta and meta.get("is_crypto")
            threshold = OUTLIER_BTC if is_crypto else OUTLIER_EQUITY
            # FRED FX series update weekly — use weekly stale threshold
            # Crypto (yfinance) is 24/7 — use daily threshold
            stale_threshold = STALE_DAYS if is_crypto else STALE_DAYS_WEEKLY
            stale = check_staleness(s, max_days=stale_threshold)
            if stale:
                fx_flags.append(f"{key}: {stale}")
            outlier = check_outlier(s, threshold=threshold)
            if outlier:
                fx_flags.append(f"{key}: {outlier}")
        if fx_flags:
            flags["fx"] = fx_flags

    total_flags = sum(len(v) for v in flags.values())
    flags["_summary"] = {
        "total": total_flags,
        "has_flags": total_flags > 0,
        "generated_at": now_report().isoformat(),
    }

    return flags


def email_subject(flags: dict) -> str:
    """Generate email subject line based on flag status."""
    ts = now_report().strftime("%Y-%m-%d")
    if flags.get("_summary", {}).get("has_flags"):
        return f"⚠️ DATA FLAGS | Market Monitor | {ts}"
    return f"📊 Market Monitor | {ts}"
