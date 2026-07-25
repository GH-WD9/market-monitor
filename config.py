"""
config.py — Market Monitor configuration
Phase 2k: Energy commodities switched from FRED EIA spot to yfinance front-month futures
          (CL=F/BZ=F/NG=F); COMMODITY_FRED retired; STALE_DAYS_COMMODITY=2 added
Phase 3b: load_dotenv removed — GitHub Actions injects env vars natively from secrets
"""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Runtime phase
# ---------------------------------------------------------------------------
PHASE = "4g"

# ---------------------------------------------------------------------------
# FRED API
# ---------------------------------------------------------------------------
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# ---------------------------------------------------------------------------
# FRED cache
# ---------------------------------------------------------------------------
CACHE_DIR = "cache"
CACHE_MAX_AGE_HOURS = 4

# ---------------------------------------------------------------------------
# Section 0 — Market Stress
# Ratio instruments — yfinance futures (spot sources failed)
# ---------------------------------------------------------------------------
STRESS_TICKERS = {
    "^VIX":  "VIX",
    "GC=F":  "Gold (GC=F)",
    "SI=F":  "Silver (SI=F)",
    "HG=F":  "Copper (HG=F)",
}

# ---------------------------------------------------------------------------
# Section 1 — Equity Indices
# Ordered for report display: Global → DM → EM → US → Europe → Asia-Pac
# ---------------------------------------------------------------------------
EQUITY_INDICES = {
    # Global
    "ACWI":        {"name": "MSCI ACWI",          "geo": "Global",          "region": "Global",       "type": "etf"},
    "URTH":        {"name": "MSCI World",          "geo": "Developed Mkts",  "region": "Global",       "type": "etf"},
    "EEM":         {"name": "MSCI EM",             "geo": "Emerging Mkts",   "region": "Global",       "type": "etf"},
    # Americas
    "^GSPC":       {"name": "S&P 500",             "geo": "US",              "region": "Americas",     "type": "index"},
    "^NDX":        {"name": "Nasdaq 100",          "geo": "US",              "region": "Americas",     "type": "index"},
    "^GSPTSE":     {"name": "TSX Composite",       "geo": "Canada",          "region": "Americas",     "type": "index"},
    # EMEA
    "^STOXX50E":   {"name": "Euro Stoxx 50",       "geo": "Eurozone",        "region": "EMEA",         "type": "index",
                    "fallback": "EZU"},
    "^FTSE":       {"name": "FTSE 100",            "geo": "UK",              "region": "EMEA",         "type": "index"},
    # Asia-Pacific
    "^N225":       {"name": "Nikkei 225",          "geo": "Japan",           "region": "Asia-Pacific", "type": "index"},
    "^STI":        {"name": "STI",                 "geo": "Singapore",       "region": "Asia-Pacific", "type": "index"},
    "^AXJO":       {"name": "ASX 200",             "geo": "Australia",       "region": "Asia-Pacific", "type": "index"},
    "000300.SS":   {"name": "CSI 300",             "geo": "China A-shares",  "region": "Asia-Pacific", "type": "index",
                    "fallback": "510300.SS"},
    "^HSCE":       {"name": "HSCEI",               "geo": "China H-shares",  "region": "Asia-Pacific", "type": "index"},
}

# Return periods: label → trading-day offset
RETURN_PERIODS = {
    "1D":  1,
    "1W":  5,
    "1M":  21,
    "3M":  63,
    "6M":  126,
    "1Y":  252,
    "3Y":  756,
    "5Y":  1260,
    "10Y": 2520,
}

# ---------------------------------------------------------------------------
# Section 2 — Government Bond Yields, Cash Rates & Spreads
# ---------------------------------------------------------------------------

# -- US (FRED, daily) -------------------------------------------------------
US_FRED_RATES = {
    "cash_rate":  "DFF",
    "3m":         "DGS3MO",
    "2y":         "DGS2",
    "10y":        "DGS10",
    "30y":        "DGS30",
}

# -- Eurozone (ECB API, daily) ----------------------------------------------
ECB_BASE_URL = "https://data-api.ecb.europa.eu/service/data"
ECB_SERIES = {
    "cash_rate":  "FM/B.U2.EUR.4F.KR.DFR.LEV",
    "2y":         "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y",
    "10y":        "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y",
    "30y":        "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_30Y",
}

# -- UK (BoE IADB, daily) ---------------------------------------------------
BOE_BASE_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-FromShowColumns.asp"
BOE_SERIES = {
    "cash_rate":  "IUDBEDR",
    "2y":         "IUDSNPY",   # 5Y nominal par yield (2Y unavailable on BoE IADB)
    "10y":        "IUDMNPY",
    "30y":        "IUDLNPY",   # 20Y nominal par yield (30Y unavailable on BoE IADB)
}
BOE_ZIP_URL = "https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/latest-yield-curve-data.zip"

# -- Canada (BoC Valet API, daily) ------------------------------------------
BOC_BASE_URL = "https://www.bankofcanada.ca/valet/observations"
BOC_SERIES = {
    "cash_rate":  "AVG.INTWO",
    "2y":         "BD.CDN.2YR.DQ.YLD",
    "10y":        "BD.CDN.10YR.DQ.YLD",
    "30y":        "BD.CDN.LONG.DQ.YLD",
}

# -- Australia (RBA xlsx + FRED fallback) -----------------------------------
RBA_CASH_URL = "https://www.rba.gov.au/statistics/tables/xls/f01d.xlsx"
RBA_CASH_SERIES = "FIRMMCRTD"
RBA_YIELDS_URL = "https://www.rba.gov.au/statistics/tables/xls/f02d.xlsx"
RBA_YIELDS_SERIES = {
    "2y":  "FCMYGBAG2D",
    "10y": "FCMYGBAG10D",
}
RBA_FRED = {
    "cash_rate":  "IRSTCI01AUM156N",
    "10y":        "IRLTLT01AUM156N",
}
RBA_2Y_FRED = None

# -- Singapore (MAS HTML scrape) --------------------------------------------
MAS_SORA_API_URL = "https://eservices.mas.gov.sg/api/action/datastore/search.json?resource_id=9a0bf149-308c-4bd2-832d-76c8e6cb47ed"
MAS_SORA_URL = "https://eservices.mas.gov.sg/statistics/dir/DomesticInterestRates.aspx"
MAS_SGS_URL  = "https://eservices.mas.gov.sg/statistics/fdanet/SgsBenchmarkIssuePrices.aspx"

# -- Japan (FRED monthly — no free daily source) ----------------------------
JAPAN_FRED = {
    "cash_rate":  "IRSTCI01JPM156N",
    "10y":        "IRLTLT01JPM156N",
}
JAPAN_MOF_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"

# -- China (FRED monthly fallback) ------------------------------------------
# Primary: ChinaBond live scraper (daily). These are fallbacks on ChinaBond failure.
# cash_rate: PBOC deposit rate — still active on FRED.
# 2Y/10Y: IRLTLT01CNM156N (OECD) confirmed discontinued — returns HTTP 400 as of 2026-06.
# 30Y: no FRED equivalent exists.
# None entries are skipped in fetch_china_rates(); ChinaBond is the only source for 2Y/10Y/30Y.
CHINA_FRED = {
    "cash_rate":  "INTDSRCNM193N",   # PBOC deposit rate monthly — active
    "2y":         None,               # IRLTLT01CNM156N discontinued — ChinaBond primary only
    "10y":        None,               # IRLTLT01CNM156N discontinued — ChinaBond primary only
    "30y":        None,               # No FRED equivalent — ChinaBond primary only
}
CHINABOND_URL = "https://yield.chinabond.com.cn/cbweb-mn/yield_main?locale=en_US"
CHINABOND_API_URL = (
    "https://yield.chinabond.com.cn/cbweb-mn/yc/ycDetail"
    "?ycDefIds=2c9081e50a2f9606010a3068cae70001"
    "&&zblx=txy&&workTime=&&dxbj=&&qxlx=&&yqqxN=&&yqqxK=&&wrjxCBFlag=0&locale=en_US"
)

# ---------------------------------------------------------------------------
# Section 3 — Credit (OAS via FRED)
# ---------------------------------------------------------------------------
CREDIT_FRED_SERIES = {
    "US_IG": {
        "series":  "BAMLC0A0CM",
        "name":    "US IG OAS (ICE BofA)",
        "phase":   "2a",
        "status":  "confirmed",
    },
    "US_HY": {
        "series":  "BAMLH0A0HYM2",
        "name":    "US HY OAS (ICE BofA)",
        "phase":   "2a",
        "status":  "confirmed",
    },
    "EUR_HY": {
        "series":  "BAMLHE00EHYIOAS",
        "name":    "EUR HY OAS (ICE BofA Euro HY)",
        "phase":   "2b",
        "status":  "confirmed",
    },
}

CREDIT_GAPS = {
    "EUR_IG": "No ICE BofA EUR IG OAS series found on FRED.",
    "GBP_IG": "FRED availability unconfirmed. Fallback: SLXX.L ETF price proxy.",
}

GBP_IG_FALLBACK_TICKER = "SLXX.L"

# ---------------------------------------------------------------------------
# Section 4 — REITs
# ---------------------------------------------------------------------------
REIT_TICKERS = {
    "VNQ":   "US REITs (Vanguard Real Estate)",
    "VNQI":  "Global ex-US REITs (Vanguard Global ex-US RE)",
}

# ---------------------------------------------------------------------------
# Section 5 — Commodities
# ---------------------------------------------------------------------------
COMMODITY_YFINANCE = {
    "CL=F":  {"name": "WTI Crude Oil",             "unit": "USD/bbl",   "note": "front-month futures"},
    "BZ=F":  {"name": "Brent Crude Oil",           "unit": "USD/bbl",   "note": "front-month futures"},
    "NG=F":  {"name": "Natural Gas (Henry Hub)",   "unit": "USD/MMBtu", "note": "front-month futures"},
    "GC=F":  {"name": "Gold",                      "unit": "USD/oz",    "note": "front-month futures"},
    "SI=F":  {"name": "Silver",                    "unit": "USD/oz",    "note": "front-month futures"},
    "HG=F":  {"name": "Copper",                    "unit": "USD/lb",    "note": "front-month futures"},
    "DJP":   {"name": "Broad Commodities (DJP)",   "unit": "price",     "note": "ETN proxy"},
    "BDRY":  {"name": "Baltic Dry proxy (BDRY)",   "unit": "price",     "note": "ETF proxy ⚠️not BDI — tracking error"},
}

COMMODITY_FRED = {}  # Phase 2k: retired

# ---------------------------------------------------------------------------
# Section 6 — Currencies & Digital Assets vs USD
# ---------------------------------------------------------------------------
FX_FRED = {
    "DEXUSEU": {"pair": "EUR/USD", "ccy": "EUR", "natural": True},
    "DEXUSUK": {"pair": "GBP/USD", "ccy": "GBP", "natural": True},
    "DEXJPUS": {"pair": "JPY/USD", "ccy": "JPY", "natural": False},
    "DEXUSAL": {"pair": "AUD/USD", "ccy": "AUD", "natural": True},
    "DEXCAUS": {"pair": "CAD/USD", "ccy": "CAD", "natural": False},
    "DEXSIUS": {"pair": "SGD/USD", "ccy": "SGD", "natural": False},
    "DEXCHUS": {"pair": "CNY/USD", "ccy": "CNY", "natural": False},
}

FX_YFINANCE = {
    "BTC-USD": {
        "pair": "Bitcoin",
        "ccy": "BTC",
        "natural": True,
        "is_crypto": True,
        "outlier_threshold": 0.15,
        "note": "24/7; no market close; midnight UTC reference",
    },
}

# ---------------------------------------------------------------------------
# Validation thresholds
# ---------------------------------------------------------------------------
STALE_DAYS = 5
STALE_DAYS_WEEKLY = 12
STALE_DAYS_COMMODITY = 3   # Phase 4a: 2 → 3 (2 flagged benign Fri-close/Mon-run gaps)
OUTLIER_EQUITY = 0.08
OUTLIER_YIELD = 0.50
OUTLIER_OAS = 0.50
OUTLIER_BTC = 0.15

# ---------------------------------------------------------------------------
# Report colour thresholds (Phase 4d — LLY decisions D3/D4/D5, 2026-07-24)
# Single home for the colour bands; report_generator reads them, never
# hard-codes them (Entry 31 Central Configuration Management).
#
# D3 sets the DEFAULT neutral band; D4/D5 are per-class overrides of it.
# Inside the band a value renders neutral grey — colour is binary red/green
# outside it. The signed prefix (+/-) always carries direction independently
# of colour (user-experience §4: colour is never the sole carrier of meaning).
# ---------------------------------------------------------------------------
COLOUR_BAND_PCT    = 0.001   # D3 default: ±0.1% (decimal fraction)
COLOUR_BAND_BPS    = 2.0     # D3 default: ±2bps
COLOUR_BAND_EQUITY = 0.01    # D5 override: equity securities ±1% (review after one week)
                             # Applies to Section 1 equity indices AND Section 4
                             # REITs (LLY 2026-07-24 s5: REITs are equity
                             # securities, so they take the equity band — the
                             # literal index-only reading made a 0.4% VNQ move
                             # colour while a 0.4% S&P move did not).
COLOUR_BAND_YIELD  = 10.0    # D4 override: government yields ±10bps

# ---------------------------------------------------------------------------
# Report clock — single source for "what time is it, for this report"
#
# Phase 4f: every user-facing date and time in this system is expressed in
# REPORT_TIMEZONE, and MUST come from now_report(). Bare datetime.now() is a
# defect here: it returns the *runner's* local time, which on GitHub Actions
# is UTC. That produced two live errors on the published page —
#   (1) the header stamped UTC and labelled it "SGT" (8h wrong), and
#   (2) the 23:00 UTC run is 07:00 SGT the NEXT day, so the report title and
#       every date-based check ran a calendar day behind Singapore.
# Both were invisible locally, where the machine genuinely is on SGT — the
# test exercised a scope the runner does not share.
# ---------------------------------------------------------------------------
REPORT_TIMEZONE = "Asia/Singapore"
REPORT_TZ_LABEL = "SGT"


def now_report() -> datetime:
    """Timezone-aware 'now' in REPORT_TIMEZONE. Use instead of datetime.now()."""
    return datetime.now(ZoneInfo(REPORT_TIMEZONE))


def today_report() -> date:
    """Today's date in REPORT_TIMEZONE — never the runner's date."""
    return now_report().date()


# ---------------------------------------------------------------------------
# Disclaimer (uwa §1.31 ladder — FULL form)
#
# This report is published publicly (GitHub Pages) and emailed, and it is
# financial in subject matter: travels-by-design AND regulated-adjacent, which
# is the full form under the ladder.
#
# ⚠ MIRRORED COPY — verbatim from Registry `meta.standing_texts.disclaimer_full`.
# §1.31 requires exactly one machine home for these texts, consumed by pointer
# or generated render. This repository is PUBLIC and cannot read the private
# Registry at runtime, so a copy is unavoidable here. It is therefore a copy
# under obligation: if the Registry text changes, this MUST be re-synced in the
# same touch. A mechanical arm comparing the two is owed (see Team AI SB).
# ---------------------------------------------------------------------------
DISCLAIMER_FULL = (
    "We are not licensed, regulated, or accredited by any government "
    "authority, professional body, or educational institution, and nothing we "
    "provide constitutes professional advice or any service that requires such "
    "licensing or regulation. Our role is to support your own thinking and "
    "decisions to the extent of our ability — including by helping you frame "
    "questions and identify issues to raise with your duly licensed and trained "
    "professional advisers. Always seek their advice on such matters."
)

# ---------------------------------------------------------------------------
# Report metadata
# ---------------------------------------------------------------------------
REPORT_TITLE = "Market Monitor"
REPORT_VERSION = f"Phase {PHASE}"
# REPORT_TIMEZONE moved above, next to now_report() — it is the report clock's
# input, not a metadata label, and two copies of it would fork.
REPORT_SCHEDULE = "07:00 and 19:00 SGT daily (23:00 and 11:00 UTC)"

# ---------------------------------------------------------------------------
# Email: no config constants — emailer.py reads its own env contract directly
# (GMAIL_APP_PASSWORD / EMAIL_SENDER / EMAIL_RECIPIENTS, injected by GitHub
# Actions secrets). A parallel EMAIL_* block here was dead code that nothing
# read, with a mismatched password var — removed 2026-07-15 (CF-9 / F-7).
# ---------------------------------------------------------------------------
