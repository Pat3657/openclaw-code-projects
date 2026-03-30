#!/usr/bin/env python3
"""
sec_edgar.py — SEC EDGAR scraper for biotech/pharma 8-K filings
"""
import sys, os, json, urllib.request, urllib.parse, time
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

OUT = '/workspace/signal/data/sec_filings.json'

# Key biotech/pharma tickers with CIK numbers
TICKERS = {
    'MRNA': '0001682852', 'BNTX': '0001776985', 'REGN': '0000872589',
    'BIIB': '0000875320', 'GILD': '0000882095', 'AMGN': '0000006769',
    'BMY': '0000014272', 'PFE':  '0000078003',  'ABBV': '0001551152',
    'VRTX': '0000875320', 'ALNY': '0001178670', 'SGEN': '0001060349',
    'INCY': '0000879169', 'EXAS': '0001124940', 'RARE': '0001403708',
    'CRSP': '0001674930', 'BEAM': '0001762463', 'EDIT': '0001650153',
}

def fetch_company_filings(cik, ticker):
    """Fetch recent 8-K filings for a company via EDGAR REST API."""
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'SignalDashboard research@signal.ai',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())

        filings = data.get('filings', {}).get('recent', {})
        forms = filings.get('form', [])
        dates = filings.get('filingDate', [])
        descriptions = filings.get('primaryDocument', [])
        accessions = filings.get('accessionNumber', [])
        company_name = data.get('name', ticker)

        results = []
        for i, form in enumerate(forms):
            if form in ('8-K', '8-K/A', 'S-1', '10-K', '20-F') and i < len(dates):
                date = dates[i]
                if date < '2025-01-01':
                    continue
                acc = accessions[i].replace('-', '') if i < len(accessions) else ''
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{descriptions[i]}" if acc and i < len(descriptions) else ''
                results.append({
                    'company': company_name,
                    'ticker': ticker,
                    'form': form,
                    'filed_date': date,
                    'description': descriptions[i] if i < len(descriptions) else '',
                    'url': filing_url,
                    'is_clinical': any(kw in (descriptions[i] if i < len(descriptions) else '').lower()
                                       for kw in ['clinical', 'trial', 'fda', 'phase', 'nda', 'bla', 'pdufa']),
                })
                if len(results) >= 5:
                    break
        return results, company_name
    except Exception as e:
        print(f"  Error {ticker}: {e}")
        return [], ticker

def run():
    all_filings = []

    # Also try EDGAR full-text search for clinical readout 8-Ks
    try:
        search_url = ('https://efts.sec.gov/LATEST/search-index?'
                      'q=%22phase+3%22+%22clinical+trial%22&forms=8-K'
                      '&dateRange=custom&startdt=2025-01-01&enddt=2025-12-31')
        req = urllib.request.Request(search_url, headers={
            'User-Agent': 'SignalDashboard research@signal.ai',
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            search_data = json.loads(r.read().decode())

        hits = search_data.get('hits', {}).get('hits', [])
        print(f"  EDGAR search: {len(hits)} hits")
        for hit in hits[:25]:
            src = hit.get('_source', {})
            all_filings.append({
                'company': src.get('entity_name', 'Unknown'),
                'ticker': src.get('ticker', ''),
                'form': src.get('form_type', '8-K'),
                'filed_date': src.get('file_date', '')[:10],
                'description': src.get('file_name', '')[:80],
                'url': f"https://www.sec.gov/Archives/edgar/data/{src.get('entity_id','')}/{src.get('file_name','')}",
                'is_clinical': True,
            })
    except Exception as e:
        print(f"  EDGAR search error: {e}")

    # Fetch per-company filings
    for ticker, cik in list(TICKERS.items())[:12]:
        filings, name = fetch_company_filings(cik, ticker)
        all_filings.extend(filings)
        print(f"  {ticker} ({name}): {len(filings)} filings")
        time.sleep(0.3)

    # Sort by date desc, dedupe
    all_filings.sort(key=lambda x: x.get('filed_date',''), reverse=True)
    seen = set()
    unique = []
    for f in all_filings:
        key = f['company'] + f['filed_date'] + f['form']
        if key not in seen:
            seen.add(key)
            unique.append(f)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump({'count': len(unique), 'filings': unique[:80]}, f, indent=2)
    print(f"✅ sec_filings.json: {len(unique)} filings")

if __name__ == '__main__':
    run()
