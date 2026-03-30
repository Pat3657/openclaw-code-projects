#!/usr/bin/env python3
"""
bls_macro.py — BLS public API: core + manufacturing + trade price indices
"""
import sys, os, json, urllib.request, time
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

OUT = '/workspace/signal/data/bls_macro.json'
BLS_URL = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'

SERIES = {
    # Core labor
    'LNS14000000':  'Unemployment Rate',
    'LNS11300000':  'Labor Force Participation Rate',
    'LNS13023621':  'Unemployed 27+ Weeks (Lagging)',
    'CES0000000001':'Total Nonfarm Payrolls',
    'CES0500000003':'Avg Hourly Earnings (Priv)',
    'CES0500000007':'Avg Weekly Hours (Priv)',
    # Manufacturing (coincident / leading)
    'CEU3000000001':'Manufacturing Employment',
    'CES3000000007':'Manufacturing Avg Wkly Hours',
    'IPMAN':         'Industrial Production: Mfg',
    # Prices
    'CUUR0000SA0':  'CPI All Urban Consumers',
    'CUUR0000SAF':  'CPI Food',
    'CUUR0000SAH':  'CPI Housing/Shelter',
    'CUUR0000SACE': 'CPI Energy',
    'WPUFD49104':   'PPI Final Demand',
    'WPUFD4':       'PPI Intermediate Goods',
    # Import/Export prices
    'EIUIR':        'Import Price Index (All)',
    'EIUEX':        'Export Price Index (All)',
}

def fetch_bls(series_ids):
    payload = json.dumps({
        'seriesid': series_ids,
        'startyear': '2022',
        'endyear': '2026',
    }).encode('utf-8')
    try:
        req = urllib.request.Request(BLS_URL, data=payload, headers={
            'Content-Type': 'application/json',
            'User-Agent': 'SignalDashboard/1.0',
        }, method='POST')
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  BLS API error: {e}")
        return None

def parse_series(data, series_map):
    result = {}
    if not data or data.get('status') != 'REQUEST_SUCCEEDED':
        print(f"  BLS status: {data.get('status') if data else 'no data'}")
        return result

    for s in data.get('Results', {}).get('series', []):
        sid  = s['seriesID']
        name = series_map.get(sid, sid)
        pts  = []
        for dp in sorted(s.get('data', []), key=lambda x: (x['year'], x['period'])):
            if not dp['period'].startswith('M'):
                continue
            month = int(dp['period'][1:])
            try:
                val = float(dp['value'])
            except:
                continue
            pts.append({'year': int(dp['year']), 'month': month,
                        'label': f"{dp['year']}-{month:02d}", 'value': val})
        if pts:
            latest   = pts[-1]
            prev     = pts[-2] if len(pts) >= 2 else latest
            yoy_pt   = pts[-13] if len(pts) >= 13 else pts[0]
            yoy_pct  = round((latest['value'] - yoy_pt['value']) / yoy_pt['value'] * 100, 2) if yoy_pt['value'] else 0
            result[sid] = {
                'name':         name,
                'series_id':    sid,
                'latest_value': latest['value'],
                'latest_label': latest['label'],
                'mom_change':   round(latest['value'] - prev['value'], 3),
                'mom_pct':      round((latest['value'] - prev['value']) / prev['value'] * 100, 2) if prev['value'] else 0,
                'yoy_change':   round(latest['value'] - yoy_pt['value'], 3),
                'yoy_pct':      yoy_pct,
                'history':      pts[-24:],
                'history_36':   pts[-36:],
            }
            print(f"  {name}: {latest['value']} ({latest['label']}) | YoY: {yoy_pct:+.2f}%")
    return result

def run():
    all_ids = list(SERIES.keys())
    result  = {}

    # BLS API v2 allows max 25 series per request
    for i in range(0, len(all_ids), 20):
        batch = all_ids[i:i+20]
        print(f"  Fetching batch {i//20+1} ({len(batch)} series)...")
        data = fetch_bls(batch)
        parsed = parse_series(data, SERIES)
        result.update(parsed)
        time.sleep(0.5)

    # CPI YoY for Phillips Curve (12-month % changes)
    cpi_sid = 'CUUR0000SA0'
    unemp_sid = 'LNS14000000'
    phillips_data = []
    if cpi_sid in result and unemp_sid in result:
        cpi_pts = {p['label']: p['value'] for p in result[cpi_sid].get('history_36', [])}
        cpi_pts_old = {p['label']: p['value'] for p in result[cpi_sid].get('history_36', [])}
        unemp_pts = {p['label']: p['value'] for p in result[unemp_sid].get('history_36', [])}
        cpi_hist = sorted(result[cpi_sid].get('history_36', []), key=lambda x: x['label'])
        for j, pt in enumerate(cpi_hist):
            if j < 12: continue  # need 12 months prior
            prior = cpi_hist[j-12]
            if prior['value'] == 0: continue
            yoy_cpi = round((pt['value'] - prior['value']) / prior['value'] * 100, 2)
            u = unemp_pts.get(pt['label'])
            if u is not None:
                phillips_data.append({'label': pt['label'], 'unemployment': u, 'cpi_yoy': yoy_cpi})
        print(f"  Phillips Curve: {len(phillips_data)} data points")

    result['_phillips_curve'] = phillips_data
    result['_as_of'] = __import__('datetime').datetime.utcnow().strftime('%Y-%m-%d')

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"✅ bls_macro.json: {len([k for k in result if not k.startswith('_')])} series")

if __name__ == '__main__':
    run()
