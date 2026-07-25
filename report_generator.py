"""
report_generator.py — HTML market report builder
Phase 2b: Sections 0-6 live (stress, equity, bonds, credit, REITs, commodities, FX)
"""

from datetime import datetime
import logging

from config import (
    REPORT_TITLE, REPORT_VERSION, REPORT_TZ_LABEL, now_report, DISCLAIMER_FULL,
    EQUITY_INDICES, STRESS_TICKERS, REIT_TICKERS,
    COMMODITY_YFINANCE, COMMODITY_FRED,
    FX_FRED, FX_YFINANCE,
    CREDIT_FRED_SERIES, CREDIT_GAPS,
    RETURN_PERIODS,
    COLOUR_BAND_PCT, COLOUR_BAND_BPS, COLOUR_BAND_EQUITY, COLOUR_BAND_YIELD,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _na(value) -> str:
    """Return 'N/A' for None values."""
    return "N/A" if value is None else value


def fmt_pct(val, band: float = None) -> str:
    """
    Format a decimal percentage with colour class. None → N/A.

    Phase 4d (D3/D5): colour is binary red/green OUTSIDE a neutral band and
    grey inside it. `band` is a decimal fraction (0.01 = 1%); it defaults to
    COLOUR_BAND_PCT (±0.1%). Equity securities — Section 1 indices and
    Section 4 REITs — pass COLOUR_BAND_EQUITY (±1%).
    The signed prefix carries direction regardless of colour.
    """
    if val is None:
        return '<span class="na">N/A</span>'
    threshold = COLOUR_BAND_PCT if band is None else band
    pct = val * 100
    if abs(val) < threshold:
        cls = "flat"
    else:
        cls = "pos" if pct > 0 else "neg"
    return f'<span class="{cls}">{pct:+.2f}%</span>'


def fmt_level(val, decimals: int = 2) -> str:
    if val is None:
        return '<span class="na">N/A</span>'
    return f"{val:,.{decimals}f}"


def fmt_bps(val, invert_color: bool = False, band: float = None) -> str:
    """
    Format a basis-point change with colour.
    Convention used throughout: positive bps = red (yield/spread ROSE), negative bps = green (fell).
    invert_color is kept for future use but not needed: both yields and OAS use same sign convention.

    Phase 4d (D3/D4): colour is binary red/green OUTSIDE a neutral band and
    grey inside it. `band` is in bps; it defaults to COLOUR_BAND_BPS (±2bps,
    which credit OAS uses). Government yields pass COLOUR_BAND_YIELD (±10bps).
    """
    if val is None:
        return '<span class="na">N/A</span>'
    threshold = COLOUR_BAND_BPS if band is None else band
    if abs(val) < threshold:
        cls = "flat"
    else:
        cls = "neg" if val > 0 else "pos"
    sign = "+" if val > 0 else ""
    return f'<span class="{cls}">{sign}{val:.0f}bps</span>'


def fmt_oas(val) -> str:
    """Format an OAS level in bps."""
    if val is None:
        return '<span class="na">N/A</span>'
    return f"{val:.0f}bps"


def fmt_rate(val) -> str:
    """Format a rate/yield level (percent)."""
    if val is None:
        return '<span class="na">N/A</span>'
    return f"{val:.2f}%"


def _asof(stats: dict) -> str:
    """
    Phase 4g: the observation date behind the row, shown to the reader.

    Independent of the G-9 session detector and deliberately so: this needs no
    venue mapping and no calendar, so it still tells the truth for any series
    the detector has not been mapped for, and it stays honest if the detector
    is ever mis-tuned. A reader can see a stale print without being told.
    """
    d = stats.get("date")
    if not d:
        return ""
    return f"<br><small style='color:#aaa'>as of {d}</small>"


def _monthly_tag(is_monthly: bool) -> str:
    return ' <span class="monthly-tag">⚠️monthly</span>' if is_monthly else ""


def _sparse_policy_tag() -> str:
    """Tag for policy rates that update on a sparse schedule (e.g. ECB DFR — 6-week cycle)."""
    return ' <span class="monthly-tag">⚠️sparse (policy rate)</span>'


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
    font-size: 13px; color: #1a1a2e; background: #f5f5f7; padding: 20px;
  }
  h1 { font-size: 20px; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }
  h2 { font-size: 14px; font-weight: 700; color: #2c3e50; margin: 20px 0 6px; text-transform: uppercase; letter-spacing: 0.5px; }
  .meta { font-size: 11px; color: #666; margin-bottom: 16px; }
  .flag-banner { background: #fff3cd; border-left: 4px solid #ffc107; padding: 8px 12px; margin-bottom: 16px; font-size: 12px; }
  .clean-banner { background: #d4edda; border-left: 4px solid #28a745; padding: 8px 12px; margin-bottom: 16px; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 6px; overflow: hidden; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  th { background: #2c3e50; color: #fff; padding: 7px 10px; text-align: right; font-size: 11px; font-weight: 600; white-space: nowrap; }
  th:first-child { text-align: left; }
  td { padding: 6px 10px; text-align: right; border-bottom: 1px solid #f0f0f0; font-size: 12px; white-space: nowrap; }
  td:first-child { text-align: left; font-weight: 500; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f8f9fa; }
  .pos { color: #16a34a; font-weight: 600; }
  .neg { color: #dc2626; font-weight: 600; }
  .flat { color: #6b7280; }
  .na { color: #9ca3af; font-style: italic; }
  .monthly-tag { color: #e17055; font-size: 10px; }
  .verify-tag { color: #e17055; font-size: 10px; }
  .geo-header td { background: #f8f9fa; font-weight: 700; color: #2c3e50; font-size: 11px; text-transform: uppercase; letter-spacing: 0.3px; }
  .section-note { font-size: 11px; color: #777; margin-bottom: 6px; font-style: italic; }
  .footer { margin-top: 24px; font-size: 11px; color: #888; border-top: 1px solid #ddd; padding-top: 12px; }
  /* uwa §1.31: a disclaimer must render visually distinct from content, so a
     reader can always tell content from caveat. Italic + rule + inset. */
  .disclaimer { margin-top: 14px; padding: 10px 12px; border-left: 3px solid #b0b0b0;
                background: #fafafa; color: #666; font-size: 11px; line-height: 1.5; }
  .data-gap { background: #fff8e1; }
  .data-gap td { color: #b45309; font-style: italic; }
  table.summary { margin-bottom: 16px; }
  table.summary td { text-align: center; padding: 10px 8px; border-bottom: none; border-right: 1px solid #f0f0f0; }
  table.summary td:last-child { border-right: none; }
  table.summary td:first-child { text-align: center; font-weight: normal; }
  .tile-label { display: block; font-size: 10px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 3px; }
  .tile-value { display: block; font-size: 15px; font-weight: 700; }
</style>
"""

# ---------------------------------------------------------------------------
# Header / Footer
# ---------------------------------------------------------------------------

def _header(flags: dict, generated_at: datetime) -> str:
    # Phase 4f: the label comes from config, and generated_at is already in
    # REPORT_TIMEZONE. Previously this hard-coded the string "SGT" onto whatever
    # naive local time the machine had — true locally, 8h wrong on the UTC runner.
    ts = generated_at.strftime(f"%Y-%m-%d %H:%M {REPORT_TZ_LABEL}")
    total_flags = flags.get("_summary", {}).get("total", 0)
    if total_flags > 0:
        banner = f'<div class="flag-banner">⚠️ {total_flags} data flag(s) — review before use</div>'
    else:
        banner = '<div class="clean-banner">✅ All data checks passed</div>'

    return f"""
    <h1>{REPORT_TITLE}</h1>
    <div class="meta">Generated: {ts} &nbsp;|&nbsp; {REPORT_VERSION} &nbsp;|&nbsp; Returns in local index currency unless noted</div>
    {banner}
    """


def _summary_strip(stress_stats: dict, equity_stats: dict,
                   rate_stats: dict, flags: dict) -> str:
    """
    Phase 4e (D6) — at-a-glance summary: VIX · S&P 500 1D · US 10Y Δbps ·
    Gold/Copper direction · data-flag count.

    Rendered at the top of the report, so the emailed HTML and the published
    page carry one summary from one source (no second email-only assembly).
    Each tile pairs its colour with a signed number or a word, never colour
    alone (user-experience §4 accessibility floor).
    """
    tiles = []

    # VIX level
    vix_level = stress_stats.get("^VIX", {}).get("level")
    vix_cls = "flat"
    if vix_level is not None:
        vix_cls = "neg" if vix_level > 30 else ("flat" if vix_level > 20 else "pos")
    tiles.append(("VIX", f"{vix_level:.1f}" if vix_level is not None else "N/A", vix_cls))

    # S&P 500 1D
    spx_1d = equity_stats.get("^GSPC", {}).get("1D")
    if spx_1d is None:
        tiles.append(("S&P 500 1D", "N/A", "na"))
    else:
        cls = "flat" if abs(spx_1d) < COLOUR_BAND_EQUITY else ("pos" if spx_1d > 0 else "neg")
        tiles.append(("S&P 500 1D", f"{spx_1d * 100:+.2f}%", cls))

    # US 10Y — 1M change in bps (the shortest change the rates pipeline carries)
    us10 = rate_stats.get("US", {}).get("10y")
    us10_bps = us10.get("1M_bps") if isinstance(us10, dict) else None
    if us10_bps is None:
        tiles.append(("US 10Y 1M", "N/A", "na"))
    else:
        cls = "flat" if abs(us10_bps) < COLOUR_BAND_YIELD else ("neg" if us10_bps > 0 else "pos")
        sign = "+" if us10_bps > 0 else ""
        tiles.append(("US 10Y 1M", f"{sign}{us10_bps:.0f}bps", cls))

    # Gold/Copper ratio direction (1D) — risk-off proxy.
    # Ratio return = (1+gold_1d)/(1+copper_1d) - 1, exact from the two 1D returns.
    g1d = stress_stats.get("GC=F", {}).get("1D")
    c1d = stress_stats.get("HG=F", {}).get("1D")
    if g1d is None or c1d is None or c1d == -1:
        tiles.append(("Gold/Copper", "N/A", "na"))
    else:
        ratio_1d = (1 + g1d) / (1 + c1d) - 1
        if abs(ratio_1d) < COLOUR_BAND_PCT:
            word, cls = "flat", "flat"
        elif ratio_1d > 0:
            word, cls = "risk-off ▲", "neg"
        else:
            word, cls = "risk-on ▼", "pos"
        tiles.append(("Gold/Copper", f"{word} {ratio_1d * 100:+.2f}%", cls))

    # Data-flag count
    total_flags = flags.get("_summary", {}).get("total", 0)
    tiles.append(("Data flags", str(total_flags), "neg" if total_flags else "pos"))

    cells = "".join(
        f'<td><span class="tile-label">{label}</span>'
        f'<span class="tile-value {cls}">{value}</span></td>'
        for label, value, cls in tiles
    )
    return f'<table class="summary"><tbody><tr>{cells}</tr></tbody></table>'


def _footer(flags: dict, generated_at: datetime) -> str:
    ts = generated_at.strftime(f"%Y-%m-%d %H:%M {REPORT_TZ_LABEL}")
    flag_items = []
    for section, items in flags.items():
        if section.startswith("_") or not isinstance(items, list):
            continue
        for item in items:
            flag_items.append(f"<li>{section.upper()}: {item}</li>")

    flag_html = ""
    if flag_items:
        flag_html = "<strong>Data flags:</strong><ul>" + "".join(flag_items) + "</ul>"

    return f"""
    <div class="footer">
      <p><strong>Sources:</strong> FRED (Federal Reserve Bank of St. Louis) · ECB Statistical Data Warehouse ·
      Bank of England yield curve ZIP (par curve) / IADB fallback · Bank of Canada Valet API ·
      RBA Statistics (xlsx) · MAS SGS Benchmark Prices ·
      Japan MoF JGB CSV (daily par yields) / FRED monthly fallback · yfinance · ICE BofA Indices via FRED</p>
      <p><strong>Methodology:</strong> Equity/REIT/commodity returns use adjusted close, trading-day lookback, local currency.
      Bond/rate changes in basis points (absolute). OAS in bps from FRED % values (widening=red).
      FX as USD per 1 unit of foreign currency (positive % = foreign currency strengthened vs USD).
      All commodities: yfinance front-month futures (Phase 2k — EIA spot retired due to T+2 lag).</p>
      <p><strong>Monthly series (⚠️monthly):</strong>
      Japan cash rate — FRED monthly (no free daily source).
      Japan 10Y — MoF CSV daily if available, else FRED monthly.
      Australia — FRED monthly fallback if RBA xlsx fetch fails.
      Sparse policy rate (⚠️sparse): ECB DFR updates on 6-week meeting cycle — not a monthly source.
      1D/1W changes N/A for monthly series.</p>
      <p><strong>30Y yields note:</strong> UK = BoE ZIP par curve 30Y (Phase 2h); falls back to IADB 20Y (IUDLNPY) if ZIP unavailable.
      Canada = BoC "Long" bond (BD.CDN.LONG.DQ.YLD; verify label on first run).
      Australia = permanent gap (RBA F2 table goes to 10Y only).
      China = ChinaBond 30Y govt yield curve (daily spot).</p>
      <p><strong>China sources (Phase 2i):</strong> Cash rate = ChinaBond 0Y proxy (daily); 2Y/10Y/30Y = ChinaBond yield curve (daily).
      FRED PBOC LPR monthly retained as cash rate fallback if ChinaBond unavailable.</p>
      {flag_html}
      <p style="margin-top:8px; color:#aaa;">Generated {ts} | Market Monitor {REPORT_VERSION}</p>
      <p class="disclaimer"><em>{DISCLAIMER_FULL}</em></p>
    </div>
    """


# ---------------------------------------------------------------------------
# Section 0 — Market Stress
# ---------------------------------------------------------------------------

def _section_stress(stress_stats: dict) -> str:
    """Stress indicators: VIX level, Gold/Silver ratio, Gold/Copper ratio."""
    rows = ""

    # VIX
    vix = stress_stats.get("^VIX", {})
    vix_level = vix.get("level")
    vix_1d = vix.get("1D")
    vix_class = "neg" if (vix_level and vix_level > 30) else ("flat" if (vix_level and vix_level > 20) else "pos")
    rows += f"""
    <tr>
      <td>VIX (CBOE Volatility Index)</td>
      <td><span class="{vix_class}">{fmt_level(vix_level, 1) if vix_level else "N/A"}</span></td>
      <td>{fmt_pct(vix_1d)}</td>
      <td>{fmt_pct(vix.get("1W"))}</td>
      <td>{fmt_pct(vix.get("1M"))}</td>
    </tr>"""

    # Gold/Silver ratio
    gold = stress_stats.get("GC=F", {})
    silver = stress_stats.get("SI=F", {})
    gs_ratio = None
    gs_1d = None
    if gold.get("level") and silver.get("level") and silver["level"] != 0:
        gs_ratio = gold["level"] / silver["level"]
    rows += f"""
    <tr>
      <td>Gold/Silver Ratio (GC=F / SI=F) <span class="section-note">risk-off → ratio rises</span></td>
      <td>{fmt_level(gs_ratio, 1) if gs_ratio else "N/A"}</td>
      <td><span class="na">—</span></td>
      <td><span class="na">—</span></td>
      <td><span class="na">—</span></td>
    </tr>"""

    # Gold/Copper ratio
    copper = stress_stats.get("HG=F", {})
    gc_ratio = None
    if gold.get("level") and copper.get("level") and copper["level"] != 0:
        gc_ratio = gold["level"] / copper["level"]
    rows += f"""
    <tr>
      <td>Gold/Copper Ratio (GC=F / HG=F) <span class="section-note">risk-off → ratio rises</span></td>
      <td>{fmt_level(gc_ratio, 1) if gc_ratio else "N/A"}</td>
      <td><span class="na">—</span></td>
      <td><span class="na">—</span></td>
      <td><span class="na">—</span></td>
    </tr>"""

    return f"""
    <h2>Section 0 — Market Stress</h2>
    <table>
      <colgroup>
        <col style="width:45%"><col style="width:15%">
        <col style="width:13%"><col style="width:13%"><col style="width:14%">
      </colgroup>
      <thead><tr><th>Indicator</th><th>Level</th><th>1D</th><th>1W</th><th>1M</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <p class="section-note">Futures-based: GC=F (Gold), SI=F (Silver), HG=F (Copper). Spot sources attempted and failed.</p>
    """


# ---------------------------------------------------------------------------
# Section 1 — Equity Indices
# ---------------------------------------------------------------------------

def _section_equity(equity_stats: dict) -> str:
    """Two tables: short-term (1D–3M) and long-term (6M–10Y)."""
    short_rows = ""
    long_rows = ""

    # Group by region
    current_region = None

    for ticker, meta in EQUITY_INDICES.items():
        stats = equity_stats.get(ticker, {})
        region = meta.get("region", "")
        name = meta.get("name", ticker)

        if region != current_region:
            region_cell = f'<tr class="geo-header"><td colspan="7">{region}</td></tr>'
            short_rows += region_cell
            long_rows += region_cell
            current_region = region

        level = fmt_level(stats.get("level"))
        date_str = stats.get("date", "")
        ticker_display = f"{name} <small style='color:#999'>{ticker}</small>{_asof(stats)}"

        eq = COLOUR_BAND_EQUITY   # D5: equity colour threshold ±1%

        short_rows += f"""
        <tr>
          <td>{ticker_display}</td>
          <td>{level}</td>
          <td>{fmt_pct(stats.get("1D"), band=eq)}</td>
          <td>{fmt_pct(stats.get("1W"), band=eq)}</td>
          <td>{fmt_pct(stats.get("1M"), band=eq)}</td>
          <td>{fmt_pct(stats.get("3M"), band=eq)}</td>
        </tr>"""

        long_rows += f"""
        <tr>
          <td>{ticker_display}</td>
          <td>{level}</td>
          <td>{fmt_pct(stats.get("6M"), band=eq)}</td>
          <td>{fmt_pct(stats.get("1Y"), band=eq)}</td>
          <td>{fmt_pct(stats.get("3Y"), band=eq)}</td>
          <td>{fmt_pct(stats.get("5Y"), band=eq)}</td>
          <td>{fmt_pct(stats.get("10Y"), band=eq)}</td>
        </tr>"""

    short_html = f"""
    <table>
      <colgroup>
        <col style="width:32%"><col style="width:12%">
        <col style="width:14%"><col style="width:14%"><col style="width:14%"><col style="width:14%">
      </colgroup>
      <thead><tr><th>Index</th><th>Level</th><th>1D</th><th>1W</th><th>1M</th><th>3M</th></tr></thead>
      <tbody>{short_rows}</tbody>
    </table>"""

    long_html = f"""
    <table>
      <colgroup>
        <col style="width:32%"><col style="width:12%">
        <col style="width:14%"><col style="width:14%"><col style="width:14%"><col style="width:14%"><col style="width:0%">
      </colgroup>
      <thead><tr><th>Index</th><th>Level</th><th>6M</th><th>1Y</th><th>3Y</th><th>5Y</th><th>10Y</th></tr></thead>
      <tbody>{long_rows}</tbody>
    </table>"""

    return f"""
    <h2>Section 1 — Equity Indices</h2>
    <p class="section-note">Returns in local index currency. See Section 6 FX table for USD currency impact. ETF proxies: ACWI, URTH, EEM.
    Colour: moves within &plusmn;1% render neutral grey (D5, review after one week); the signed number always carries direction.</p>
    {short_html}
    {long_html}
    """


# ---------------------------------------------------------------------------
# Section 2 — Government Bonds
# ---------------------------------------------------------------------------

def _rate_row(name: str, rate_dict: dict, key: str, is_monthly: bool = False,
              force_sparse_policy: bool = False) -> str:
    """Single rate row: name | level | 1M Δbps | 3M Δbps | 1Y Δbps.
    force_sparse_policy: use ⚠️sparse (policy rate) tag instead of ⚠️monthly.
    """
    stats = rate_dict.get(key)
    if stats is None or not isinstance(stats, dict):
        return f'<tr><td>{name}</td><td colspan="4"><span class="na">N/A</span></td></tr>'

    level = fmt_rate(stats.get("level"))
    yb = COLOUR_BAND_YIELD   # D4: government-yield colour threshold ±10bps
    m1 = fmt_bps(stats.get("1M_bps"), band=yb)
    m3 = fmt_bps(stats.get("3M_bps"), band=yb)
    y1 = fmt_bps(stats.get("1Y_bps"), band=yb)
    if force_sparse_policy:
        monthly_note = _sparse_policy_tag()
    else:
        monthly_note = _monthly_tag(is_monthly or stats.get("is_monthly", False))

    return f"<tr><td>{name}{monthly_note}</td><td>{level}</td><td>{m1}</td><td>{m3}</td><td>{y1}</td></tr>"


def _geo_bond_section(geo: str, rates: dict, is_monthly: bool = False,
                      cash_rate_sparse_policy: bool = False,
                      label_2y: str = "2Y Yield",
                      label_30y: str = None) -> str:
    """Build bond rows for one geography.
    cash_rate_sparse_policy: use ⚠️sparse (policy rate) tag on the cash rate row.
    label_2y: override the 2Y row label (e.g. '5Y* Yield' when 2Y is unavailable).
    label_30y: if provided, render a 30Y row with this label. None = omit row.
    """
    m = _monthly_tag(is_monthly)
    rows = f'<tr class="geo-header"><td colspan="5">{geo}{m}</td></tr>'
    rows += _rate_row("Cash Rate", rates, "cash_rate", is_monthly,
                      force_sparse_policy=cash_rate_sparse_policy)
    rows += _rate_row(label_2y, rates, "2y", is_monthly)
    rows += _rate_row("10Y Yield", rates, "10y", is_monthly)
    if label_30y:
        rows += _rate_row(label_30y, rates, "30y", is_monthly)
    return rows


def _section_rates(rate_stats: dict) -> str:
    """Full Section 2: all geographies."""
    rows = ""

    rows += _geo_bond_section("United States (FRED, daily)", rate_stats.get("US", {}),
                              label_30y="30Y Yield")

    # US curve spreads — within US block
    us = rate_stats.get("US", {})
    r10 = us.get("10y", {}).get("level")
    r2  = us.get("2y", {}).get("level")
    r3m = us.get("3m", {}).get("level") if "3m" in us else us.get("cash_rate", {}).get("level")
    spread_2_10 = (r10 - r2) * 100 if (r10 is not None and r2 is not None) else None
    spread_3m_10 = (r10 - r3m) * 100 if (r10 is not None and r3m is not None) else None
    inv_2_10 = "neg" if (spread_2_10 is not None and spread_2_10 < 0) else "flat"
    inv_3m10 = "neg" if (spread_3m_10 is not None and spread_3m_10 < 0) else "flat"

    rows += f"""
    <tr>
      <td style="padding-left:20px; font-style:italic; color:#666">↳ 2-10 Spread</td>
      <td><span class="{inv_2_10}">{f"{spread_2_10:+.0f}bps" if spread_2_10 is not None else "N/A"}</span></td>
      <td colspan="3"></td>
    </tr>
    <tr>
      <td style="padding-left:20px; font-style:italic; color:#666">↳ 3M-10Y Spread (NY Fed recession)</td>
      <td><span class="{inv_3m10}">{f"{spread_3m_10:+.0f}bps" if spread_3m_10 is not None else "N/A"}</span></td>
      <td colspan="3"></td>
    </tr>"""

    rows += _geo_bond_section("Canada (BoC Valet API)", rate_stats.get("Canada", {}),
                              label_30y='30Y Yield ("Long" bond)')
    rows += _geo_bond_section("Eurozone (ECB API, daily — AAA euro govt composite)",
                              rate_stats.get("Eurozone", {}),
                              cash_rate_sparse_policy=True,
                              label_30y="30Y Yield")
    rows += _geo_bond_section("United Kingdom (BoE yield curve ZIP — 2Y/30Y par; IADB fallback)",
                              rate_stats.get("UK", {}),
                              label_2y="2Y Yield",
                              label_30y="30Y Yield")
    rows += _geo_bond_section("Japan (MoF CSV daily — 2Y/10Y/30Y; FRED monthly cash rate)",
                              rate_stats.get("Japan", {}),
                              label_30y="30Y Yield")
    rows += _geo_bond_section("Singapore (MAS SGS daily — 6M T-bill + 2Y/5Y/10Y/30Y)",
                              rate_stats.get("Singapore", {}),
                              label_30y="30Y Yield")
    rows += _geo_bond_section("Australia (RBA xlsx daily — f01d/f02d; FRED monthly fallback)",
                              rate_stats.get("Australia", {}))
    rows += _geo_bond_section("China (ChinaBond daily — 0Y proxy/2Y/10Y/30Y; FRED cash rate fallback)",
                              rate_stats.get("China", {}), is_monthly=False,
                              label_30y="30Y Yield")

    return f"""
    <h2>Section 2 — Government Bond Yields, Cash Rates & Spreads</h2>
    <p class="section-note">All changes in basis points (bps). Positive bps = rate rose (red). Monthly series: 1D/1W changes N/A.
    Colour: changes within &plusmn;10bps render neutral grey (D4).</p>
    <table>
      <colgroup>
        <col style="width:40%"><col style="width:15%">
        <col style="width:15%"><col style="width:15%"><col style="width:15%">
      </colgroup>
      <thead><tr><th>Market / Instrument</th><th>Rate</th><th>1M Δbps</th><th>3M Δbps</th><th>1Y Δbps</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """


# ---------------------------------------------------------------------------
# Section 3 — Credit OAS
# ---------------------------------------------------------------------------

def _section_credit(credit_stats: dict) -> str:
    rows = ""

    credit_order = [
        ("US_IG",  "US IG OAS (ICE BofA US Corporate)",   False),
        ("US_HY",  "US HY OAS (ICE BofA US High Yield)",  False),
        ("EUR_HY", "EUR HY OAS (ICE BofA Euro HY)",       False),
    ]

    for key, label, _ in credit_order:
        stats = credit_stats.get(key)
        if stats is None or not isinstance(stats, dict):
            rows += f'<tr class="data-gap"><td>{label}</td><td colspan="4">N/A — series not fetched</td></tr>'
            continue
        rows += f"""
        <tr>
          <td>{label}</td>
          <td>{fmt_oas(stats.get("level"))}</td>
          <td>{fmt_bps(stats.get("1M_bps"))}</td>
          <td>{fmt_bps(stats.get("3M_bps"))}</td>
          <td>{fmt_bps(stats.get("1Y_bps"))}</td>
        </tr>"""

    # Data gap notes
    rows += '<tr class="data-gap"><td>EUR IG OAS</td><td colspan="4">Data gap — no ICE BofA EUR IG OAS series available on FRED.</td></tr>'
    rows += '<tr class="data-gap"><td>GBP IG OAS</td><td colspan="4">Data gap — no FRED series confirmed. ETF price proxy (SLXX.L) excluded: price ≠ OAS.</td></tr>'

    return f"""
    <h2>Section 3 — Credit (OAS)</h2>
    <p class="section-note">OAS in basis points. Widening = red (credit risk rising). Tightening = green. FRED ICE BofA series.
    Colour: changes within &plusmn;2bps render neutral grey (D3 default band).</p>
    <table>
      <colgroup>
        <col style="width:40%"><col style="width:15%">
        <col style="width:15%"><col style="width:15%"><col style="width:15%">
      </colgroup>
      <thead><tr><th>Index</th><th>OAS (bps)</th><th>1M Δbps</th><th>3M Δbps</th><th>1Y Δbps</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """


# ---------------------------------------------------------------------------
# Section 4 — REITs
# ---------------------------------------------------------------------------

def _section_reits(reit_stats: dict) -> str:
    short_rows = ""
    long_rows = ""
    eq = COLOUR_BAND_EQUITY   # D5 (LLY 2026-07-24 s5): REITs take the equity band
    for ticker, stats in reit_stats.items():
        name = stats.get("name", ticker)
        level = fmt_level(stats.get("level"))
        label = f"{name} <small style='color:#999'>{ticker}</small>{_asof(stats)}"

        short_rows += f"""
        <tr>
          <td>{label}</td>
          <td>{level}</td>
          <td>{fmt_pct(stats.get("1D"), band=eq)}</td>
          <td>{fmt_pct(stats.get("1W"), band=eq)}</td>
          <td>{fmt_pct(stats.get("1M"), band=eq)}</td>
          <td>{fmt_pct(stats.get("3M"), band=eq)}</td>
        </tr>"""

        long_rows += f"""
        <tr>
          <td>{label}</td>
          <td>{level}</td>
          <td>{fmt_pct(stats.get("6M"), band=eq)}</td>
          <td>{fmt_pct(stats.get("1Y"), band=eq)}</td>
          <td>{fmt_pct(stats.get("3Y"), band=eq)}</td>
          <td>{fmt_pct(stats.get("5Y"), band=eq)}</td>
        </tr>"""

    return f"""
    <h2>Section 4 — REITs</h2>
    <table>
      <colgroup><col style="width:40%"><col style="width:12%"><col style="width:12%"><col style="width:12%"><col style="width:12%"><col style="width:12%"></colgroup>
      <thead><tr><th>ETF</th><th>Price</th><th>1D</th><th>1W</th><th>1M</th><th>3M</th></tr></thead>
      <tbody>{short_rows}</tbody>
    </table>
    <table>
      <colgroup><col style="width:40%"><col style="width:12%"><col style="width:12%"><col style="width:12%"><col style="width:12%"><col style="width:12%"><col style="width:12%"></colgroup>
      <thead><tr><th>ETF</th><th>Price</th><th>6M</th><th>1Y</th><th>3Y</th><th>5Y</th></tr></thead>
      <tbody>{long_rows}</tbody>
    </table>
    """


# ---------------------------------------------------------------------------
# Section 5 — Commodities
# ---------------------------------------------------------------------------

def _section_commodities(commodity_stats: dict) -> str:
    # Order: energy first, then metals, then broad/Baltic
    ordered_keys = [
        "CL=F", "BZ=F", "NG=F",      # yfinance energy futures (Phase 2k)
        "GC=F", "SI=F", "HG=F",       # yfinance metals futures
        "DJP", "BDRY",                 # yfinance broad
    ]
    rows = ""
    for key in ordered_keys:
        stats = commodity_stats.get(key)
        if stats is None:
            continue
        name = stats.get("name", key)
        unit = stats.get("unit", "")
        note = stats.get("note", "")
        level = stats.get("level")
        level_str = fmt_level(level)
        note_html = f' <span class="section-note">{note}</span>' if note else ""

        rows += f"""
        <tr>
          <td>{name} <small style='color:#999'>{key}</small>{note_html}{_asof(stats)}</td>
          <td>{level_str} <small style='color:#aaa'>{unit}</small></td>
          <td>{fmt_pct(stats.get("1D"))}</td>
          <td>{fmt_pct(stats.get("1W"))}</td>
          <td>{fmt_pct(stats.get("1M"))}</td>
          <td>{fmt_pct(stats.get("3M"))}</td>
          <td>{fmt_pct(stats.get("1Y"))}</td>
        </tr>"""

    return f"""
    <h2>Section 5 — Commodities</h2>
    <p class="section-note">All commodities: yfinance front-month futures. Returns in USD.</p>
    <table>
      <colgroup>
        <col style="width:35%"><col style="width:15%">
        <col style="width:10%"><col style="width:10%"><col style="width:10%"><col style="width:10%"><col style="width:10%">
      </colgroup>
      <thead><tr><th>Commodity</th><th>Level</th><th>1D</th><th>1W</th><th>1M</th><th>3M</th><th>1Y</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """


# ---------------------------------------------------------------------------
# Section 6 — FX & Digital Assets
# ---------------------------------------------------------------------------

def _section_fx(fx_stats: dict) -> str:
    # Ordered display: EUR, GBP, AUD, JPY, CAD, SGD, CNY, BTC
    ordered_ccys = ["CAD", "EUR", "GBP", "JPY", "SGD", "AUD", "CNY", "BTC"]
    rows = ""
    for ccy in ordered_ccys:
        stats = fx_stats.get(ccy)
        if stats is None:
            continue
        pair = stats.get("pair", ccy)
        level = stats.get("level")
        is_crypto = stats.get("is_crypto", False)

        if is_crypto:
            level_str = f"${level:,.0f}" if level else "N/A"
            label = f"{pair} <span class='section-note'>24/7; midnight UTC ref</span>"
        else:
            level_str = fmt_level(level, 4) if level else "N/A"
            label = pair

        rows += f"""
        <tr>
          <td>{label}</td>
          <td>{level_str}</td>
          <td>{fmt_pct(stats.get("1D"))}</td>
          <td>{fmt_pct(stats.get("1W"))}</td>
          <td>{fmt_pct(stats.get("1M"))}</td>
          <td>{fmt_pct(stats.get("3M"))}</td>
          <td>{fmt_pct(stats.get("1Y"))}</td>
        </tr>"""

    return f"""
    <h2>Section 6 — Currencies & Digital Assets vs USD</h2>
    <p class="section-note">All as "USD per 1 unit of foreign currency". Positive % = that currency strengthened vs USD.
    ⚠️ Direction verified on first run. JPY/CAD/SGD/CNY are inverted FRED series.</p>
    <table>
      <colgroup>
        <col style="width:30%"><col style="width:14%">
        <col style="width:10%"><col style="width:10%"><col style="width:10%"><col style="width:10%"><col style="width:10%">
      </colgroup>
      <thead><tr><th>Currency / Asset</th><th>Rate (USD/unit)</th><th>1D</th><th>1W</th><th>1M</th><th>3M</th><th>1Y</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """


# ---------------------------------------------------------------------------
# Master report builder
# ---------------------------------------------------------------------------

def build_report(
    stress_stats: dict,
    equity_stats: dict,
    rate_stats: dict,
    credit_stats: dict,
    reit_stats: dict,
    commodity_stats: dict,
    fx_stats: dict,
    flags: dict,
) -> str:
    """Assemble the full HTML report."""
    now = now_report()   # Phase 4f: report timezone, never the runner's clock

    html_parts = [
        "<!DOCTYPE html><html><head>",
        "<meta charset='UTF-8'>",
        f"<title>{REPORT_TITLE} — {now.strftime('%Y-%m-%d')}</title>",
        _CSS,
        "</head><body>",
        _header(flags, now),
        _summary_strip(stress_stats, equity_stats, rate_stats, flags),
        _section_stress(stress_stats),
        _section_equity(equity_stats),
        _section_rates(rate_stats),
        _section_credit(credit_stats),
        _section_reits(reit_stats),
        _section_commodities(commodity_stats),
        _section_fx(fx_stats),
        _footer(flags, now),
        "</body></html>",
    ]

    return "\n".join(html_parts)
