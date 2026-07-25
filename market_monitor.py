"""
market_monitor.py — Market Monitor entry point
Phase 2d: full instrument universe; BoE multi-format date fix; RBA xlsx; Stooq retired
Phase 2e: Phase marker corrected; MAS/RBA fixes
Phase 2f: MAS SGS col_map + sub-header fix; Singapore cash_rate = 6M T-bill
Phase 2g: 30Y yields — UK 20Y, Canada Long, ECB 30Y, Japan MoF CSV, Singapore col 14
Phase 2h: MoF skiprows=1; BoE ZIP fetcher; ChinaBond scraper; BOE key fix
Phase 2k: Energy commodities to yfinance futures; STALE_DAYS_COMMODITY split
Phase 3:  Gmail SMTP_SSL email delivery; --no-email flag
Phase 3b: --no-open flag and webbrowser removed (headless GitHub Actions runner)
Phase 3c: Two scheduled runs — 07:00 SGT (23:00 UTC) and 19:00 SGT (11:00 UTC)

Usage:
    python market_monitor.py              # generate and send email
    python market_monitor.py --no-email  # generate without sending email
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from emailer import send_report
from data_fetcher import (
    fetch_stress_data,
    fetch_equity_data,
    fetch_all_rates,
    fetch_all_credit_oas,
    fetch_reit_data,
    fetch_commodity_data,
    fetch_fx_data,
)
from calculator import (
    price_stats_multi,
    rate_stats,
    oas_stats,
    fx_stats as calc_fx_stats,
    commodity_stats as calc_commodity_stats,
    reit_stats as calc_reit_stats,
)
from validator import run_all, email_subject
from report_generator import build_report

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "monitor.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stats pipeline
# ---------------------------------------------------------------------------

def _compute_rate_stats(raw_rates: dict) -> dict:
    """Convert raw rate data dict {geo: {key: pd.Series}} to stats dicts."""
    from calculator import rate_stats as _rate_stats

    result = {}
    for geo, geo_data in raw_rates.items():
        geo_stats = {}
        for key, val in geo_data.items():
            if isinstance(val, bool) or val is None:
                geo_stats[key] = val
            else:
                geo_stats[key] = _rate_stats(val)
        result[geo] = geo_stats
    return result


def _compute_credit_stats(raw_credit: dict) -> dict:
    """Convert raw credit OAS series to stats dicts."""
    from calculator import oas_stats as _oas_stats

    result = {}
    for label, s in raw_credit.items():
        if hasattr(s, "dropna"):
            result[label] = _oas_stats(s)
        else:
            result[label] = None
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    logger.info("=== Market Monitor starting (Phase 3c) ===")
    start_time = datetime.now()

    logger.info("Fetching market stress data...")
    stress_raw = fetch_stress_data()

    logger.info("Fetching equity index data...")
    equity_raw = fetch_equity_data()

    logger.info("Fetching government bond / rate data (all geographies)...")
    rates_raw = fetch_all_rates()

    logger.info("Fetching credit OAS data...")
    credit_raw = fetch_all_credit_oas()

    logger.info("Fetching REIT data...")
    reit_raw = fetch_reit_data()

    logger.info("Fetching commodity data...")
    commodity_raw = fetch_commodity_data()

    logger.info("Fetching FX / digital asset data...")
    fx_raw = fetch_fx_data()

    logger.info("Computing statistics...")
    stress_stats  = price_stats_multi(stress_raw)
    equity_stats  = price_stats_multi(equity_raw)
    rate_stats_d  = _compute_rate_stats(rates_raw)
    credit_stats  = _compute_credit_stats(credit_raw)
    reit_stats_d  = calc_reit_stats(reit_raw)
    comm_stats    = calc_commodity_stats(commodity_raw)
    fx_stats_d    = calc_fx_stats(fx_raw)

    logger.info("Running validation checks...")
    flags = run_all(
        equity_data=equity_raw,
        rate_data=rates_raw,
        credit_data=credit_raw,
        reit_data=reit_raw,
        commodity_data=commodity_raw,
        fx_data=fx_raw,
    )

    total_flags = flags.get("_summary", {}).get("total", 0)
    if total_flags:
        logger.warning(f"{total_flags} data flag(s) detected — check report footer")
    else:
        logger.info("All validation checks passed")

    logger.info("Building HTML report...")
    html = build_report(
        stress_stats=stress_stats,
        equity_stats=equity_stats,
        rate_stats=rate_stats_d,
        credit_stats=credit_stats,
        reit_stats=reit_stats_d,
        commodity_stats=comm_stats,
        fx_stats=fx_stats_d,
        flags=flags,
    )

    # Phase 4b (D2): docs/index.html is the ONLY report file in the repo.
    # The timestamped companion is retired — it accumulated one file per run
    # in a repo that is now public and served by GitHub Pages, and nothing
    # read it. History lives in git, not in a directory of dated copies.
    os.makedirs("docs", exist_ok=True)
    out_file = os.path.join("docs", "index.html")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"Report written: {out_file}")

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"=== Completed in {elapsed:.1f}s | Subject: {email_subject(flags)} ===")

    return out_file, html, flags


def main():
    parser = argparse.ArgumentParser(description="Market Monitor — Phase 3c")
    parser.add_argument("--no-email", action="store_true", help="Skip email delivery")
    args = parser.parse_args()

    out_file, html, flags = run()
    print(f"\nReport saved: {out_file}")

    if not args.no_email:
        subject = email_subject(flags)
        sent = send_report(os.path.abspath(out_file), subject)
        if sent:
            print(f"📧 Email sent: {subject}")
        else:
            print("⚠️  Email delivery failed — check logs/monitor.log")

    n_flags = flags.get("_summary", {}).get("total", 0)
    if n_flags:
        print(f"⚠️  {n_flags} data flag(s) — see report footer for details")
    else:
        print("✅ All data checks passed")


if __name__ == "__main__":
    main()
