# OpenClaw Signal Dashboard

> Biopharma & Macro Intelligence Dashboard — built with OpenClaw AI

A single-file HTML dashboard combining real-time market intelligence, biopharma pipeline data, clinical trial tracking, and macroeconomic signals. No backend required — runs entirely from a pre-built `index.html`.

## Features

- **⚡ Executive Summary** — Market pulse, Fear & Greed gauge, VIX sparkline, crypto signals, rules-based trading signal engine, Polymarket odds, Buffett indicator, Debt/GDP, Put/Call ratio, insider trades, earnings calendar
- **🎯 Catalyst Calendar** — PDUFA dates with trade thesis modals
- **🧬 Pipeline Intel** — 3,000+ biopharma programs, heatmaps by phase/TA/modality
- **🔬 Clinical Trials** — Phase 3 studies from ClinicalTrials.gov
- **📚 PubMed Signals** — Research papers by target/indication
- **📋 SEC Filings** — 8-K/10-K/S-1 feed
- **🏢 Company View** — Investment-grade: 3-statement financials, full pipeline, FDA approved products, patent cliff, readouts
- **📊 BLS Indicators** — Leading/coincident/lagging macro signals, recession risk score
- **📈 Yield Curve** — 3M/10Y/30Y Treasury, spread chart, S&P 500
- **🏭 Manufacturing** — Employment, hours, import prices
- **🔄 Sector Rotation** — ETF performance matrix
- **📺 TradingView** — Live charts with RSI/MACD

## Companies Covered

LLY · ABBV · REGN · VRTX · AMGN · GILD · BMY · PFE · MRNA · BIIB · ALNY · INCY

## Structure

```
signal/
├── template.html          # Dashboard HTML/CSS/JS template
├── build_dashboard.py     # Build script (injects JSON data into template)
├── syntax_check.py        # Post-build JS syntax validator
├── scrapers/
│   ├── signal_intel.py    # Market intelligence scraper (VIX, F&G, crypto, Polymarket, EDGAR)
│   └── company_drugs.py   # ClinicalTrials.gov + FDA drugs scraper
└── data/
    ├── signal_intel.json          # Live market signals snapshot
    ├── drug_commercial.json       # Revenue, market share, patent cliff per drug
    ├── company_financials.json    # SEC EDGAR 3-statement financials
    ├── company_drugs.json         # ClinicalTrials + FDA pipeline (755KB)
    ├── fred_macro.json            # FRED macroeconomic data
    ├── bls_macro.json             # BLS indicators
    ├── clinical_trials.json       # Phase 3 trial listing
    └── sector_signals.json        # Sector ETF performance
```

## Build & Run

```bash
# Requires Python 3.11 + dependencies in /workspace/pylib

# 1. Scrape fresh market intelligence
python3.11 signal/scrapers/signal_intel.py

# 2. Build the dashboard HTML
python3.11 signal/build_dashboard.py
# Output: signal/index.html (686KB single-file dashboard)

# 3. Validate JS syntax
python3.11 signal/syntax_check.py

# 4. Deploy (example: S3 presigned URL)
python3.11 -c "from s3_utils import s3_upload; s3_upload('signal/index.html', 'signal/index.html')"
```

## Data Sources

| Source | Data |
|--------|------|
| CNN Fear & Greed | Sentiment score 0–100 |
| Yahoo Finance | VIX, crypto, sector ETFs, earnings |
| CBOE | Put/Call ratio |
| Polymarket | Prediction market probabilities |
| SEC EDGAR | Form 4 insider trades, 10-K financials |
| ClinicalTrials.gov | Phase 3 biopharma trials |
| FDA drugs@fda | Approved products per company |
| BLS / FRED | CPI, payrolls, unemployment, manufacturing |
| US Treasury | Yield curve 3M/2Y/5Y/10Y/30Y |

---
*Built with [OpenClaw](https://openclaw.ai)*
