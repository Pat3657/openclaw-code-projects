#!/usr/bin/env python3
"""
fred_macro.py — Yield curve, treasury rates, leading indicators via Yahoo Finance
(No API key needed — uses Yahoo Finance chart API)
"""
import sys, os, json, urllib.request, urllib.parse, time, datetime
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

OUT = '/workspace/signal/data/fred_macro.json'

TREASURIES = {
    '^IRX':  '3M',
    '^FVX':  '5Y',
    '^TNX':  '10Y',
    '^TYX':  '30Y',
    '^GSPC': 'SP500',   # for growth proxy
}
# Approximate 2Y from interpolation; Yahoo doesn't have clean 2Y symbol

def fetch_chart(symbol, rng='2y'):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range={rng}'
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        result = data.get('chart', {}).get('result', [])
        if not result: return None
        return result[0]
    except Exception as e:
        print(f"  Error {symbol}: {e}")
        return None

def extract_series(chart, days_back=730):
    """Return list of {date, value} sorted ascending."""
    if not chart: return []
    ts   = chart.get('timestamp', [])
    closes = chart.get('indicators', {}).get('quote', [{}])[0].get('close', [])
    out = []
    cutoff = time.time() - days_back * 86400
    for t, c in zip(ts, closes):
        if c is not None and t >= cutoff:
            out.append({'date': datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d'), 'value': round(c, 4)})
    return out

def latest(series):
    if not series: return None
    return series[-1]['value']

def run():
    rates = {}
    for sym, label in TREASURIES.items():
        print(f"  Fetching {sym} ({label})...")
        chart = fetch_chart(sym)
        series = extract_series(chart)
        rates[label] = {
            'symbol': sym,
            'series': series[-24:],   # last 24 data points for chart
            'latest': latest(series),
            'series_1y': series[-252:],
        }
        print(f"    → {label}: {latest(series)}")
        time.sleep(0.2)

    # Yield curve snapshot (most recent values)
    curve = {
        '3M':  rates.get('3M', {}).get('latest'),
        '5Y':  rates.get('5Y', {}).get('latest'),
        '10Y': rates.get('10Y', {}).get('latest'),
        '30Y': rates.get('30Y', {}).get('latest'),
    }

    # Approximate 2Y (interpolate between 3M and 5Y - rough but directionally right)
    if curve['3M'] and curve['5Y']:
        curve['2Y'] = round(curve['3M'] + (curve['5Y'] - curve['3M']) * 0.35, 3)

    # Key spread: 10Y - 2Y (inversion = recession signal)
    spread_10y2y = None
    if curve.get('10Y') and curve.get('2Y'):
        spread_10y2y = round(curve['10Y'] - curve['2Y'], 3)
        print(f"  10Y-2Y spread: {spread_10y2y:+.3f} ({'INVERTED ⚠️' if spread_10y2y < 0 else 'Normal ✓'})")

    # Historical 10Y-2Y spread (use 10Y series vs 3M as proxy)
    spread_history = []
    t10 = {p['date']: p['value'] for p in rates.get('10Y', {}).get('series_1y', [])}
    t3m = {p['date']: p['value'] for p in rates.get('3M',  {}).get('series_1y', [])}
    for date in sorted(set(t10.keys()) & set(t3m.keys())):
        spread_history.append({'date': date, 'spread': round(t10[date] - t3m[date], 3)})
    spread_history = spread_history[-60:]  # last 60 data points

    # Leading / Coincident / Lagging framework
    # Use available data to score each category
    t10_latest = curve.get('10Y', 0) or 0
    t3m_latest = curve.get('3M', 0) or 0
    spread_v   = spread_10y2y or 0

    leading_signals = {
        'yield_curve_spread': {
            'value': spread_v,
            'label': '10Y-2Y Spread',
            'signal': 'bearish' if spread_v < 0 else ('neutral' if spread_v < 0.5 else 'bullish'),
            'note': 'Inversion (< 0) historically precedes recessions by 6-18 months',
        },
        'yield_curve_label': 'Normal' if spread_v >= 0.5 else ('Flat' if spread_v >= 0 else 'Inverted'),
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump({
            'curve_snapshot': curve,
            'spread_10y2y': spread_10y2y,
            'spread_history': spread_history,
            'treasury_series': {k: v['series'] for k, v in rates.items() if k != 'SP500'},
            'treasury_1y': {k: v['series_1y'] for k, v in rates.items() if k != 'SP500'},
            'sp500_series': rates.get('SP500', {}).get('series_1y', []),
            'leading_signals': leading_signals,
            'as_of': datetime.datetime.utcnow().strftime('%Y-%m-%d'),
        }, f, indent=2)

    print(f"✅ fred_macro.json: yield curve {curve}, spread={spread_10y2y}")

if __name__ == '__main__':
    run()
