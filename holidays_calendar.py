"""
holidays_calendar.py — Market holiday calendar
Phase 2b: US, UK, Eurozone, Japan, Singapore, Australia, Canada, China
Used by validator.py to issue INFO flags on known market closures.
"""

from datetime import date

# ---------------------------------------------------------------------------
# US Market Holidays 2025–2026
# NYSE/Nasdaq
# ---------------------------------------------------------------------------
US_HOLIDAYS = {
    # 2025
    date(2025, 1, 1):   "New Year's Day",
    date(2025, 1, 20):  "Martin Luther King Jr. Day",
    date(2025, 2, 17):  "Presidents' Day",
    date(2025, 4, 18):  "Good Friday",
    date(2025, 5, 26):  "Memorial Day",
    date(2025, 6, 19):  "Juneteenth",
    date(2025, 7, 4):   "Independence Day",
    date(2025, 9, 1):   "Labor Day",
    date(2025, 11, 27): "Thanksgiving Day",
    date(2025, 11, 28): "Thanksgiving Day (observed)",
    date(2025, 12, 25): "Christmas Day",
    # 2026
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 1, 19):  "Martin Luther King Jr. Day",
    date(2026, 2, 16):  "Presidents' Day",
    date(2026, 4, 3):   "Good Friday",
    date(2026, 5, 25):  "Memorial Day",
    date(2026, 6, 19):  "Juneteenth",
    date(2026, 7, 3):   "Independence Day (observed)",
    date(2026, 9, 7):   "Labor Day",
    date(2026, 11, 26): "Thanksgiving Day",
    date(2026, 12, 25): "Christmas Day",
}

# ---------------------------------------------------------------------------
# UK Market Holidays 2025–2026
# LSE
# ---------------------------------------------------------------------------
UK_HOLIDAYS = {
    # 2025
    date(2025, 1, 1):   "New Year's Day",
    date(2025, 4, 18):  "Good Friday",
    date(2025, 4, 21):  "Easter Monday",
    date(2025, 5, 5):   "Early May Bank Holiday",
    date(2025, 5, 26):  "Spring Bank Holiday",
    date(2025, 8, 25):  "Summer Bank Holiday",
    date(2025, 12, 25): "Christmas Day",
    date(2025, 12, 26): "Boxing Day",
    # 2026
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 4, 3):   "Good Friday",
    date(2026, 4, 6):   "Easter Monday",
    date(2026, 5, 4):   "Early May Bank Holiday",
    date(2026, 5, 25):  "Spring Bank Holiday",
    date(2026, 8, 31):  "Summer Bank Holiday",
    date(2026, 12, 25): "Christmas Day",
    date(2026, 12, 28): "Boxing Day (observed)",
}

# ---------------------------------------------------------------------------
# Eurozone Market Holidays 2025–2026
# Euronext / Frankfurt
# ---------------------------------------------------------------------------
EUROZONE_HOLIDAYS = {
    # 2025
    date(2025, 1, 1):   "New Year's Day",
    date(2025, 4, 18):  "Good Friday",
    date(2025, 4, 21):  "Easter Monday",
    date(2025, 5, 1):   "Labour Day",
    date(2025, 12, 25): "Christmas Day",
    date(2025, 12, 26): "Boxing Day",
    # 2026
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 4, 3):   "Good Friday",
    date(2026, 4, 6):   "Easter Monday",
    date(2026, 5, 1):   "Labour Day",
    date(2026, 12, 25): "Christmas Day",
    date(2026, 12, 26): "Boxing Day",
}

# ---------------------------------------------------------------------------
# Japan Market Holidays 2025–2026
# TSE — key national holidays (partial list; Japan has ~16 public holidays/year)
# ---------------------------------------------------------------------------
JAPAN_HOLIDAYS = {
    # 2025
    date(2025, 1, 1):   "New Year's Day",
    date(2025, 1, 13):  "Coming of Age Day",
    date(2025, 2, 11):  "National Foundation Day",
    date(2025, 3, 20):  "Vernal Equinox",
    date(2025, 4, 29):  "Showa Day",
    date(2025, 5, 3):   "Constitution Day",
    date(2025, 5, 4):   "Greenery Day",
    date(2025, 5, 5):   "Children's Day",
    date(2025, 7, 21):  "Marine Day",
    date(2025, 8, 11):  "Mountain Day",
    date(2025, 9, 15):  "Respect for the Aged Day",
    date(2025, 9, 23):  "Autumnal Equinox",
    date(2025, 10, 13): "Sports Day",
    date(2025, 11, 3):  "Culture Day",
    date(2025, 11, 23): "Labour Thanksgiving Day",
    date(2025, 12, 31): "New Year's Eve (market closed)",
    # 2026 (approximate — TSE announces exact dates annually)
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 1, 12):  "Coming of Age Day",
    date(2026, 2, 11):  "National Foundation Day",
    date(2026, 3, 20):  "Vernal Equinox",
    date(2026, 4, 29):  "Showa Day",
    date(2026, 5, 3):   "Constitution Day",
    date(2026, 5, 4):   "Greenery Day",
    date(2026, 5, 5):   "Children's Day",
    # Phase 4g: the 2026 Japan calendar stopped at Children's Day — every
    # holiday from May onward was missing, including Marine Day (2026-07-20),
    # which is the exact day the G-9 incident straddled. A missing holiday
    # makes the session-freshness check expect a close that never happened,
    # i.e. a false STALE flag. Backfilled below.
    date(2026, 2, 23):  "Emperor's Birthday",
    date(2026, 5, 6):   "Constitution Day (substitute — 3 May fell on Sunday)",
    date(2026, 7, 20):  "Marine Day",
    date(2026, 8, 11):  "Mountain Day",
    date(2026, 9, 21):  "Respect for the Aged Day",
    date(2026, 9, 22):  "Citizens' Holiday",
    date(2026, 9, 23):  "Autumnal Equinox",
    date(2026, 10, 12): "Sports Day",
    date(2026, 11, 3):  "Culture Day",
    date(2026, 11, 23): "Labour Thanksgiving Day",
    date(2026, 1, 2):   "New Year (TSE closed)",
    date(2026, 1, 3):   "New Year (TSE closed)",
    date(2026, 12, 31): "New Year's Eve (market closed)",
}

# ---------------------------------------------------------------------------
# Singapore Market Holidays 2025–2026
# SGX
# ---------------------------------------------------------------------------
SINGAPORE_HOLIDAYS = {
    # 2025
    date(2025, 1, 1):   "New Year's Day",
    date(2025, 1, 29):  "Chinese New Year",
    date(2025, 1, 30):  "Chinese New Year (Day 2)",
    date(2025, 4, 18):  "Good Friday",
    date(2025, 5, 1):   "Labour Day",
    date(2025, 5, 12):  "Vesak Day",
    date(2025, 6, 6):   "Hari Raya Haji",
    date(2025, 8, 9):   "National Day",
    date(2025, 10, 20): "Deepavali",
    date(2025, 12, 25): "Christmas Day",
    # 2026 — corrected 2026-07-25 against two independent providers
    # (markethours.io + forexchurch.com, in full agreement): National Day
    # fell Sun 9 Aug — the closure is Mon 10 AUG (OBSERVED; prior entry sat
    # on the Sunday and the real closure two weeks out was missing); Hari
    # Raya Haji (27 May), Vesak (observed 1 Jun) and Deepavali (observed
    # 9 Nov) were absent entirely — Nov 9 was a future-dated gap that would
    # have raised a false STALE on STI at the Nov-10 run.
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 2, 17):  "Chinese New Year",
    date(2026, 2, 18):  "Chinese New Year (Day 2)",
    date(2026, 4, 3):   "Good Friday",
    date(2026, 5, 1):   "Labour Day",
    date(2026, 5, 27):  "Hari Raya Haji",
    date(2026, 6, 1):   "Vesak Day (observed — 31 May fell on Sunday)",
    date(2026, 8, 10):  "National Day (observed — 9 Aug fell on Sunday)",
    date(2026, 11, 9):  "Deepavali (observed — 8 Nov fell on Sunday)",
    date(2026, 12, 25): "Christmas Day",
}

# ---------------------------------------------------------------------------
# Australia Market Holidays 2025–2026
# ASX — national holidays only (state holidays vary)
# ---------------------------------------------------------------------------
AUSTRALIA_HOLIDAYS = {
    # 2025
    date(2025, 1, 1):   "New Year's Day",
    date(2025, 1, 27):  "Australia Day (observed)",
    date(2025, 4, 18):  "Good Friday",
    date(2025, 4, 19):  "Easter Saturday",
    date(2025, 4, 21):  "Easter Monday",
    date(2025, 4, 25):  "Anzac Day",
    date(2025, 12, 25): "Christmas Day",
    date(2025, 12, 26): "Boxing Day",
    # 2026
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 1, 26):  "Australia Day",
    date(2026, 4, 3):   "Good Friday",
    date(2026, 4, 4):   "Easter Saturday",
    date(2026, 4, 6):   "Easter Monday",
    date(2026, 4, 25):  "Anzac Day",
    date(2026, 12, 25): "Christmas Day",
    date(2026, 12, 28): "Boxing Day (observed)",
}

# ---------------------------------------------------------------------------
# Canada Market Holidays 2025–2026
# TSX
# ---------------------------------------------------------------------------
CANADA_HOLIDAYS = {
    # 2025
    date(2025, 1, 1):   "New Year's Day",
    date(2025, 2, 17):  "Family Day (ON/BC)",
    date(2025, 4, 18):  "Good Friday",
    date(2025, 5, 19):  "Victoria Day",
    date(2025, 7, 1):   "Canada Day",
    date(2025, 8, 4):   "Civic Holiday",
    date(2025, 9, 1):   "Labour Day",
    date(2025, 9, 30):  "National Day for Truth and Reconciliation",
    date(2025, 10, 13): "Thanksgiving",
    date(2025, 11, 11): "Remembrance Day",
    date(2025, 12, 25): "Christmas Day",
    date(2025, 12, 26): "Boxing Day",
    # 2026
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 2, 16):  "Family Day (ON/BC)",
    date(2026, 4, 3):   "Good Friday",
    date(2026, 5, 18):  "Victoria Day",
    date(2026, 7, 1):   "Canada Day",
    date(2026, 9, 7):   "Labour Day",
    date(2026, 10, 12): "Thanksgiving",
    date(2026, 12, 25): "Christmas Day",
    date(2026, 12, 28): "Boxing Day (observed)",
}

# ---------------------------------------------------------------------------
# China Market Holidays 2025–2026
# SSE / SZSE — key holidays (data already monthly — holidays informational only)
# ---------------------------------------------------------------------------
CHINA_HOLIDAYS = {
    # 2025
    date(2025, 1, 1):   "New Year's Day",
    date(2025, 1, 28):  "Chinese New Year (Spring Festival)",
    date(2025, 1, 29):  "Spring Festival",
    date(2025, 1, 30):  "Spring Festival",
    date(2025, 1, 31):  "Spring Festival",
    date(2025, 2, 3):   "Spring Festival",
    date(2025, 2, 4):   "Spring Festival",
    date(2025, 4, 4):   "Tomb Sweeping Day",
    date(2025, 5, 1):   "Labour Day",
    date(2025, 10, 1):  "National Day Golden Week",
    date(2025, 10, 2):  "National Day",
    date(2025, 10, 3):  "National Day",
    date(2025, 10, 6):  "National Day",
    date(2025, 10, 7):  "National Day",
    # 2026 — full SSE/SZSE closure set, verified 2026-07-25 against three
    # independent providers (markethours.io, forexchurch.com, calendarlabs.com;
    # SSE's own English schedule page still listed only 2024-25 and SHFE's
    # circular was bot-walled — both checked). All three agree on every date
    # below; total 17 weekday closures. Prior table had 5 single-day entries,
    # incl. Tomb Sweeping on Apr 5 — a SUNDAY in 2026; the actual closure was
    # Mon Apr 6. NOTE: Jan 2 was claimed closed by 2 of 3 providers but open
    # by the self-consistent one ("18 full closures" incl. weekend-adjacent
    # count differences); date is past and inert for the forward-looking
    # session detector — recorded here as unresolved rather than guessed.
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 2, 16):  "Spring Festival Eve",
    date(2026, 2, 17):  "Chinese New Year (Spring Festival)",
    date(2026, 2, 18):  "Spring Festival",
    date(2026, 2, 19):  "Spring Festival",
    date(2026, 2, 20):  "Spring Festival",
    date(2026, 2, 23):  "Spring Festival",
    date(2026, 4, 6):   "Tomb Sweeping Day (observed — 5 Apr fell on Sunday)",
    date(2026, 5, 1):   "Labour Day",
    date(2026, 5, 4):   "Labour Day Holiday",
    date(2026, 5, 5):   "Labour Day Holiday",
    date(2026, 6, 19):  "Dragon Boat Festival",
    date(2026, 9, 25):  "Mid-Autumn Festival",
    date(2026, 10, 1):  "National Day Golden Week",
    date(2026, 10, 2):  "National Day Golden Week",
    date(2026, 10, 5):  "National Day Golden Week",
    date(2026, 10, 6):  "National Day Golden Week",
    date(2026, 10, 7):  "National Day Golden Week",
}

# ---------------------------------------------------------------------------
# All-market combined lookup
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Hong Kong Market Holidays 2025-2026 (HKEX)
# Phase 4g: added for ^HSCE. Hong Kong holidays are NOT China's - HKEX and SSE
# keep separate calendars (HK observes Good Friday, Easter, Christmas, Boxing
# Day; the mainland does not, and the mainland's Golden Week is far longer).
# Mapping ^HSCE onto CHINA_HOLIDAYS would have been wrong in both directions.
# ---------------------------------------------------------------------------
HONGKONG_HOLIDAYS = {
    # 2025
    date(2025, 1, 1):   "New Year's Day",
    date(2025, 1, 29):  "Lunar New Year",
    date(2025, 1, 30):  "Lunar New Year",
    date(2025, 1, 31):  "Lunar New Year",
    date(2025, 4, 4):   "Ching Ming Festival",
    date(2025, 4, 18):  "Good Friday",
    date(2025, 4, 21):  "Easter Monday",
    date(2025, 5, 1):   "Labour Day",
    date(2025, 5, 5):   "Buddha's Birthday",
    date(2025, 7, 1):   "HKSAR Establishment Day",
    date(2025, 10, 1):  "National Day",
    date(2025, 10, 29): "Chung Yeung Festival",
    date(2025, 12, 25): "Christmas Day",
    date(2025, 12, 26): "Boxing Day",
    # 2026 — corrected 2026-07-25 against the official gov.hk general-holidays
    # 2026 page (authoritative): Buddha's Birthday fell Sun 24 May — the
    # closure was Mon 25 May (prior entry sat on the Sunday); Tue 7 Apr was an
    # additional holiday the table missed; and Mon 19 Oct ("the day following
    # Chung Yeung Festival" — festival falls on Sunday) IS a closure, the
    # future-dated gap that would have raised a false STALE on ^HSCE at the
    # Oct-20 run. Sat 26 Sep (day after Mid-Autumn) omitted deliberately —
    # weekend, never an expected session.
    date(2026, 1, 1):   "New Year's Day",
    date(2026, 2, 17):  "Lunar New Year",
    date(2026, 2, 18):  "Lunar New Year",
    date(2026, 2, 19):  "Lunar New Year",
    date(2026, 4, 3):   "Good Friday",
    date(2026, 4, 6):   "Easter Monday / Ching Ming",
    date(2026, 4, 7):   "Additional holiday (Easter/Ching Ming week)",
    date(2026, 5, 1):   "Labour Day",
    date(2026, 5, 25):  "Buddha's Birthday (observed — 24 May fell on Sunday)",
    date(2026, 7, 1):   "HKSAR Establishment Day",
    date(2026, 10, 1):  "National Day",
    date(2026, 10, 19): "Day following Chung Yeung Festival",
    date(2026, 12, 25): "Christmas Day",
    date(2026, 12, 26): "Boxing Day",
}

MARKET_HOLIDAYS = {
    "US":        US_HOLIDAYS,
    "UK":        UK_HOLIDAYS,
    "Eurozone":  EUROZONE_HOLIDAYS,
    "Japan":     JAPAN_HOLIDAYS,
    "Singapore": SINGAPORE_HOLIDAYS,
    "Australia": AUSTRALIA_HOLIDAYS,
    "Canada":    CANADA_HOLIDAYS,
    "China":     CHINA_HOLIDAYS,
    "HongKong":  HONGKONG_HOLIDAYS,
}


def get_holiday_name(check_date: date, market: str = None) -> dict:
    """
    Returns {market: holiday_name} for all markets where check_date is a holiday.
    If market is specified, checks only that market.
    """
    if isinstance(check_date, str):
        from datetime import datetime
        check_date = datetime.strptime(check_date, "%Y-%m-%d").date()

    if market:
        markets = {market: MARKET_HOLIDAYS.get(market, {})}
    else:
        markets = MARKET_HOLIDAYS

    return {
        mkt: name
        for mkt, holidays in markets.items()
        if check_date in holidays
        for name in [holidays[check_date]]
    }


def is_us_market_holiday(check_date: date) -> bool:
    """True if check_date is a US market holiday."""
    return check_date in US_HOLIDAYS
