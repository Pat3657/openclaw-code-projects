#!/usr/bin/env python3
"""
company_financials.py — Pull 3-statement financials from SEC EDGAR XBRL facts API.
Free, reliable, no auth needed. User-Agent header required.
"""
import sys, os, json, urllib.request, time, datetime
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

OUT = '/workspace/signal/data/company_financials.json'

# CIK must be zero-padded to 10 digits
COMPANIES = {
    'LLY':  {'cik': '0000059478',  'name': 'Eli Lilly'},
    'ABBV': {'cik': '0001551152',  'name': 'AbbVie'},
    'REGN': {'cik': '0000872589',  'name': 'Regeneron'},
    'VRTX': {'cik': '0000875320',  'name': 'Vertex Pharmaceuticals'},
    'AMGN': {'cik': '0000006769',  'name': 'Amgen'},
    'GILD': {'cik': '0000882095',  'name': 'Gilead Sciences'},
    'BMY':  {'cik': '0000014272',  'name': 'Bristol-Myers Squibb'},
    'MRNA': {'cik': '0001682852',  'name': 'Moderna'},
    'BIIB': {'cik': '0000875045',  'name': 'Biogen'},
    'PFE':  {'cik': '0000078003',  'name': 'Pfizer'},
    'ALNY': {'cik': '0001178670',  'name': 'Alnylam Pharmaceuticals'},
    'INCY': {'cik': '0000879169',  'name': 'Incyte'},
    'SRPT': {'cik': '0000885462',  'name': 'Sarepta Therapeutics'},
    'BPMC': {'cik': '0001597988',  'name': 'Blueprint Medicines'},
    'ARVN': {'cik': '0001674930',  'name': 'Arvinas'},
}

HDRS = {'User-Agent': 'SignalDashboard research@signal.ai', 'Accept': 'application/json'}

# XBRL concept → friendly label
CONCEPTS = {
    # Income Statement
    'Revenues':                                 'revenue',
    'RevenueFromContractWithCustomerExcludingAssessedTax': 'revenue',
    'GrossProfit':                              'gross_profit',
    'ResearchAndDevelopmentExpense':            'rd_expense',
    'SellingGeneralAndAdministrativeExpense':   'sga',
    'OperatingIncomeLoss':                      'operating_income',
    'NetIncomeLoss':                            'net_income',
    # Balance Sheet
    'CashAndCashEquivalentsAtCarryingValue':    'cash',
    'Assets':                                   'total_assets',
    'Liabilities':                              'total_liabilities',
    'StockholdersEquity':                       'stockholders_equity',
    'LongTermDebt':                             'lt_debt',
    'RetainedEarningsAccumulatedDeficit':       'retained_earnings',
    # Cash Flow
    'NetCashProvidedByUsedInOperatingActivities': 'operating_cf',
    'NetCashProvidedByUsedInInvestingActivities': 'investing_cf',
    'NetCashProvidedByUsedInFinancingActivities': 'financing_cf',
    'PaymentsToAcquirePropertyPlantAndEquipment': 'capex',
}

def fetch_facts(cik):
    url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
    try:
        req = urllib.request.Request(url, headers=HDRS)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"    error: {e}")
        return None

def get_annual_series(facts, concept, unit='USD'):
    """Return last 4 annual 10-K values sorted by date ascending."""
    gaap = facts.get('facts', {}).get('us-gaap', {})
    data = gaap.get(concept, {}).get('units', {}).get(unit, [])
    if not data:
        return []
    # Filter to 10-K annual filings, pick latest per fiscal year end
    annual = {}
    for item in data:
        form = item.get('form', '')
        if form not in ('10-K', '20-F'): continue
        end = item.get('end', '')
        if not end: continue
        yr = end[:4]
        # Prefer the item with the most recent filed date
        if yr not in annual or item.get('filed','') > annual[yr].get('filed',''):
            annual[yr] = item
    if not annual:
        return []
    rows = []
    for yr in sorted(annual.keys())[-4:]:
        item = annual[yr]
        rows.append({
            'year': yr,
            'end': item.get('end',''),
            'val': item.get('val', 0),
            'val_b': round(item.get('val', 0) / 1e9, 3),
        })
    return rows

def get_best_revenue_series(facts):
    """Try all revenue concepts, return the one with the most recent annual data."""
    revenue_concepts = [
        'RevenueFromContractWithCustomerExcludingAssessedTax',
        'RevenueFromContractWithCustomerIncludingAssessedTax',
        'Revenues',
        'SalesRevenueNet',
        'SalesRevenueGoodsNet',
        'RevenuesNetOfInterestExpense',
        'NetRevenues',
        'TotalRevenues',
        'HealthCareOrganizationRevenue',
        'ProductRevenue',
        'RevenueFromProductSales',
        'RevenueNotFromContractWithCustomer',
    ]
    best_series = []
    best_year = ''
    for concept in revenue_concepts:
        series = get_annual_series(facts, concept)
        if series:
            latest_year = series[-1]['year']
            if latest_year > best_year:
                best_year = latest_year
                best_series = series
    return best_series

def pull_company(ticker, cik, name):
    facts = fetch_facts(cik)
    if not facts:
        return {'ticker': ticker, 'name': name, 'error': True}

    entity = facts.get('entityName', name)
    result = {'ticker': ticker, 'name': entity, 'cik': cik, 'fetched': datetime.datetime.utcnow().strftime('%Y-%m-%d')}

    # Pull each concept
    raw = {}
    for concept, label in CONCEPTS.items():
        series = get_annual_series(facts, concept)
        if series and label not in raw:
            raw[label] = series

    # Revenue — use best (most recently filed) concept across all alternatives
    raw['revenue'] = get_best_revenue_series(facts)

    # Gross profit
    for alt in ['GrossProfit', 'GrossProfitLoss']:
        s = get_annual_series(facts, alt)
        if s and 'gross_profit' not in raw:
            raw['gross_profit'] = s
            break

    # Build 3-statement model aligned by year
    years = sorted(set(r['year'] for v in raw.values() for r in v))[-4:]
    def get_val(label, yr):
        series = raw.get(label, [])
        for row in series:
            if row['year'] == yr:
                return row['val_b']
        return None

    income_stmt, balance_sheet, cash_flow = [], [], []
    for yr in years:
        rev     = get_val('revenue', yr)
        gp      = get_val('gross_profit', yr)
        rd      = get_val('rd_expense', yr)
        sga     = get_val('sga', yr)
        op_inc  = get_val('operating_income', yr)
        net_inc = get_val('net_income', yr)
        gm      = round(gp / rev * 100, 1) if gp and rev and rev != 0 else None
        op_m    = round(op_inc / rev * 100, 1) if op_inc and rev and rev != 0 else None
        net_m   = round(net_inc / rev * 100, 1) if net_inc and rev and rev != 0 else None
        rd_pct  = round(rd / rev * 100, 1) if rd and rev and rev != 0 else None
        income_stmt.append({
            'year': yr, 'revenue_b': rev, 'gross_profit_b': gp,
            'rd_expense_b': rd, 'sga_b': sga, 'operating_income_b': op_inc,
            'net_income_b': net_inc, 'gross_margin': gm,
            'operating_margin': op_m, 'net_margin': net_m, 'rd_pct': rd_pct,
        })
        balance_sheet.append({
            'year': yr,
            'cash_b':              get_val('cash', yr),
            'total_assets_b':      get_val('total_assets', yr),
            'total_liabilities_b': get_val('total_liabilities', yr),
            'stockholders_equity_b': get_val('stockholders_equity', yr),
            'lt_debt_b':           get_val('lt_debt', yr),
            'retained_earnings_b': get_val('retained_earnings', yr),
        })
        op_cf   = get_val('operating_cf', yr)
        capex   = get_val('capex', yr)
        fcf     = round(op_cf + capex, 3) if op_cf is not None and capex is not None else None
        cash_flow.append({
            'year': yr,
            'operating_cf_b':  op_cf,
            'investing_cf_b':  get_val('investing_cf', yr),
            'financing_cf_b':  get_val('financing_cf', yr),
            'capex_b':         capex,
            'fcf_b':           fcf,
        })

    result['years']        = years
    result['income_stmt']  = income_stmt
    result['balance_sheet']= balance_sheet
    result['cash_flow']    = cash_flow

    # Latest snapshot KPIs
    if income_stmt:
        latest = income_stmt[-1]
        result['revenue_b_latest']   = latest.get('revenue_b')
        result['net_income_b_latest']= latest.get('net_income_b')
        result['rd_b_latest']        = latest.get('rd_expense_b')
        result['net_margin_latest']  = latest.get('net_margin')
        result['rd_pct_latest']      = latest.get('rd_pct')
        result['gross_margin_latest']= latest.get('gross_margin')
    if cash_flow:
        result['fcf_b_latest'] = cash_flow[-1].get('fcf_b')
    if balance_sheet:
        result['cash_b_latest']= balance_sheet[-1].get('cash_b')
        result['debt_b_latest']= balance_sheet[-1].get('lt_debt_b')

    return result

def run():
    results = {}
    for ticker, info in COMPANIES.items():
        print(f"  {ticker} ({info['name']})...", end=' ', flush=True)
        data = pull_company(ticker, info['cik'], info['name'])
        results[ticker] = data
        if not data.get('error'):
            rev = data.get('revenue_b_latest')
            print(f"✓  rev=${rev:.2f}B  net={data.get('net_income_b_latest','?')}B" if rev else "✓ (limited data)")
        else:
            print("✗ failed")
        time.sleep(0.4)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(results, f, indent=2)
    ok = sum(1 for v in results.values() if not v.get('error'))
    print(f"✅ company_financials.json: {ok}/{len(COMPANIES)} companies")

if __name__ == '__main__':
    run()
