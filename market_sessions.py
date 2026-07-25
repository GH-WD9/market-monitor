"""
market_sessions.py — session-aware freshness (Phase 4g, closes Gap Register G-9)

WHAT G-9 WAS
------------
The 2026-07-21 23:55 run carried Nikkei 225 and CSI 300 prints byte-identical
to the 2026-07-20 run — level and every return window — with NO flag raised.
`check_staleness()` only asks "how old is the newest row?", never "should a
newer row exist by now?". So any series whose last observation stops advancing
is reused silently for `STALE_DAYS` days (5 for equities). The threshold IS the
silent-duplication window.

WHY NOT A RUN-TO-RUN "BYTE-IDENTICAL" COMPARISON
------------------------------------------------
Because it is wrong twice a day. Runs fire at 07:00 and 19:00 SGT:

  07:00 SGT — US/Canada (closed ~04-05:00 SGT) and UK/Europe (closed ~23:30-
              00:30 SGT) are fresh. ALL of Asia legitimately still shows
              YESTERDAY's close: Tokyo does not open until 08:00 SGT.
  19:00 SGT — Japan/Australia/China/Hong Kong/Singapore are fresh. US is not
              open yet and Europe is mid-session, so BOTH legitimately show
              the SAME close the 07:00 run used.

A run-to-run comparison flags that second column every single day. What is
actually needed is per-venue expectation, which is what this module computes:
the most recent session whose close (plus a publication grace) has passed.

TWO DIFFERENT MAPPINGS, AND WHY BOTH EXIST
------------------------------------------
LLY instruction (2026-07-25): classify assets by WHAT THEY HOLD — ACWI is
Global equities; the fact it happens to list in the US is secondary. That is
right for how the report reads, and `EXPOSURE` below is that mapping. It is
the one shown to the reader.

But a trading calendar is a property of a VENUE, not of an exposure: "Global"
has no opening hours, so "should ACWI have a new close today?" cannot be
answered from its exposure. ACWI prints only when NYSE Arca trades — on US
Independence Day it does not print even though Tokyo and London did. So
`VENUE` below is a second, internal attribute used ONLY for the freshness
expectation. Exposure describes the risk; venue describes the clock. Using
exposure as the clock would false-flag every US holiday; using venue as the
label would mis-describe the asset. Hence both.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from holidays_calendar import MARKET_HOLIDAYS

# ---------------------------------------------------------------------------
# Venue table — where an instrument actually prints a close.
# `holiday_key` indexes MARKET_HOLIDAYS; None = no calendar available yet
# (weekend logic only, stated rather than silently assumed).
# `grace_h`: hours after the close before data is REQUIRED to have arrived.
# Deliberately generous — a false "stale" flag trains the reader to ignore
# flags, which is the same failure G-9 already represents.
# ---------------------------------------------------------------------------
VENUE_SESSIONS = {
    "NYSE":  {"tz": "America/New_York", "close": time(16, 0),  "holiday_key": "US",        "grace_h": 3},
    "TSX":   {"tz": "America/Toronto",  "close": time(16, 0),  "holiday_key": "Canada",    "grace_h": 3},
    "XETRA": {"tz": "Europe/Berlin",    "close": time(17, 30), "holiday_key": "Eurozone",  "grace_h": 3},
    "LSE":   {"tz": "Europe/London",    "close": time(16, 30), "holiday_key": "UK",        "grace_h": 3},
    "TSE":   {"tz": "Asia/Tokyo",       "close": time(15, 0),  "holiday_key": "Japan",     "grace_h": 3},
    "SSE":   {"tz": "Asia/Shanghai",    "close": time(15, 0),  "holiday_key": "China",     "grace_h": 3},
    "HKEX":  {"tz": "Asia/Hong_Kong",   "close": time(16, 0),  "holiday_key": "HongKong",  "grace_h": 3},
    "SGX":   {"tz": "Asia/Singapore",   "close": time(17, 0),  "holiday_key": "Singapore", "grace_h": 3},
    "ASX":   {"tz": "Australia/Sydney", "close": time(16, 0),  "holiday_key": "Australia", "grace_h": 3},
    # CME/ICE futures settle on the US calendar; near-24h trading, so the
    # settlement time rather than a bell governs.
    "CME":   {"tz": "America/New_York", "close": time(17, 0),  "holiday_key": "US",        "grace_h": 4},
}

# Instruments that never close. Session logic does not apply; these fall back
# to the calendar-day thresholds.
CONTINUOUS = {"BTC-USD"}

# ---------------------------------------------------------------------------
# EXPOSURE — what the instrument HOLDS. The reader-facing classification
# (LLY, 2026-07-25). This is the label; it is not the clock.
# ---------------------------------------------------------------------------
EXPOSURE = {
    "ACWI": "Global", "URTH": "Developed Mkts", "EEM": "Emerging Mkts",
    "^GSPC": "US", "^NDX": "US", "^GSPTSE": "Canada",
    "^STOXX50E": "Eurozone", "^FTSE": "UK", "^N225": "Japan",
    "^STI": "Singapore", "^AXJO": "Australia",
    "000300.SS": "China A-shares", "^HSCE": "China H-shares",
    "VNQ": "US REITs", "VNQI": "Global ex-US REITs",
    "^VIX": "US volatility",
    "CL=F": "Global energy", "BZ=F": "Global energy", "NG=F": "US natural gas",
    "GC=F": "Global precious metals", "SI=F": "Global precious metals",
    "HG=F": "Global industrial metals",
    "DJP": "Global commodities", "BDRY": "Global dry bulk freight",
    "BTC-USD": "Digital assets",
}

# ---------------------------------------------------------------------------
# VENUE — where it PRINTS. Internal; drives the freshness expectation only.
# Note the deliberate divergences from EXPOSURE: ACWI/URTH/EEM/VNQI/DJP/BDRY
# are US-listed funds, so they follow the NYSE calendar whatever they hold.
# ---------------------------------------------------------------------------
VENUE = {
    "ACWI": "NYSE", "URTH": "NYSE", "EEM": "NYSE",
    "^GSPC": "NYSE", "^NDX": "NYSE", "^GSPTSE": "TSX",
    "^STOXX50E": "XETRA", "^FTSE": "LSE", "^N225": "TSE",
    "^STI": "SGX", "^AXJO": "ASX",
    "000300.SS": "SSE", "^HSCE": "HKEX",
    "VNQ": "NYSE", "VNQI": "NYSE",
    "^VIX": "NYSE",
    "CL=F": "CME", "BZ=F": "CME", "NG=F": "CME",
    "GC=F": "CME", "SI=F": "CME", "HG=F": "CME",
    "DJP": "NYSE", "BDRY": "NYSE",
}


def _is_closed(d: date, holiday_key: str) -> bool:
    """Weekend, or a holiday for this venue's calendar."""
    if d.weekday() >= 5:
        return True
    if holiday_key and d in MARKET_HOLIDAYS.get(holiday_key, {}):
        return True
    return False


def venue_closed(venue: str, d: date) -> bool:
    """True if `venue` was shut on date `d` (weekend or listed holiday)."""
    cfg = VENUE_SESSIONS.get(venue)
    if cfg is None:
        return False
    return _is_closed(d, cfg["holiday_key"])


def expected_session_date(venue: str, now_utc: datetime = None) -> date | None:
    """
    The most recent trading session for `venue` whose close + grace has passed.

    This is the date the series' newest observation SHOULD carry. Returns None
    for an unknown venue — the caller must then skip the check rather than
    invent an expectation (a silently-empty expectation is the G-9 defect in
    a new costume).
    """
    cfg = VENUE_SESSIONS.get(venue)
    if cfg is None:
        return None
    tz = ZoneInfo(cfg["tz"])
    now_local = (now_utc or datetime.now(ZoneInfo("UTC"))).astimezone(tz)

    d = now_local.date()
    for _ in range(15):                      # 15 days spans any holiday run
        if not _is_closed(d, cfg["holiday_key"]):
            close_dt = datetime.combine(d, cfg["close"], tzinfo=tz)
            if now_local >= close_dt + timedelta(hours=cfg["grace_h"]):
                return d
        d -= timedelta(days=1)
    return None


def series_venue(ticker: str) -> str | None:
    return VENUE.get(ticker)


def series_exposure(ticker: str) -> str | None:
    return EXPOSURE.get(ticker)
