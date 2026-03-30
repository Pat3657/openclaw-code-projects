#!/usr/bin/env python3
"""
sector_signals.py — Sector ETF rotation data via Yahoo Finance
"""
import sys, os, json, urllib.request, urllib.parse, time, datetime
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

OUT = '/workspace/signal/data/sector_signals.json'

ETFS = {
    'SPY':  'S&P 500',
    'QQQ':  'Nasdaq 100',
    'XLK':  'Technology',
    'XLV':  'Health Care',
    'XLF':  'Financials',
    'XLE':  'Energy',
    'XLI':  'Industrials',
    'XLC':  'Communication',
    'XLY':  'Consumer Discret',
    'XLP':  'Consumer Staples',
    'XLU':  'Utilities',
    'XLRE': 'Real Estate',
    'XLB':  'Materials',
    'IBB':  'Biotech (IBB)',
    'XBI':  'Biotech (XBI)',
    'IHI':  'Medical Devices',
}

def fetch_chart(symbol, range_='1y'):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
           f'?interval=1d&range={range_}')
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        chart = data.get('chart', {})
        if chart.get('error'):
            return None
        result = chart.get('result', [])
        if not result:
            return None
        return result[0]
    except Exception as e:
        print(f"  Error {symbol}: {e}")
        return None

def pct(new, old):
    if old and old != 0:
        return round((new - old) / old * 100, 2)
    return None

def run():
    results = []
    today = datetime.datetime.utcnow()
    ytd_start = datetime.datetime(today.year, 1, 1)

    for symbol, name in ETFS.items():
        chart = fetch_chart(symbol)
        if not chart:
            results.append({'symbol': symbol, 'name': name, 'error': True})
            time.sleep(0.2)
            continue

        timestamps = chart.get('timestamp', [])
        closes = chart.get('indicators', {}).get('quote', [{}])[0].get('close', [])

        # Filter None values
        valid = [(ts, c) for ts, c in zip(timestamps, closes) if c is not None]
        if len(valid) < 2:
            results.append({'symbol': symbol, 'name': name, 'error': True})
            continue

        current_price = valid[-1][1]
        current_ts = valid[-1][0]

        def price_n_days_ago(n):
            cutoff = current_ts - n * 86400
            for ts, c in reversed(valid):
                if ts <= cutoff:
                    return c
            return valid[0][1]

        def price_ytd():
            cutoff = ytd_start.timestamp()
            for ts, c in valid:
                if ts >= cutoff:
                    return c
            return valid[0][1]

        w1  = pct(current_price, price_n_days_ago(7))
        m1  = pct(current_price, price_n_days_ago(30))
        m3  = pct(current_price, price_n_days_ago(91))
        m6  = pct(current_price, price_n_days_ago(182))
        ytd = pct(current_price, price_ytd())

        results.append({
            'symbol': symbol,
            'name': name,
            'price': round(current_price, 2),
            'change_1w': w1,
            'change_1m': m1,
            'change_3m': m3,
            'change_6m': m6,
            'change_ytd': ytd,
            'momentum_score': round(sum(x or 0 for x in [w1, m1, m3]) / 3, 2),
        })
        print(f"  {symbol}: ${current_price:.2f}  1W:{w1}%  1M:{m1}%  YTD:{ytd}%")
        time.sleep(0.15)

    # Sort by 1M performance for rotation view
    valid_results = [r for r in results if not r.get('error')]
    valid_results.sort(key=lambda x: x.get('change_1m') or -999, reverse=True)

    # Assign leading/lagging
    mid = len(valid_results) // 2
    for i, r in enumerate(valid_results):
        r['rotation_rank'] = i + 1
        r['rotation_label'] = 'Leading' if i < mid else 'Lagging'

    # Simple history for SPY (last 30 closes)
    spy_chart = fetch_chart('SPY', '3mo')
    spy_history = []
    if spy_chart:
        timestamps = spy_chart.get('timestamp', [])
        closes = spy_chart.get('indicators', {}).get('quote', [{}])[0].get('close', [])
        spy_history = [
            {'ts': ts, 'date': datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d'), 'close': round(c, 2)}
            for ts, c in zip(timestamps, closes) if c is not None
        ][-30:]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump({
            'sectors': valid_results,
            'spy_history': spy_history,
            'as_of': today.strftime('%Y-%m-%d'),
        }, f, indent=2)
    print(f"✅ sector_signals.json: {len(valid_results)} ETFs")

if __name__ == '__main__':
    run()
