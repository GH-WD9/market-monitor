"""
data_fetcher.py — All market data retrieval
Phase 2e: MAS SGS colspan-aware parser; RBA_CASH_SERIES = FIRMMCRTD
Phase 2f: MAS SGS col_map row[1] fix; sub-header row[3]; 6M T-bill as cash_rate
Phase 2g: 30Y yields — MoF CSV, ChinaBond assess, ECB/BoC/SGS 30Y, BoE IUDLNPY
Phase 2h: MoF skiprows=1 fix; BoE ZIP fetcher (true 2Y/30Y); ChinaBond real scraper;
          BOE_SERIES '30y' key fix (was '20y')
Phase 2i: BoE ZIP multi-candidate sheet selection; Japan 2Y from MoF CSV;
          ChinaBond 2-col scraper (cash_rate/2Y/10Y/30Y); Australia 2Y (FCMYGBAG2D)
Phase 2j: ChinaBond fix — two-step POST to ycDetail XHR endpoint (was GET to page shell)
Phase 2k: Energy commodities (WTI/Brent/NatGas) switched from FRED EIA spot to yfinance
          front-month futures (CL=F/BZ=F/NG=F); COMMODITY_FRED retired
Phase 3c: ChinaBond timeout 10s→25s; 1 retry added; FRED monthly fallback for all China
          tenors on ChinaBond failure. RBA dayfirst warning suppressed.
"""

import os
import pickle
import time
import logging
from datetime import datetime, timedelta, date
from io import StringIO, BytesIO

import requests
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup

from config import (
    FRED_API_KEY, FRED_BASE_URL,
    CACHE_DIR, CACHE_MAX_AGE_HOURS,
    US_FRED_RATES, JAPAN_FRED, JAPAN_MOF_URL, CHINA_FRED, CHINABOND_URL, CHINABOND_API_URL, RBA_FRED,
    ECB_BASE_URL, ECB_SERIES,
    BOE_BASE_URL, BOE_SERIES, BOE_ZIP_URL,
    BOC_BASE_URL, BOC_SERIES,
    RBA_CASH_URL, RBA_CASH_SERIES, RBA_YIELDS_URL, RBA_YIELDS_SERIES,
    MAS_SORA_API_URL, MAS_SORA_URL, MAS_SGS_URL,
    CREDIT_FRED_SERIES, GBP_IG_FALLBACK_TICKER,
    EQUITY_INDICES, STRESS_TICKERS,
    REIT_TICKERS, COMMODITY_YFINANCE,
    FX_FRED, FX_YFINANCE,
)

logger = logging.getLogger(__name__)
os.makedirs(CACHE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Shared session (connection pooling)
# ---------------------------------------------------------------------------
SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json, text/csv, */*"})

# ---------------------------------------------------------------------------
# FRED cache helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> str:
    safe = key.replace("/", "_").replace(".", "_")
    return os.path.join(CACHE_DIR, f"{safe}.pkl")


def _load_cache(key: str):
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            ts, data = pickle.load(f)
        age_hours = (datetime.now() - ts).total_seconds() / 3600
        if age_hours < CACHE_MAX_AGE_HOURS:
            return data
    except Exception:
        pass
    return None


def _save_cache(key: str, data):
    try:
        with open(_cache_path(key), "wb") as f:
            pickle.dump((datetime.now(), data), f)
    except Exception as e:
        logger.warning(f"Cache save failed for {key}: {e}")


# ---------------------------------------------------------------------------
# FRED — single series, with cache
# ---------------------------------------------------------------------------

def fetch_fred_cached(series_id: str, lookback_days: int = 2600) -> pd.Series:
    """
    Fetch a FRED series, using the local cache if fresh.
    Returns a pd.Series with DatetimeIndex, float values, name=series_id.
    """
    cached = _load_cache(series_id)
    if cached is not None:
        return cached

    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    params = {
        "series_id":       series_id,
        "observation_start": start_date,
        "api_key":         FRED_API_KEY,
        "file_type":       "json",
    }
    try:
        resp = SESSION.get(FRED_BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        obs = resp.json().get("observations", [])
        s = pd.Series(
            {o["date"]: float(o["value"]) for o in obs if o["value"] not in (".", "")},
            name=series_id,
            dtype=float,
        )
        s.index = pd.to_datetime(s.index)
        s.sort_index(inplace=True)
        _save_cache(series_id, s)
        time.sleep(0.6)   # Phase 3b: avoid FRED 429s (120 req/min limit)
        return s
    except Exception as e:
        logger.error(f"FRED fetch failed [{series_id}]: {e}")
        return pd.Series(name=series_id, dtype=float)


# ---------------------------------------------------------------------------
# yfinance — equity, ETF, futures
# ---------------------------------------------------------------------------

def fetch_yfinance(ticker: str, lookback_days: int = 3700) -> pd.Series:
    """
    Fetch adjusted close prices for a yfinance ticker.
    Returns pd.Series with DatetimeIndex, float values, name=ticker.
    lookback_days=3700 (~10.1 years): extended from 2600 to populate 10Y return column
    (2520 trading-day minimum requires ~3650 calendar days of history).
    """
    start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    try:
        raw = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if raw.empty:
            logger.warning(f"yfinance returned empty for {ticker}")
            return pd.Series(name=ticker, dtype=float)
        # Handle MultiIndex columns (yfinance >=0.2 may return MultiIndex)
        if isinstance(raw.columns, pd.MultiIndex):
            if ("Close", ticker) in raw.columns:
                s = raw[("Close", ticker)].dropna()
            else:
                s = raw["Close"].squeeze().dropna()
        else:
            s = raw["Close"].dropna()
        s.name = ticker
        return s
    except Exception as e:
        logger.error(f"yfinance fetch failed [{ticker}]: {e}")
        return pd.Series(name=ticker, dtype=float)


def fetch_yfinance_multi(tickers: list, lookback_days: int = 3700) -> dict:
    """Fetch multiple yfinance tickers; returns {ticker: pd.Series}."""
    return {t: fetch_yfinance(t, lookback_days) for t in tickers}


# ---------------------------------------------------------------------------
# Section 0 — Market Stress
# ---------------------------------------------------------------------------

def fetch_stress_data() -> dict:
    """Returns {ticker: pd.Series} for VIX, Gold, Silver, Copper."""
    tickers = list(STRESS_TICKERS.keys())
    return fetch_yfinance_multi(tickers)


# ---------------------------------------------------------------------------
# Section 1 — Equity Indices
# ---------------------------------------------------------------------------

def fetch_equity_data() -> dict:
    """Returns {ticker: pd.Series} for all equity indices."""
    tickers = list(EQUITY_INDICES.keys())
    return fetch_yfinance_multi(tickers)


# ---------------------------------------------------------------------------
# Section 2 — Government Bonds: US (FRED)
# ---------------------------------------------------------------------------

def fetch_us_rates() -> dict:
    """Returns {key: pd.Series} — Fed funds, 3M, 2Y, 10Y, 30Y."""
    return {k: fetch_fred_cached(v) for k, v in US_FRED_RATES.items()}


# ---------------------------------------------------------------------------
# Section 2 — Government Bonds: Eurozone (ECB API)
# ---------------------------------------------------------------------------

def _ecb_fetch(series_key: str, lookback_days: int = 400) -> pd.Series:
    """
    Fetch a single ECB SDMX series via the newer data-api.ecb.europa.eu endpoint.
    Returns pd.Series with DatetimeIndex.
    """
    cached = _load_cache(f"ECB_{series_key}")
    if cached is not None:
        return cached

    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    url = f"{ECB_BASE_URL}/{series_key}"
    params = {
        "format":          "csvdata",
        "startPeriod":     start_date,
        "detail":          "dataonly",
    }
    try:
        resp = SESSION.get(url, params=params, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        # ECB CSV has columns like TIME_PERIOD, OBS_VALUE
        if "OBS_VALUE" not in df.columns or "TIME_PERIOD" not in df.columns:
            logger.warning(f"ECB unexpected columns for {series_key}: {df.columns.tolist()}")
            return pd.Series(name=series_key, dtype=float)
        df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"])
        s = df.set_index("TIME_PERIOD")["OBS_VALUE"].dropna().astype(float)
        s.index.name = "date"
        s.name = series_key
        s.sort_index(inplace=True)
        _save_cache(f"ECB_{series_key}", s)
        return s
    except Exception as e:
        logger.error(f"ECB fetch failed [{series_key}]: {e}")
        return pd.Series(name=series_key, dtype=float)


def fetch_ecb_rates() -> dict:
    """Returns {key: pd.Series} — ECB deposit rate, 2Y, 10Y."""
    # ECB DFR (cash_rate) updates on 6-week meeting cycle — sparse by policy design.
    # 1200-day lookback required: 800 days from May 2026 reaches only March 2024;
    # first ECB cut was June 2024 — pre-cut baseline needed for 1Y_bps calculation.
    # Note: delete cache/ECB_cash_rate*.pkl if fix has no effect (4h cache).
    lookback = {"cash_rate": 1200}  # 2c-5: extended from 800 days
    return {k: _ecb_fetch(v, lookback_days=lookback.get(k, 400)) for k, v in ECB_SERIES.items()}


# ---------------------------------------------------------------------------
# Section 2 — Government Bonds: UK (BoE IADB)
# ---------------------------------------------------------------------------

def _boe_fetch(series_code: str, lookback_days: int = 400) -> pd.Series:
    """
    Fetch a BoE IADB series via CSV endpoint.
    Returns pd.Series with DatetimeIndex.
    ⚠️ Series codes for gilt yields need first-run verification.
    """
    cached = _load_cache(f"BOE_{series_code}")
    if cached is not None:
        return cached

    today = datetime.now()
    d_from = today - timedelta(days=lookback_days)
    # %-d/%-b are Linux-only; build cross-platform date strings manually
    from_date = f"{d_from.day}/{d_from.strftime('%b')}/{d_from.year}"
    to_date = f"{today.day}/{today.strftime('%b')}/{today.year}"

    params = {
        "csv.x":       "yes",
        "DATEFROM":    from_date,
        "DATETO":      to_date,
        "SeriesCodes": series_code,
        "UsingCodes":  "Y",
        "CSVF":        "TT",
        "html.x":      "66",
        "html.y":      "26",
        "FNY":         "Y",
        "VPD":         "Y",
    }
    # BoE IADB requires browser-like headers to avoid 403
    boe_headers = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer":         "https://www.bankofengland.co.uk/boeapps/database/",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        resp = SESSION.get(BOE_BASE_URL, params=params, headers=boe_headers, timeout=15)
        resp.raise_for_status()
        text = resp.text
        if "not found" in text.lower() or len(text) < 50:
            logger.warning(f"BoE series not found or empty: {series_code}")
            return pd.Series(name=series_code, dtype=float)
        try:
            df = pd.read_csv(StringIO(text), skiprows=0)
        except pd.errors.ParserError:
            # Some BoE series (e.g. IUDMNZS) have inconsistent column counts —
            # retry with python engine which is more permissive
            logger.warning(f"BoE CSV tokenization error for {series_code} — retrying with python engine")
            df = pd.read_csv(StringIO(text), skiprows=0, engine='python', on_bad_lines='skip')
        # Always keep only first 2 columns (date + value); handles multi-column responses
        df = df.iloc[:, :2]
        df.columns = df.columns.str.strip()
        date_col = df.columns[0]
        val_col = df.columns[1] if len(df.columns) > 1 else None
        if val_col is None:
            return pd.Series(name=series_code, dtype=float)
        # BoE IADB date format varies — try formats in order; log sample on total failure.
        # Observed formats include: "20 May 26" (%d %b %y), "20 May 2026" (%d %b %Y)
        raw_dates = df[date_col].copy()
        parsed = None
        for fmt in ('%d %b %y', '%d %b %Y', '%d/%b/%Y', '%d/%m/%Y', '%Y-%m-%d'):
            attempt = pd.to_datetime(raw_dates, format=fmt, errors='coerce')
            if attempt.notna().sum() > 0:
                parsed = attempt
                logger.info(f"BoE [{series_code}]: date format '{fmt}' matched ({attempt.notna().sum()} rows)")
                break
        if parsed is None or parsed.notna().sum() == 0:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(raw_dates, dayfirst=True, errors='coerce')
            sample = raw_dates.dropna().head(3).tolist()
            if parsed.notna().sum() == 0:
                logger.warning(f"BoE [{series_code}]: all date formats failed — raw sample: {sample}")
                return pd.Series(name=series_code, dtype=float)
            logger.info(f"BoE [{series_code}]: date inferred; raw sample: {sample}")
        df[date_col] = parsed
        s = df.dropna(subset=[date_col]).set_index(date_col)[val_col]
        s = pd.to_numeric(s, errors="coerce").dropna()
        s.index.name = "date"
        s.name = series_code
        s.sort_index(inplace=True)
        if not s.empty:
            _save_cache(f"BOE_{series_code}", s)
        else:
            logger.warning(f"BoE [{series_code}]: parsed but no numeric values — not caching")
        return s
    except Exception as e:
        logger.error(f"BoE fetch failed [{series_code}]: {e}")
        return pd.Series(name=series_code, dtype=float)


def _boe_zip_fetch() -> dict:
    """
    Fetch BoE nominal gilt par yield curve from the daily ZIP file.
    URL: BOE_ZIP_URL (latest-yield-curve-data.zip)
    Published by BoE by noon the following business day.
    ZIP contains multiple Excel files; we want the nominal par curve file.
    File naming pattern: 'GLC Nominal daily data_*' (confirmed from BoE archive structure).
    Sheet structure (from BoE documentation): header rows 0-3 are metadata;
      row 3 is the column header with maturity values as decimals (0.5, 1, 2, 5, 10, 20, 25, 30).
      Sheet names: '1. par curve' (or similar numbering); date in index column 0.
    Returns {tenor_key: pd.Series} for 2y, 5y, 10y, 20y, 30y.
    Falls back to empty dict on any failure — IADB scrapers remain as fallback.
    Phase 2h: new source; first-run verification required for sheet/column names.
    """
    import zipfile

    cache_key = "BOE_ZIP"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    try:
        resp = SESSION.get(BOE_ZIP_URL, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bankofengland.co.uk/statistics/yield-curves",
        })
        resp.raise_for_status()

        zf = zipfile.ZipFile(BytesIO(resp.content))
        filenames = zf.namelist()
        logger.info(f"BoE ZIP: {len(filenames)} file(s): {filenames}")

        # Find the nominal par curve Excel file
        # BoE naming: 'GLC Nominal daily data_YYYY.xlsx' or 'fwd_curve_nominal.xlsx'
        target = None
        for name in filenames:
            name_lower = name.lower()
            if 'nominal' in name_lower and ('daily' in name_lower or 'par' in name_lower) and name_lower.endswith('.xlsx'):
                target = name
                break
        if target is None:
            # Fallback: first xlsx containing 'nominal'
            for name in filenames:
                if 'nominal' in name.lower() and name.lower().endswith('.xlsx'):
                    target = name
                    break
        if target is None:
            logger.warning(f"BoE ZIP: no nominal xlsx found in {filenames}")
            return {}

        logger.info(f"BoE ZIP: using file '{target}'")
        xlsx_bytes = zf.read(target)

        # Inspect sheet names
        import openpyxl
        wb = openpyxl.load_workbook(BytesIO(xlsx_bytes), read_only=True, data_only=True)
        sheets = wb.sheetnames
        logger.info(f"BoE ZIP: sheets = {sheets}")

        # Target the par/spot curve sheet — multi-candidate search for robustness
        # BoE ZIP sheets confirmed: ['info', '1. fwds, short end', '2. fwd curve', '3. spot, short end', '4. spot curve']
        # Priority: 'par curve' → 'spot curve' → any sheet with 'spot' → any sheet with 'curve' → sheet index 1
        par_sheet = None
        for candidate in ('par curve', 'spot curve', 'par', 'spot', 'curve'):
            for s in sheets:
                if candidate in s.lower():
                    par_sheet = s
                    break
            if par_sheet:
                break
        if par_sheet is None:
            par_sheet = sheets[1] if len(sheets) > 1 else sheets[0]
        wb.close()

        logger.info(f"BoE ZIP: using sheet '{par_sheet}'")
        # BoE format: first 3 rows are metadata/title; row 4 (header=3) has maturity columns
        # Columns: date (index) | 0.5 | 1 | 2 | 3 | 5 | 7 | 10 | 15 | 20 | 25 | 30 | ...
        df = pd.read_excel(BytesIO(xlsx_bytes), sheet_name=par_sheet, header=3, index_col=0, engine='openpyxl')
        df.index = pd.to_datetime(df.index, errors='coerce')
        df = df[df.index.notna()]
        logger.info(f"BoE ZIP: {len(df)} rows; columns = {df.columns.tolist()[:15]}")

        # Map decimal maturity columns to tenor keys
        # Column headers may be numeric (2.0, 5.0, 10.0...) or string ('2', '5', '10'...)
        results = {}
        tenor_targets = {'2y': 2.0, '5y': 5.0, '10y': 10.0, '20y': 20.0, '30y': 30.0}
        for tenor_key, target_mat in tenor_targets.items():
            best_col = None
            best_diff = 0.3  # tolerance: within 0.3Y
            for col in df.columns:
                try:
                    col_val = float(col)
                    diff = abs(col_val - target_mat)
                    if diff < best_diff:
                        best_diff = diff
                        best_col = col
                except (ValueError, TypeError):
                    continue
            if best_col is not None:
                s = pd.to_numeric(df[best_col], errors='coerce').dropna()
                s.name = f"BOE_ZIP_{tenor_key.upper()}"
                if not s.empty:
                    results[tenor_key] = s
                    logger.info(f"BoE ZIP: {tenor_key} → col '{best_col}' ({len(s)} rows, latest {s.index[-1].date()} = {s.iloc[-1]:.3f}%)")
            else:
                logger.warning(f"BoE ZIP: no column found for {tenor_key} (target {target_mat})")

        if results:
            _save_cache(cache_key, results)
        return results

    except Exception as e:
        logger.error(f"BoE ZIP fetch failed: {e}")
        return {}


def fetch_boe_rates() -> dict:
    """
    Returns {key: pd.Series} — BoE base rate + gilt yields.
    Cash rate: IADB IUDBEDR (Official Bank Rate) — sparse, keep IADB.
    Gilt yields (2y, 5y, 10y, 20y, 30y): BoE ZIP par curve — Phase 2h upgrade.
      ZIP provides true 2Y and 30Y, replacing IADB proxies (IUDSNPY=5Y, IUDLNPY=20Y).
      Falls back to IADB per-series if ZIP fetch fails.
    Phase 2h: '30y' key fix (was '20y') ensures IUDLNPY displays in report long-end slot.
    """
    results = {}

    # Cash rate always from IADB (not in ZIP)
    results["cash_rate"] = _boe_fetch("IUDBEDR")

    # Gilt yields: try ZIP first; fall back to IADB per series
    zip_data = _boe_zip_fetch()

    for key, code in BOE_SERIES.items():
        if key == "cash_rate":
            continue  # already fetched above
        if key in zip_data and not zip_data[key].empty:
            results[key] = zip_data[key]
        else:
            # IADB fallback
            s = _boe_fetch(code)
            results[key] = s
            if not s.empty:
                logger.info(f"BoE: {key} using IADB fallback ({code})")

    # Fallback flag for 10Y (FRED monthly) if both ZIP and IADB empty
    if results.get("10y") is None or (isinstance(results.get("10y"), pd.Series) and results["10y"].empty):
        logger.warning("BoE 10Y: both ZIP and IADB empty — FRED monthly fallback")
        results["10y"] = fetch_fred_cached("IRLTLT01GBM156N", lookback_days=2600)
        results["10y_is_monthly"] = True
    else:
        results["10y_is_monthly"] = False

    results["2y_is_empty"] = results.get("2y") is None or (isinstance(results.get("2y"), pd.Series) and results["2y"].empty)
    return results


# ---------------------------------------------------------------------------
# Section 2 — Government Bonds: Canada (BoC Valet API)
# ---------------------------------------------------------------------------

def _boc_fetch(series_id: str, lookback_days: int = 400) -> pd.Series:
    """
    Fetch a BoC Valet API series.
    Returns pd.Series with DatetimeIndex.
    ⚠️ Bond yield series need first-run verification.
    """
    cached = _load_cache(f"BOC_{series_id}")
    if cached is not None:
        return cached

    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    url = f"{BOC_BASE_URL}/{series_id}/json"
    params = {"start_date": start_date}
    try:
        resp = SESSION.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        observations = data.get("observations", [])
        records = {}
        for obs in observations:
            d = obs.get("d")
            v = obs.get(series_id, {}).get("v")
            if d and v and v != "":
                try:
                    records[d] = float(v)
                except (ValueError, TypeError):
                    pass
        if not records:
            logger.warning(f"BoC series empty: {series_id}")
            return pd.Series(name=series_id, dtype=float)
        s = pd.Series(records, name=series_id, dtype=float)
        s.index = pd.to_datetime(s.index)
        s.sort_index(inplace=True)
        _save_cache(f"BOC_{series_id}", s)
        return s
    except Exception as e:
        logger.error(f"BoC fetch failed [{series_id}]: {e}")
        return pd.Series(name=series_id, dtype=float)


def fetch_boc_rates() -> dict:
    """Returns {key: pd.Series} — overnight rate, 2Y, 10Y."""
    return {k: _boc_fetch(v) for k, v in BOC_SERIES.items()}


# ---------------------------------------------------------------------------
# Section 2 — Government Bonds: Australia (RBA xlsx + FRED monthly fallback)
# ---------------------------------------------------------------------------

def _rba_fetch_xlsx(url: str, series_code: str, lookback_days: int = 400) -> pd.Series:
    """
    Parse RBA F-table xlsx format (f01d.xlsx / f02d.xlsx).
    Structure: metadata rows (title, freq, series ID, description, units, source),
    then data rows with date in first column.
    Scans all rows for the series_code column index, then parses data rows below it.
    Returns pd.Series with DatetimeIndex; empty series on any failure.
    Phase 2d: replaces _rba_fetch_csv — f01hist.csv / f02hist.csv do not exist.
    """
    cache_key = f"RBA_{series_code}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()

        # Read all rows without header to scan for series code
        df_raw = pd.read_excel(BytesIO(resp.content), header=None, engine='openpyxl')

        col_idx = None
        data_start = None

        for i, row in df_raw.iterrows():
            row_vals = [str(v).strip() if pd.notna(v) else '' for v in row]
            # Find the row containing the series code
            if col_idx is None and series_code in row_vals:
                col_idx = row_vals.index(series_code)
                logger.info(f"RBA: found '{series_code}' at column {col_idx} (row {i})")
                continue
            # Data rows: first cell must parse as a date (try after series code row)
            if col_idx is not None and data_start is None and row_vals[0]:
                try:
                    pd.to_datetime(row_vals[0], dayfirst=True)
                    data_start = i
                except Exception:
                    pass

        if col_idx is None:
            # Dump rows 0-14 to show actual series codes — one-time diagnostic
            try:
                preview_rows = []
                for ri in range(min(15, len(df_raw))):
                    row_vals = [str(v).strip() if pd.notna(v) else '' for v in df_raw.iloc[ri]]
                    preview_rows.append(' | '.join(row_vals[:8]))  # first 8 cols only
                logger.warning(
                    f"RBA: series '{series_code}' not found in {url}\n"
                    f"First 15 rows (cols 0-7):\n" + '\n'.join(preview_rows)
                )
            except Exception:
                logger.warning(f"RBA: series '{series_code}' not found in {url}")
            return pd.Series(name=series_code, dtype=float)
        if data_start is None:
            logger.warning(f"RBA: no data rows found for '{series_code}' in {url}")
            return pd.Series(name=series_code, dtype=float)

        cutoff = (datetime.now() - timedelta(days=lookback_days)).date()
        records = {}
        for i in range(data_start, len(df_raw)):
            row = df_raw.iloc[i]
            date_val = row.iloc[0]
            if pd.isna(date_val) or str(date_val).strip() == '':
                continue
            try:
                # Handle both Excel datetime objects and string dates
                if isinstance(date_val, (datetime, pd.Timestamp)):
                    d = pd.Timestamp(date_val).date()
                else:
                    d = pd.to_datetime(str(date_val).strip(), dayfirst=False).date()
                if d < cutoff:
                    continue
                val_val = row.iloc[col_idx] if len(row) > col_idx else None
                if val_val is None or pd.isna(val_val):
                    continue
                val_str = str(val_val).strip()
                if val_str in ('', 'nan', '-', 'n.a.', 'N/A', 'na'):
                    continue
                records[str(d)] = float(val_str)
            except Exception:
                continue

        if not records:
            logger.warning(f"RBA: no valid data rows parsed for '{series_code}' from {url}")
            return pd.Series(name=series_code, dtype=float)

        s = pd.Series(records, dtype=float, name=series_code)
        s.index = pd.to_datetime(s.index)
        s.sort_index(inplace=True)
        _save_cache(cache_key, s)
        logger.info(f"RBA: '{series_code}' — {len(s)} rows, latest: {s.index[-1].date()}")
        return s

    except Exception as e:
        logger.warning(f"RBA xlsx fetch failed ['{series_code}' @ {url}]: {e}")
        return pd.Series(name=series_code, dtype=float)


def fetch_rba_rates() -> dict:
    """
    Australia: RBA xlsx (daily) with FRED monthly fallback.
    Cash rate: f01d.xlsx, series FIRMMCRTD (Phase 2e: corrected from FIRMMCRT).
    10Y AGS yield: f02d.xlsx, series FCMYGBAG10D.
    Falls back to FRED monthly (RBA_FRED) on any fetch failure.
    Phase 2d: replaces CSV fetcher — f01hist/f02hist.csv do not exist on RBA site.
    """
    results = {}

    # Cash rate: RBA xlsx → FRED monthly fallback
    s_cash = _rba_fetch_xlsx(RBA_CASH_URL, RBA_CASH_SERIES)
    if not s_cash.empty:
        results["cash_rate"] = s_cash
    else:
        results["cash_rate"] = fetch_fred_cached(RBA_FRED["cash_rate"])
        logger.warning("RBA: cash rate falling back to FRED monthly")

    # 2Y AGS yield: RBA xlsx (Phase 2i — confirmed in f02d.xlsx)
    if RBA_YIELDS_SERIES.get("2y"):
        s_2y = _rba_fetch_xlsx(RBA_YIELDS_URL, RBA_YIELDS_SERIES["2y"])
        if not s_2y.empty:
            results["2y"] = s_2y
        # No FRED fallback for Australia 2Y

    # 10Y AGS yield: RBA xlsx → FRED monthly fallback
    if RBA_YIELDS_SERIES.get("10y"):
        s_10y = _rba_fetch_xlsx(RBA_YIELDS_URL, RBA_YIELDS_SERIES["10y"])
        if not s_10y.empty:
            results["10y"] = s_10y
        else:
            results["10y"] = fetch_fred_cached(RBA_FRED["10y"])
            logger.warning("RBA: 10Y yield falling back to FRED monthly")
    else:
        results["10y"] = fetch_fred_cached(RBA_FRED["10y"])

    return results


# ---------------------------------------------------------------------------
# Section 2 — Government Bonds: Singapore (MAS HTML scrapers)
# Phase 2d: MAS apimg JSON API returns 404 — no JSON API exists.
# SORA: HTML table at DomesticInterestRates.aspx
# SGS yields (2Y, 5Y, 10Y): HTML table at SgsBenchmarkIssuePrices.aspx
# Both scrapers use persistent accumulation cache so bps changes build up over time.
# ---------------------------------------------------------------------------

def _mas_load_history(key: str) -> pd.Series:
    """
    Load persistent MAS history for a series key (no age expiry — accumulates indefinitely).
    Separate from the main FRED cache (which has 4h expiry).
    """
    path = os.path.join(CACHE_DIR, f"mas_hist_{key}.pkl")
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                s = pickle.load(f)
            if isinstance(s, pd.Series):
                return s
        except Exception:
            pass
    return pd.Series(dtype=float, name=key)


def _mas_save_history(key: str, s: pd.Series):
    """Save persistent MAS history."""
    path = os.path.join(CACHE_DIR, f"mas_hist_{key}.pkl")
    try:
        with open(path, "wb") as f:
            pickle.dump(s, f)
    except Exception as e:
        logger.warning(f"MAS history save failed [{key}]: {e}")


def _mas_merge_and_save(key: str, new_data: pd.Series) -> pd.Series:
    """Merge new_data into persistent history, deduplicate, sort, save and return."""
    existing = _mas_load_history(key)
    if new_data.empty:
        return existing
    combined = pd.concat([existing, new_data])
    combined = combined[~combined.index.duplicated(keep='last')]
    combined.sort_index(inplace=True)
    combined.name = key
    _mas_save_history(key, combined)
    return combined


def _mas_already_fetched_today(key: str) -> bool:
    """Return True if we already have today's date in the history cache."""
    s = _mas_load_history(key)
    if s.empty:
        return False
    today = pd.Timestamp(date.today())
    return today in s.index


_MAS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-SG,en;q=0.9",
}


def _mas_html_sora() -> pd.Series:
    """
    Fetch SORA from MAS.
    Strategy 0 (Phase 2e): CKAN /api/ JSON endpoint — fast, reliable if it works.
    Strategy A (HTML): column-header scan for 'sora' in table header.
    Strategy B (HTML): row-label scan for 'sora' in first cell.
    Falls back to cached history if all strategies fail (e.g. JS-rendered page).
    Uses persistent accumulation cache — each day adds one data point for bps history.
    """
    if _mas_already_fetched_today("SGD_SORA"):
        return _mas_load_history("SGD_SORA")

    records = {}

    # ------------------------------------------------------------------
    # Strategy 0: CKAN /api/ JSON endpoint
    # ------------------------------------------------------------------
    try:
        resp = SESSION.get(MAS_SORA_API_URL, timeout=10, headers=_MAS_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            api_records = data.get("result", {}).get("records", [])
            logger.info(f"MAS SORA API: status 200 — {len(api_records)} record(s) returned")
            if api_records:
                # Log field names from first record for diagnostic
                sample_fields = list(api_records[0].keys())
                logger.info(f"MAS SORA API: fields in first record: {sample_fields}")
                for rec in api_records:
                    # Find date field (common: 'end_of_day', 'date', 'published_date')
                    date_val = (rec.get("end_of_day") or rec.get("date")
                                or rec.get("published_date") or rec.get("Date"))
                    if not date_val:
                        continue
                    # Find SORA overnight field: prefer 'comp_sora_1d', 'overnight_rate';
                    # fall back to any key containing 'sora' that isn't 1m/3m/6m/12m
                    sora_val = (rec.get("comp_sora_1d") or rec.get("overnight_rate")
                                or rec.get("sora") or rec.get("SORA"))
                    if sora_val is None:
                        # Scan for sora key not containing month suffixes
                        for k, v in rec.items():
                            k_low = k.lower()
                            if 'sora' in k_low and not any(m in k_low for m in ('1m', '3m', '6m', '12m', '1y')):
                                sora_val = v
                                logger.info(f"MAS SORA API: using field '{k}' = {v}")
                                break
                    if sora_val is None:
                        continue
                    try:
                        d = str(pd.to_datetime(date_val).date())
                        records[d] = float(str(sora_val).replace(',', '').strip())
                    except Exception as ex:
                        logger.debug(f"MAS SORA API: could not parse record {rec}: {ex}")
                if records:
                    logger.info(f"MAS SORA API: {len(records)} date(s) parsed — Strategy 0 succeeded")
        else:
            logger.info(f"MAS SORA API: status {resp.status_code} — falling through to HTML strategies")
    except Exception as e:
        logger.info(f"MAS SORA API: request failed ({e}) — falling through to HTML strategies")

    # ------------------------------------------------------------------
    # Strategy A & B: HTML scrape (fallback — page may be JS-rendered)
    # ------------------------------------------------------------------
    if not records:
        try:
            resp = SESSION.get(MAS_SORA_URL, timeout=15, headers=_MAS_HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')

            all_tables = soup.find_all('table')
            logger.info(f"MAS SORA HTML: {len(all_tables)} table(s) found on page")
            for t_idx, table in enumerate(all_tables):
                rows = table.find_all('tr')
                if rows:
                    first_row = [c.get_text(strip=True) for c in rows[0].find_all(['th', 'td'])]
                    logger.info(f"MAS SORA HTML: table[{t_idx}] header: {first_row}")
                    if len(rows) > 1:
                        second_row = [c.get_text(strip=True) for c in rows[1].find_all(['th', 'td'])]
                        logger.info(f"MAS SORA HTML: table[{t_idx}] first data row: {second_row}")

            # Strategy A: SORA as column header
            for table in all_tables:
                header_row = table.find('tr')
                if not header_row:
                    continue
                header_cells = [c.get_text(strip=True) for c in header_row.find_all(['th', 'td'])]
                sora_col = next((i for i, h in enumerate(header_cells) if 'sora' in h.lower()), None)
                date_col = next((i for i, h in enumerate(header_cells) if 'date' in h.lower()), None)
                if sora_col is None:
                    continue
                if date_col is None:
                    date_col = 0
                logger.info(f"MAS SORA HTML Strategy A: date_col={date_col}, sora_col={sora_col}")
                for row in table.find_all('tr')[1:]:
                    cells = row.find_all('td')
                    if len(cells) <= max(date_col, sora_col):
                        continue
                    try:
                        d = pd.to_datetime(cells[date_col].get_text(strip=True)).date()
                        v = float(cells[sora_col].get_text(strip=True).replace(',', '').replace('%', ''))
                        records[str(d)] = v
                    except Exception:
                        continue

            # Strategy B: SORA as row label
            if not records:
                for table in all_tables:
                    for row in table.find_all('tr'):
                        cells = row.find_all(['td', 'th'])
                        if len(cells) < 2:
                            continue
                        label = cells[0].get_text(strip=True).lower()
                        if 'sora' not in label:
                            continue
                        logger.info(f"MAS SORA HTML Strategy B: row label '{cells[0].get_text(strip=True)}'")
                        snap_date = date.today()
                        for cell in cells[1:]:
                            val_text = cell.get_text(strip=True).replace('%', '').replace(',', '').strip()
                            if not val_text:
                                continue
                            try:
                                v = float(val_text)
                                records[str(snap_date)] = v
                                logger.info(f"MAS SORA HTML Strategy B: {v} for {snap_date}")
                                break
                            except ValueError:
                                try:
                                    snap_date = pd.to_datetime(cell.get_text(strip=True)).date()
                                except Exception:
                                    pass
        except Exception as e:
            logger.warning(f"MAS SORA HTML scrape failed: {e}")

    if records:
        new_data = pd.Series(records, dtype=float, name="SGD_SORA")
        new_data.index = pd.to_datetime(new_data.index)
        merged = _mas_merge_and_save("SGD_SORA", new_data)
        logger.info(f"MAS SORA: {len(new_data)} row(s) fetched, {len(merged)} total in history")
        return merged
    else:
        logger.warning("MAS SORA: all strategies failed — returning cached history")
        return _mas_load_history("SGD_SORA")


def _mas_html_sgs() -> dict:
    """
    Scrape SGS benchmark yields from MAS SgsBenchmarkIssuePrices.aspx.

    Page structure (confirmed from Phase 2e live run):
    - Table 0, multi-row header + data rows
    - Row 0: category headers — 'Treasury Bills', 'Bonds' (colspan spans; NOT tenor labels)
    - Row 1: tenor labels — '6-Mth', '1-Year', '2-Year', ... (col_map source — Phase 2f fix)
    - Row 2: issue codes / coupon / maturity (not used)
    - Row 3: sub-header — Yield/Price designations (Phase 2f fix)
    - Rows 3+: data rows — col 0 = date (date parse skips non-data rows gracefully),
               col 1 = 6M T-bill Yield, col 4 = 2Y Yield, col 6 = 5Y Yield, col 8 = 10Y Yield

    Primary approach: hardcoded TARGET_COLS (confirmed from diagnostic).
    Validation: colspan expansion from row 1 + Yield check from row 3 (with warnings if mismatch).
    Per-row date: each data row provides its own date — supports multi-day history from single fetch.
    Uses persistent accumulation cache — each run adds new date(s) to bps history.
    Returns dict: {'cash_rate': pd.Series, '2y': pd.Series, '5y': pd.Series, '10y': pd.Series}
    """
    keys = {"cash_rate": "SGS_6M", "2y": "SGS_2Y", "5y": "SGS_5Y", "10y": "SGS_10Y", "30y": "SGS_30Y"}
    all_fetched = all(_mas_already_fetched_today(v) for v in keys.values())
    if all_fetched:
        return {k: _mas_load_history(v) for k, v in keys.items()}

    empty = {k: _mas_load_history(v) for k, v in keys.items()}

    # Confirmed target columns (0-indexed, col 0 = date)
    TARGET_COLS = {"cash_rate": 1, "2y": 4, "5y": 6, "10y": 8, "30y": 14}

    try:
        resp = SESSION.get(MAS_SGS_URL, timeout=15, headers=_MAS_HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        all_tables = soup.find_all('table')
        logger.info(f"MAS SGS: page fetched OK — {len(all_tables)} table(s) found")

        if not all_tables:
            logger.warning("MAS SGS: no tables found — page may be JS-rendered")
            return empty

        # Use table 0 (confirmed from diagnostic)
        table = all_tables[0]
        rows = table.find_all('tr')
        logger.info(f"MAS SGS: table[0] has {len(rows)} rows")

        # Log header rows for diagnostic
        for i in range(min(4, len(rows))):
            cells = rows[i].find_all(['th', 'td'])
            cell_texts = [c.get_text(strip=True) for c in cells]
            logger.info(f"MAS SGS: header row[{i}]: {cell_texts}")

        if len(rows) < 4:
            logger.warning(f"MAS SGS: only {len(rows)} rows — expected 4+ (header rows 0-2 + data)")
            return empty

        # ------------------------------------------------------------------
        # Validate column positions via colspan expansion of row 0
        # ------------------------------------------------------------------
        col_map = {}  # physical_col → tenor label
        physical_col = 0
        for cell in rows[1].find_all(['th', 'td']):
            text = cell.get_text(strip=True).lower()
            try:
                span = int(cell.get('colspan', 1))
            except (ValueError, TypeError):
                span = 1
            for _ in range(span):
                col_map[physical_col] = text
                physical_col += 1
        logger.info(f"MAS SGS: colspan-expanded col_map: {col_map}")

        # Validate TARGET_COLS against col_map (warning only — hardcoded cols take priority)
        # cash_rate key maps to the 6-mth T-bill column — different naming convention
        _EXPECTED_LABELS = {
            "cash_rate": "6-mth",
            "30y": "30-year",
        }
        for tenor, col_idx in TARGET_COLS.items():
            expected_label = _EXPECTED_LABELS.get(tenor, tenor.replace('y', '-year'))  # '2y' → '2-year'
            actual_label = col_map.get(col_idx, 'unknown')
            if expected_label not in actual_label and expected_label.replace('-', ' ') not in actual_label:
                logger.warning(
                    f"MAS SGS: col_map mismatch for {tenor}: "
                    f"col {col_idx} maps to '{actual_label}' (expected '{expected_label}') — "
                    f"using hardcoded col anyway; update TARGET_COLS if data is wrong"
                )
            else:
                logger.info(f"MAS SGS: {tenor} col {col_idx} validated — label='{actual_label}'")

        # Validate Yield designation from row 3 (sub-headers offset by 1: no date col)
        if len(rows) > 3:
            sub_cells = rows[3].find_all(['th', 'td'])
            sub_texts = [c.get_text(strip=True).lower() for c in sub_cells]
            logger.info(f"MAS SGS: row[3] sub-headers (no date col): {sub_texts}")
            for tenor, col_idx in TARGET_COLS.items():
                sub_idx = col_idx - 1  # sub_texts has no date col
                if sub_idx < len(sub_texts):
                    label = sub_texts[sub_idx]
                    if 'yield' not in label:
                        logger.warning(
                            f"MAS SGS: row[2] col {col_idx} (sub_idx={sub_idx}) = '{label}' "
                            f"(expected 'yield') — may be a Price column"
                        )

        # ------------------------------------------------------------------
        # Parse data rows (rows[3:]) — per-row date from col 0
        # ------------------------------------------------------------------
        new_records = {k: {} for k in keys}
        data_row_count = 0

        for row in rows[3:]:
            cells = row.find_all('td')
            if not cells:
                continue
            max_needed = max(TARGET_COLS.values())
            if len(cells) <= max_needed:
                logger.debug(f"MAS SGS: data row has only {len(cells)} cells (need {max_needed+1}) — skipping")
                continue

            # Date from col 0
            date_text = cells[0].get_text(strip=True)
            if not date_text:
                continue
            try:
                row_date = pd.to_datetime(date_text, dayfirst=True).date()
            except Exception:
                logger.debug(f"MAS SGS: could not parse date '{date_text}' — skipping row")
                continue

            data_row_count += 1
            for tenor_key, col_idx in TARGET_COLS.items():
                try:
                    val_text = cells[col_idx].get_text(strip=True).replace('%', '').replace(',', '').strip()
                    if not val_text or val_text in ('-', 'N/A', 'n/a', 'na', ''):
                        continue
                    v = float(val_text)
                    new_records[tenor_key][str(row_date)] = v
                    logger.info(f"MAS SGS: {tenor_key} = {v:.4f}% for {row_date}")
                except Exception as ex:
                    logger.debug(f"MAS SGS: could not parse {tenor_key} at col {col_idx} for {row_date}: {ex}")

        logger.info(f"MAS SGS: parsed {data_row_count} data row(s)")

        results = {}
        for tenor_key, hist_key in keys.items():
            if new_records[tenor_key]:
                new_s = pd.Series(new_records[tenor_key], dtype=float, name=hist_key)
                new_s.index = pd.to_datetime(new_s.index)
                merged = _mas_merge_and_save(hist_key, new_s)
                results[tenor_key] = merged
                logger.info(f"MAS SGS: {tenor_key} — {len(new_records[tenor_key])} new row(s), {len(merged)} total")
            else:
                logger.warning(f"MAS SGS: no new data for {tenor_key} — returning cached history")
                results[tenor_key] = _mas_load_history(hist_key)

        return results

    except Exception as e:
        logger.warning(f"MAS SGS scrape failed: {e}")
        return empty


def fetch_singapore_rates() -> dict:
    """
    Singapore: MAS HTML scrapers.
    cash_rate: MAS SGS 6M T-bill (col 1) — Phase 2f; SORA permanent gap confirmed Phase 2e.
    SGS yields (2Y, 5Y, 10Y, 30Y): SgsBenchmarkIssuePrices.aspx — Phase 2g adds 30Y (col 14).
    Both use persistent accumulation caches — bps change columns populate over time.
    No FRED fallback for Singapore.
    """
    sgs = _mas_html_sgs()
    return {
        "cash_rate": sgs.get("cash_rate", pd.Series(dtype=float, name="SGS_6M")),
        "2y":        sgs.get("2y",         pd.Series(dtype=float, name="SGS_2Y")),
        "5y":        sgs.get("5y",         pd.Series(dtype=float, name="SGS_5Y")),
        "10y":       sgs.get("10y",        pd.Series(dtype=float, name="SGS_10Y")),
        "30y":       sgs.get("30y",        pd.Series(dtype=float, name="SGS_30Y")),
    }


# ---------------------------------------------------------------------------
# Section 2 — Government Bonds: Japan (FRED monthly + MoF CSV for 30Y)
# ---------------------------------------------------------------------------
# Phase 2d: Stooq retired — now requires paid API key ("Get your apikey:").
# FRED monthly is the permanent Japan cash rate and 10Y source (no free daily source).
# Phase 2g: Japan 30Y (and potentially 10Y) via MoF CSV — daily JGB par yields.
# ---------------------------------------------------------------------------

def _mof_fetch() -> dict:
    """
    Fetch Japan JGB par yields from Ministry of Finance CSV.
    URL: https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv
    Returns {tenor_key: pd.Series} for available tenors (10y, 30y at minimum).
    Falls back to empty series on any failure — FRED monthly remains fallback for 10Y.
    Phase 2g: provides 30Y daily; if confirmed, can also replace FRED monthly for 10Y.
    """
    cache_key = "MOF_JGB"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    try:
        resp = SESSION.get(JAPAN_MOF_URL, timeout=15)
        resp.raise_for_status()
        # MoF CSV: first row is header with tenor names; no skip needed
        # Encoding is typically Shift-JIS or UTF-8 — try UTF-8 first then latin-1
        text = resp.content.decode('utf-8', errors='replace')
        # MoF CSV: row 0 is a metadata line ("Interest Rate (Month Year)"); row 1 is the real header.
        # skiprows=1 makes pandas use row 1 as the header → columns = ['Date','1Y','2Y'...'30Y','40Y']
        df = pd.read_csv(StringIO(text), skiprows=1)
        logger.info(f"MoF JGB: columns = {df.columns.tolist()}")
        logger.info(f"MoF JGB: {len(df)} rows; first row: {df.iloc[0].tolist() if not df.empty else 'empty'}")

        if df.empty:
            logger.warning("MoF JGB: empty CSV returned")
            return {}

        # Normalize column names: strip whitespace, lowercase
        df.columns = [str(c).strip() for c in df.columns]
        logger.info(f"MoF JGB: normalized columns = {df.columns.tolist()}")

        # Identify date column (first column)
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df = df.dropna(subset=[date_col])
        df = df.set_index(date_col)
        df.index.name = "date"

        # Map MoF column labels to our tenor keys
        # MoF CSV column names (English page): '1Y', '2Y', '5Y', '10Y', '20Y', '30Y', '40Y'
        # Actual column names confirmed from first run — update if different
        col_map = {}
        for col in df.columns:
            c_lower = col.lower().strip()
            if c_lower in ('2y', '2-year', '2 year', '2yr'):
                col_map['2y'] = col
            elif c_lower in ('10y', '10-year', '10 year', '10yr'):
                col_map['10y'] = col
            elif c_lower in ('30y', '30-year', '30 year', '30yr'):
                col_map['30y'] = col
            elif c_lower in ('20y', '20-year', '20 year', '20yr'):
                col_map['20y'] = col
        logger.info(f"MoF JGB: tenor col_map = {col_map}")

        results = {}
        for tenor_key, col_name in col_map.items():
            s = pd.to_numeric(df[col_name], errors='coerce').dropna()
            s.name = f"MOF_JGB_{tenor_key.upper()}"
            if not s.empty:
                results[tenor_key] = s
                logger.info(f"MoF JGB: {tenor_key} — {len(s)} rows, latest {s.index[-1].date()} = {s.iloc[-1]:.2f}%")
            else:
                logger.warning(f"MoF JGB: {tenor_key} column '{col_name}' has no numeric data")

        if results:
            _save_cache(cache_key, results)
        return results

    except Exception as e:
        logger.error(f"MoF JGB fetch failed: {e}")
        return {}


def fetch_japan_rates() -> dict:
    """
    Japan: FRED monthly for cash rate; MoF CSV (Phase 2g) for 30Y daily.
    If MoF CSV confirms 10Y daily, it replaces the FRED monthly 10Y.
    Cash rate: IRSTCI01JPM156N (BoJ policy rate ⚠️monthly — no free daily source).
    10Y JGB: MoF CSV daily if available, else FRED monthly IRLTLT01JPM156N (⚠️monthly).
    30Y JGB: MoF CSV daily — Phase 2g (permanent gap if MoF CSV fetch fails).
    """
    results = {k: fetch_fred_cached(v) for k, v in JAPAN_FRED.items()}

    # Phase 2g: attempt MoF CSV for 30Y (and 10Y upgrade if available)
    mof = _mof_fetch()
    if mof:
        if "30y" in mof and not mof["30y"].empty:
            results["30y"] = mof["30y"]
            logger.info("MoF JGB: 30Y confirmed — added to Japan rates")
        else:
            logger.warning("MoF JGB: 30Y not found in CSV — permanent gap for Japan 30Y")
            results["30y"] = pd.Series(dtype=float, name="MOF_JGB_30Y")

        # Upgrade 10Y and add 2Y to daily if MoF CSV provides them
        if "10y" in mof and not mof["10y"].empty:
            results["10y"] = mof["10y"]
            logger.info("MoF JGB: 10Y confirmed daily — replacing FRED monthly for Japan 10Y")
        if "2y" in mof and not mof["2y"].empty:
            results["2y"] = mof["2y"]
            logger.info("MoF JGB: 2Y confirmed daily — added to Japan rates")
    else:
        logger.warning("MoF JGB: fetch failed — Japan 30Y permanent gap; 10Y remains FRED monthly")
        results["30y"] = pd.Series(dtype=float, name="MOF_JGB_30Y")

    return results


def fetch_china_rates() -> dict:
    """
    China: ChinaBond live scraper for cash_rate (0Y), 2Y, 10Y, 30Y.
    On ChinaBond failure: cash_rate falls back to FRED PBOC deposit rate monthly;
    2Y/10Y/30Y have no FRED fallback (IRLTLT01CNM156N discontinued — None in config).
    Phase 2i: full ChinaBond extraction replaces FRED-only approach.
    Phase 3c: timeout raised to 25s, 1 retry added, FRED monthly fallback for all tenors.
    Phase 4a: None-guard added to FRED base dict; IRLTLT01CNM156N confirmed discontinued.
    """
    results = {k: fetch_fred_cached(v) for k, v in CHINA_FRED.items() if v is not None}  # FRED base fallback (None entries skipped)

    cb = _chinabond_assess()
    # Use ChinaBond daily data where available; fall back to FRED monthly otherwise
    if not cb.get("cash_rate", pd.Series(dtype=float)).empty:
        results["cash_rate"] = cb["cash_rate"]
    for key in ("2y", "10y", "30y"):
        cb_series = cb.get(key, pd.Series(dtype=float))
        if not cb_series.empty:
            results[key] = cb_series
        else:
            fred_fallback = CHINA_FRED.get(key)
            results[key] = fetch_fred_cached(fred_fallback) if fred_fallback else pd.Series(dtype=float, name=f"CHINABOND_{key.upper()}")
            if fred_fallback:
                logger.info(f"China {key}: ChinaBond unavailable — using FRED monthly fallback ({fred_fallback})")
    return results


def _chinabond_assess() -> dict:
    """
    Fetch China government bond yields via ChinaBond ycDetail XHR endpoint.
    Phase 2j: two-step — GET yield_main to acquire JSESSIONID, then POST to ycDetail.
    Response: HTML fragment; rows 0.0y/2.0y/10.0y/30.0y confirmed in DevTools (2026-05-30).
    Returns dict: {'cash_rate': pd.Series, '2y': pd.Series, '10y': pd.Series, '30y': pd.Series}
    Each series has today's date as the single index entry; empty on failure.
    """
    TARGETS = {
        'cash_rate': 0.0,   # 0.0y row = overnight/policy rate proxy
        '2y':        2.0,
        '10y':       10.0,
        '30y':       30.0,
    }
    TOLERANCE = 0.1

    results = {k: pd.Series(dtype=float, name=f"CHINABOND_{k.upper()}") for k in TARGETS}

    BROWSER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    }
    XHR_HEADERS = {
        **BROWSER_HEADERS,
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8,zh-CN;q=0.7,zh;q=0.6",
        "Origin": "https://yield.chinabond.com.cn",
        "Referer": "https://yield.chinabond.com.cn/cbweb-mn/yield_main?locale=en_US",
        "X-Requested-With": "XMLHttpRequest",
    }

    # Two attempts with 25s timeout; fall back to FRED monthly on both failing
    last_exc = None
    resp = None
    for attempt in range(2):
        try:
            SESSION.get(CHINABOND_URL, headers=BROWSER_HEADERS, timeout=25)
            resp = SESSION.post(CHINABOND_API_URL, headers=XHR_HEADERS, timeout=25)
            resp.raise_for_status()
            last_exc = None
            break
        except Exception as e:
            last_exc = e
            if attempt == 0:
                logger.warning(f"ChinaBond: attempt 1 failed ({e}) — retrying in 5s")
                time.sleep(5)

    if last_exc is not None:
        logger.warning(f"ChinaBond: fetch failed after 2 attempts ({last_exc}) — FRED monthly fallback active")
        return results

    try:
        soup = BeautifulSoup(resp.text, 'html.parser')
        tables = soup.find_all('table')
        logger.info(f"ChinaBond: status {resp.status_code} — {len(tables)} table(s)")

        today = pd.Timestamp(date.today())
        found = {}

        for table in tables:
            for row in table.find_all('tr'):
                cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
                if len(cells) < 2:
                    continue
                mat_text = cells[0].lower().replace('y', '').strip()
                try:
                    maturity = float(mat_text)
                    yield_val = float(cells[1])
                except (ValueError, IndexError):
                    continue
                for key, target in TARGETS.items():
                    if key not in found and abs(maturity - target) <= TOLERANCE:
                        found[key] = yield_val
                        logger.info(f"ChinaBond: {key} ({target}y) = {yield_val}%")

        for key, val in found.items():
            results[key] = pd.Series({today: val}, dtype=float, name=f"CHINABOND_{key.upper()}")

        missing = [k for k in TARGETS if k not in found]
        if missing:
            logger.warning(f"ChinaBond: no rows found for {missing} — FRED monthly fallback active for those tenors")
        if not found:
            logger.warning("ChinaBond: no yields extracted — page structure may have changed")

    except Exception as e:
        logger.warning(f"ChinaBond: parse failed ({e}) — FRED monthly fallback active")

    return results


def fetch_all_rates() -> dict:
    """
    Fetch all government bond / cash rate data.
    Returns nested dict: {geography: {key: pd.Series}}
    """
    return {
        "US":          fetch_us_rates(),
        "Eurozone":    fetch_ecb_rates(),
        "UK":          fetch_boe_rates(),
        "Canada":      fetch_boc_rates(),
        "Australia":   fetch_rba_rates(),
        "Singapore":   fetch_singapore_rates(),
        "Japan":       fetch_japan_rates(),
        "China":       fetch_china_rates(),
    }


# ---------------------------------------------------------------------------
# Section 3 — Credit OAS (FRED)
# ---------------------------------------------------------------------------

def fetch_all_credit_oas() -> dict:
    """
    Returns {label: pd.Series} for all confirmed FRED credit OAS series.
    EUR IG: no FRED series exists — omitted.
    GBP IG: SLXX.L ETF price omitted — ETF price cannot be meaningfully expressed as OAS bps.
    """
    results = {}
    for label, meta in CREDIT_FRED_SERIES.items():
        if meta["status"] == "confirmed":
            results[label] = fetch_fred_cached(meta["series"])
    return results


# ---------------------------------------------------------------------------
# Section 4 — REITs
# ---------------------------------------------------------------------------

def fetch_reit_data() -> dict:
    """Returns {ticker: pd.Series} for VNQ, VNQI."""
    return fetch_yfinance_multi(list(REIT_TICKERS.keys()))


# ---------------------------------------------------------------------------
# Section 5 — Commodities
# ---------------------------------------------------------------------------

def fetch_commodity_data() -> dict:
    """
    Returns {ticker: pd.Series} for all commodities via yfinance.
    Phase 2k: FRED EIA spot retired — all commodities now front-month futures.
    """
    return {ticker: fetch_yfinance(ticker) for ticker in COMMODITY_YFINANCE}


# ---------------------------------------------------------------------------
# Section 6 — FX and Digital Assets
# ---------------------------------------------------------------------------

def fetch_fx_data() -> dict:
    """
    Returns {series_or_ticker: pd.Series} for all FX and crypto.
    FRED series fetched with cache; BTC via yfinance.
    All returned as raw values — direction adjustment in calculator.py.
    """
    data = {}
    for series_id in FX_FRED:
        data[series_id] = fetch_fred_cached(series_id)
    for ticker in FX_YFINANCE:
        data[ticker] = fetch_yfinance(ticker)
    return data
