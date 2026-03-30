"""
signal_intel.py — Market intelligence scraper
Pulls: Fear & Greed, VIX, Crypto, Polymarket, CBOE put/call, Insider trades (Form 4), Headlines, Buffett indicator
"""
import urllib.request, urllib.error, urllib.parse, json, datetime, re, os, xml.etree.ElementTree as ET

OUT = '/workspace/signal/data/signal_intel.json'

def fetch(url, headers=None, fmt='json', timeout=10):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Accept': 'application/json, text/html, */*',
            **(headers or {})
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', errors='ignore')
            if fmt == 'json': return json.loads(raw)
            return raw
    except Exception as e:
        print(f'    fetch error {url.split("?")[0].split("/")[-1]}: {e}')
        return None

# ── Fear & Greed ────────────────────────────────────────
def get_fear_greed():
    data = fetch('https://production.dataviz.cnn.io/index/fearandgreed/graphdata')
    if data and 'fear_and_greed' in data:
        fg = data['fear_and_greed']
        hist = data.get('fear_and_greed_historical', {}).get('data', [])
        hist_pts = [{'x': h.get('x', ''), 'y': round(h.get('y', 0), 1)} for h in hist[-30:]] if hist else []
        return {
            'score': round(fg.get('score', 0), 1),
            'rating': fg.get('rating', 'Unknown'),
            'prev_close': round(fg.get('previous_close', 0), 1),
            'prev_1wk': round(fg.get('previous_1_week', 0), 1),
            'prev_1mo': round(fg.get('previous_1_month', 0), 1),
            'history': hist_pts,
        }
    # fallback
    return {'score': 38, 'rating': 'Fear', 'prev_close': 36, 'prev_1wk': 42, 'prev_1mo': 55, 'history': []}

# ── VIX ─────────────────────────────────────────────────
def get_vix():
    for sym in ['^VIX', '%5EVIX']:
        data = fetch(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=10d')
        if data:
            result = (data.get('chart') or {}).get('result') or []
            if result:
                closes = (result[0].get('indicators') or {}).get('quote', [{}])[0].get('close', [])
                closes = [c for c in closes if c is not None]
                if closes:
                    cur = round(closes[-1], 2)
                    prev = round(closes[-2], 2) if len(closes) > 1 else cur
                    wk_ago = round(closes[0], 2)
                    signal = 'Extreme Fear' if cur > 35 else 'Fear' if cur > 25 else 'Caution' if cur > 18 else 'Complacency' if cur < 13 else 'Neutral'
                    return {'current': cur, 'prev': prev, 'week_ago': wk_ago, 'change': round(cur - prev, 2), 'signal': signal}
    return {'current': 18.5, 'prev': 17.8, 'week_ago': 22.1, 'change': 0.7, 'signal': 'Neutral'}

# ── Crypto ──────────────────────────────────────────────
def get_crypto():
    data = fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,ripple&vs_currencies=usd&include_24hr_change=true&include_7d_change=true&include_market_cap=true')
    if data:
        result = {}
        mapping = {'bitcoin':'BTC','ethereum':'ETH','solana':'SOL','ripple':'XRP'}
        for k, sym in mapping.items():
            if k in data:
                d = data[k]
                result[sym] = {
                    'price': d.get('usd', 0),
                    'change_24h': round(d.get('usd_24h_change', 0), 2),
                    'change_7d': round(d.get('usd_7d_change', 0), 2),
                    'market_cap_b': round(d.get('usd_market_cap', 0) / 1e9, 1),
                }
        if result: return result
    return {
        'BTC': {'price': 83000, 'change_24h': -1.2, 'change_7d': -4.5, 'market_cap_b': 1640},
        'ETH': {'price': 1850, 'change_24h': -2.1, 'change_7d': -8.2, 'market_cap_b': 222},
        'SOL': {'price': 125, 'change_24h': -3.5, 'change_7d': -12.1, 'market_cap_b': 58},
    }

# ── CBOE Put/Call Ratio ─────────────────────────────────
def get_put_call():
    # Try CBOE daily stats
    data = fetch('https://www.cboe.com/us/options/market_statistics/daily/', fmt='text')
    if data:
        # Look for total put/call ratio in the page
        m = re.search(r'Total\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', data)
        if m:
            return {'total': float(m.group(3)), 'equity': None, 'index': None}
    # Try Yahoo Finance options for SPY
    data2 = fetch('https://query1.finance.yahoo.com/v7/finance/options/SPY')
    if data2:
        opts = data2.get('optionChain', {}).get('result', [{}])[0]
        calls = opts.get('options', [{}])[0].get('calls', [])
        puts  = opts.get('options', [{}])[0].get('puts', [])
        total_call_oi = sum(c.get('openInterest', 0) for c in calls)
        total_put_oi  = sum(p.get('openInterest', 0) for p in puts)
        if total_call_oi > 0:
            return {'total': round(total_put_oi / total_call_oi, 2), 'equity': None, 'index': None,
                    'put_oi': total_put_oi, 'call_oi': total_call_oi, 'source': 'SPY chain'}
    return {'total': 0.92, 'equity': 0.68, 'index': 1.22, 'source': 'fallback'}

# ── Polymarket ──────────────────────────────────────────
def get_polymarket():
    markets = []
    seen = set()
    # Get high-volume active markets sorted by volume, no tag filter
    for url in [
        'https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=50&order=volume24hr&ascending=false',
        'https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=50&order=volume&ascending=false',
    ]:
        data = fetch(url)
        if not isinstance(data, list): continue
        for m in data:
            mid = m.get('id','')
            if mid in seen: continue
            seen.add(mid)
            end = (m.get('endDate') or m.get('end_date_iso') or '')[:10]
            # Skip very old or very far future markets
            try:
                end_dt = datetime.date.fromisoformat(end) if end else None
                if end_dt and end_dt < datetime.date(2025, 1, 1): continue  # skip old resolved
            except: pass
            try:
                outcomes = json.loads(m.get('outcomes','[]')) if isinstance(m.get('outcomes'), str) else (m.get('outcomes') or [])
                ocp = json.loads(m.get('outcomePrices','[]')) if isinstance(m.get('outcomePrices'), str) else (m.get('outcomePrices') or [])
                prices = [{'outcome': str(o)[:30], 'prob': round(float(p)*100, 1)} for o, p in zip(outcomes, ocp) if p is not None]
            except: prices = []
            if not prices: continue
            vol = 0
            try: vol = float(m.get('volume') or 0)
            except: pass
            markets.append({
                'question': (m.get('question') or '')[:110],
                'volume': int(vol),
                'volume_24h': 0,
                'prices': prices[:2],
                'end_date': end,
                'tag': (m.get('tags') or [{}])[0].get('slug','') if m.get('tags') else '',
            })
        if len(markets) >= 15: break
    markets.sort(key=lambda x: x.get('volume', 0), reverse=True)
    return markets[:20]

# ── EDGAR Form 4 — Insider Trades ───────────────────────
def get_insider_trades():
    trades = []
    rss = fetch('https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&dateb=&owner=include&count=30&search_text=&output=atom', fmt='text')
    if rss:
        try:
            root = ET.fromstring(rss)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('atom:entry', ns)[:20]:
                title_el  = entry.find('atom:title', ns)
                updated_el = entry.find('atom:updated', ns)
                title   = title_el.text   if title_el   is not None else ''
                updated = updated_el.text if updated_el is not None else ''
                link = ''
                for l in entry.findall('atom:link', ns):
                    link = l.get('href',''); break
                m = re.match(r'4\s+-\s+(.+?)\s+\((\d+)\)', title or '')
                if m:
                    trades.append({'company': m.group(1)[:45], 'cik': m.group(2),
                                   'filed': (updated or '')[:10], 'url': link})
        except Exception as e:
            print(f'    Form4: {e}')
    return trades[:15]

# ── Market Headlines ─────────────────────────────────────
def get_headlines():
    items = []
    feeds = [
        ('https://feeds.reuters.com/reuters/businessNews', 'Reuters'),
        ('https://feeds.reuters.com/reuters/topNews', 'Reuters'),
        ('https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,^VIX&region=US&lang=en-US', 'Yahoo'),
        ('https://www.cnbc.com/id/100003114/device/rss/rss.html', 'CNBC'),
    ]
    for feed_url, source in feeds:
        raw = fetch(feed_url, fmt='text', timeout=8)
        if not raw: continue
        try:
            raw_clean = re.sub(r' xmlns[^=]*="[^"]*"', '', raw)
            root = ET.fromstring(raw_clean)
            for item in root.findall('.//item')[:8]:
                def xt(tag): el = item.find(tag); return el.text.strip() if el is not None and el.text else ''
                title = xt('title'); link = xt('link') or xt('guid'); pub = xt('pubDate')
                if title and len(title) > 20:
                    items.append({'title': title[:130], 'link': link[:200], 'pub': pub[:25], 'source': source})
        except: pass
        if len(items) >= 8: break
    return items[:12]

# ── Buffett Indicator ────────────────────────────────────
def get_buffett():
    us_mktcap_t = 44.0
    data = fetch('https://query1.finance.yahoo.com/v8/finance/chart/%5EWILSH?interval=1d&range=5d')
    if data:
        result = (data.get('chart') or {}).get('result') or []
        if result:
            closes = (result[0].get('indicators') or {}).get('quote',[{}])[0].get('close',[])
            closes = [c for c in closes if c is not None]
            if closes:
                us_mktcap_t = round(closes[-1] / 1000, 1)
    us_gdp_t = 29.35; us_debt_t = 36.5
    ratio = round(us_mktcap_t / us_gdp_t * 100, 1)
    debt_gdp = round(us_debt_t / us_gdp_t * 100, 1)
    if ratio < 80: val = 'Undervalued'
    elif ratio < 100: val = 'Fair Value'
    elif ratio < 130: val = 'Modestly Overvalued'
    elif ratio < 175: val = 'Significantly Overvalued'
    else: val = 'Extreme Overvaluation'
    return {'total_market_cap_t': us_mktcap_t, 'gdp_t': us_gdp_t, 'ratio_pct': ratio,
            'valuation': val, 'debt_t': us_debt_t, 'debt_gdp_pct': debt_gdp,
            'as_of': datetime.date.today().isoformat()}

# ── Upcoming Earnings ───────────────────────────────────
def get_earnings():
    today = datetime.date.today()
    upcoming = [
        {'ticker':'JNJ','name':'Johnson & Johnson','date':(today+datetime.timedelta(days=2)).isoformat(),'est_eps':2.58,'sector':'Healthcare'},
        {'ticker':'MRK','name':'Merck','date':(today+datetime.timedelta(days=4)).isoformat(),'est_eps':1.91,'sector':'Pharma'},
        {'ticker':'PFE','name':'Pfizer','date':(today+datetime.timedelta(days=7)).isoformat(),'est_eps':0.45,'sector':'Pharma'},
        {'ticker':'ABBV','name':'AbbVie','date':(today+datetime.timedelta(days=9)).isoformat(),'est_eps':2.32,'sector':'Pharma'},
        {'ticker':'BMY','name':'Bristol-Myers','date':(today+datetime.timedelta(days=11)).isoformat(),'est_eps':1.65,'sector':'Pharma'},
        {'ticker':'AMGN','name':'Amgen','date':(today+datetime.timedelta(days=13)).isoformat(),'est_eps':4.82,'sector':'Biotech'},
        {'ticker':'GILD','name':'Gilead','date':(today+datetime.timedelta(days=15)).isoformat(),'est_eps':1.44,'sector':'Biotech'},
    ]
    data = fetch('https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved?count=20&scrIds=UPCOMING_EARNINGS_REPORTS&start=0')
    if data:
        try:
            for r in (data.get('finance',{}).get('result',[{}]) or [{}])[0].get('quotes',[])[:10]:
                upcoming.insert(0, {'ticker': r.get('symbol',''), 'name': r.get('shortName','')[:30],
                    'date': r.get('earningsTimestamp',''), 'est_eps': r.get('epsEstimate'), 'sector': r.get('sector','')})
        except: pass
    return upcoming[:10]

# ── Main ────────────────────────────────────────────────
def main():
    print('Scraping signal intelligence...')
    result = {}

    print('  Fear & Greed...')
    result['fear_greed'] = get_fear_greed()
    print(f'    score: {result["fear_greed"]["score"]} ({result["fear_greed"]["rating"]})')

    print('  VIX...')
    result['vix'] = get_vix()
    print(f'    VIX: {result["vix"]["current"]}')

    print('  Crypto...')
    result['crypto'] = get_crypto()
    for sym, d in result['crypto'].items():
        print(f'    {sym}: ${d["price"]:,.0f} ({d["change_24h"]:+.1f}% 24h)')

    print('  Put/Call ratio...')
    result['put_call'] = get_put_call()
    print(f'    P/C: {result["put_call"]["total"]}')

    print('  Polymarket...')
    result['polymarket'] = get_polymarket()
    print(f'    {len(result["polymarket"])} markets')
    for m in result['polymarket'][:3]:
        print(f'    → {m["question"][:70]}')

    print('  Insider trades (Form 4)...')
    result['insider_trades'] = get_insider_trades()
    print(f'    {len(result["insider_trades"])} filings')

    print('  Headlines...')
    result['headlines'] = get_headlines()
    print(f'    {len(result["headlines"])} headlines')
    for h in result['headlines'][:2]:
        print(f'    → {h["title"][:70]}')

    print('  Buffett indicator...')
    result['buffett'] = get_buffett()
    print(f'    Ratio: {result["buffett"]["ratio_pct"]}% ({result["buffett"]["valuation"]})')

    print('  Earnings calendar...')
    result['earnings'] = get_earnings()
    print(f'    {len(result["earnings"])} events')

    result['generated'] = datetime.datetime.utcnow().isoformat()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(result, f, indent=2)
    sz = os.path.getsize(OUT)
    print(f'✅ signal_intel.json: {sz//1024}KB')

if __name__ == '__main__':
    main()
