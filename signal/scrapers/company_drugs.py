#!/usr/bin/env python3
"""
company_drugs.py — Pull per-company drug intelligence:
  - All clinical trials from ClinicalTrials.gov V2 API
  - FDA approved products from drugs@fda
  - Auto-generate patent cliff estimates
"""
import sys, os, json, urllib.request, urllib.parse, time, datetime, re
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

OUT = '/workspace/signal/data/company_drugs.json'

COMPANIES = {
    'LLY':  {'name': 'Eli Lilly',            'ct_sponsor': 'Eli Lilly',        'fda_name': 'ELI LILLY'},
    'ABBV': {'name': 'AbbVie',               'ct_sponsor': 'AbbVie',           'fda_name': 'ABBVIE'},
    'REGN': {'name': 'Regeneron',            'ct_sponsor': 'Regeneron',        'fda_name': 'REGENERON'},
    'VRTX': {'name': 'Vertex',               'ct_sponsor': 'Vertex',           'fda_name': 'VERTEX'},
    'AMGN': {'name': 'Amgen',                'ct_sponsor': 'Amgen',            'fda_name': 'AMGEN'},
    'GILD': {'name': 'Gilead',               'ct_sponsor': 'Gilead Sciences',  'fda_name': 'GILEAD'},
    'BMY':  {'name': 'Bristol-Myers Squibb', 'ct_sponsor': 'Bristol-Myers',    'fda_name': 'BRISTOL-MYERS'},
    'MRNA': {'name': 'Moderna',              'ct_sponsor': 'ModernaTX',        'fda_name': 'MODERNA'},
    'BIIB': {'name': 'Biogen',               'ct_sponsor': 'Biogen',           'fda_name': 'BIOGEN'},
    'PFE':  {'name': 'Pfizer',               'ct_sponsor': 'Pfizer',           'fda_name': 'PFIZER'},
    'ALNY': {'name': 'Alnylam',              'ct_sponsor': 'Alnylam',          'fda_name': 'ALNYLAM'},
    'INCY': {'name': 'Incyte',               'ct_sponsor': 'Incyte',           'fda_name': 'INCYTE'},
    'MRNA': {'name': 'Moderna',              'ct_sponsor': 'ModernaTX',        'fda_name': 'MODERNA'},
}

HDRS = {'User-Agent': 'SignalDashboard research@signal.ai', 'Accept': 'application/json'}

def fetch(url):
    try:
        req = urllib.request.Request(url, headers=HDRS)
        with urllib.request.urlopen(req, timeout=18) as r:
            return json.loads(r.read().decode('utf-8', errors='replace'))
    except Exception as e:
        print(f"    fetch error {url[-50:]}: {e}")
        return None

def pull_ct_trials(sponsor_q, max_results=80):
    """Pull all trials for a sponsor from ClinicalTrials.gov V2."""
    enc = urllib.parse.quote(sponsor_q)
    url = f'https://clinicaltrials.gov/api/v2/studies?query.spons={enc}&pageSize={max_results}&format=json'
    data = fetch(url)
    if not data: return []

    studies = data.get('studies', [])
    results = []
    for s in studies:
        ps = s.get('protocolSection', {})
        id_m  = ps.get('identificationModule', {})
        sts_m = ps.get('statusModule', {})
        des_m = ps.get('descriptionModule', {})
        des_i = ps.get('designModule', {})
        elig  = ps.get('eligibilityModule', {})
        cond  = ps.get('conditionsModule', {})
        arms  = ps.get('armsInterventionsModule', {})
        outc  = ps.get('outcomesModule', {})

        # Phase
        phases = des_i.get('phases', [])
        phase = phases[0] if phases else ''

        # Primary endpoint (with timeframe)
        prim_outcomes = outc.get('primaryOutcomes', [])
        primary_ep = ''
        if prim_outcomes:
            po = prim_outcomes[0]
            primary_ep = po.get('measure', '')
            if po.get('timeFrame'): primary_ep += ' [' + po['timeFrame'] + ']'

        # Secondary endpoints (up to 5)
        sec_outcomes = outc.get('secondaryOutcomes', [])
        secondary_eps = []
        for so in sec_outcomes[:5]:
            ep = so.get('measure', '')
            if so.get('timeFrame'): ep += ' [' + so['timeFrame'] + ']'
            if ep: secondary_eps.append(ep)

        # Arms / interventions (richer)
        interventions = arms.get('interventions', [])
        drug_names = [i.get('name', '') for i in interventions if i.get('type', '').upper() in ('DRUG', 'BIOLOGICAL', 'COMBINATION_PRODUCT', 'GENETIC')]
        arm_groups = arms.get('armGroups', [])
        arms_detail = [{'label': a.get('label',''), 'type': a.get('type',''), 'desc': (a.get('description','') or '')[:120]} for a in arm_groups[:4]]

        # Completion
        completion = sts_m.get('completionDateStruct', {}).get('date', '')
        primary_completion = sts_m.get('primaryCompletionDateStruct', {}).get('date', '')

        # Enrollment
        enrollment = des_i.get('enrollmentInfo', {}).get('count')

        # Design
        design_info = des_i.get('designInfo', {})
        study_design = design_info.get('allocation', '') + (' / ' + design_info.get('interventionModel', '') if design_info.get('interventionModel') else '')
        masking = design_info.get('maskingInfo', {}).get('masking', '')

        # Location count
        locs = ps.get('contactsLocationsModule', {})
        loc_count = len(locs.get('locations', []))
        sponsor = ps.get('sponsorCollaboratorsModule', {}).get('leadSponsor', {}).get('name', '')

        results.append({
            'nct_id':           id_m.get('nctId', ''),
            'title':            id_m.get('briefTitle', ''),
            'phase':            phase,
            'status':           sts_m.get('overallStatus', ''),
            'conditions':       cond.get('conditions', [])[:3],
            'drug_names':       drug_names[:3],
            'primary_endpoint': primary_ep[:200] if primary_ep else '',
            'secondary_endpoints': secondary_eps,
            'arms':             arms_detail,
            'enrollment':       enrollment,
            'start_date':       sts_m.get('startDateStruct', {}).get('date', ''),
            'completion_date':  completion,
            'primary_completion': primary_completion,
            'brief_summary':    (des_m.get('briefSummary', '') or '')[:600],
            'study_design':     study_design,
            'masking':          masking,
            'location_count':   loc_count,
            'sponsor':          sponsor,
        })
    return results

def pull_fda_drugs(fda_name):
    """Pull approved drugs from FDA drugs@fda."""
    enc = urllib.parse.quote(fda_name)
    url = f'https://api.fda.gov/drug/drugsfda.json?search=sponsor_name:{enc}&limit=20'
    data = fetch(url)
    if not data or 'results' not in data:
        # try openfda applicant
        url2 = f'https://api.fda.gov/drug/drugsfda.json?search=openfda.manufacturer_name:{enc}&limit=20'
        data = fetch(url2)
    if not data or 'results' not in data:
        return []

    drugs = []
    today = datetime.date.today()
    for app in data.get('results', []):
        app_num = app.get('application_number', '')
        is_biologic = app_num.startswith('BLA')
        submissions = app.get('submissions', [])

        # Find approval date
        approval_date = None
        for sub in submissions:
            if sub.get('submission_status', '') in ('AP', 'TA'):
                approval_date = sub.get('submission_status_date', '')
                break

        # Patent cliff estimate
        patent_expiry = None
        if approval_date:
            try:
                yr = int(approval_date[:4])
                # Biologics: 12yr data exclusivity; small mol: ~20yr from filing (~12 from approval)
                expiry_yr = yr + 12 if is_biologic else yr + 12
                patent_expiry = str(expiry_yr)
                years_left = expiry_yr - today.year
            except:
                years_left = None
        else:
            years_left = None

        # Product names
        products = app.get('products', [])
        brand_names = list({p.get('brand_name', '') for p in products if p.get('brand_name')})[:3]
        active_ingredients = list({p.get('active_ingredients', [{}])[0].get('name', '') if p.get('active_ingredients') else '' for p in products[:5]})
        active_ingredients = [x for x in active_ingredients if x][:3]

        openfda = app.get('openfda', {})
        routes = openfda.get('route', [])

        drugs.append({
            'application_number': app_num,
            'brand_names':   brand_names,
            'generic_names': active_ingredients,
            'is_biologic':   is_biologic,
            'approval_date': approval_date or '',
            'patent_expiry': patent_expiry,
            'years_to_expiry': years_left,
            'route':         routes[:2] if routes else [],
            'cliff_risk':    'High' if years_left is not None and years_left <= 3 else ('Medium' if years_left is not None and years_left <= 6 else 'Low'),
        })

    # Deduplicate by brand name
    seen = set()
    deduped = []
    for d in drugs:
        key = tuple(sorted(d['brand_names'])) or d['application_number']
        if key not in seen:
            seen.add(key)
            deduped.append(d)
    return deduped

def estimate_investment_thesis(ticker, fins, trials, fda_drugs):
    """Auto-generate a simple investment thesis from data."""
    thesis = {'ticker': ticker, 'bull': [], 'bear': [], 'catalysts': [], 'risks': []}

    if fins and not fins.get('error'):
        inc = fins.get('income_stmt', [])
        if len(inc) >= 2:
            rev_now  = inc[-1].get('revenue_b') or 0
            rev_prev = inc[-2].get('revenue_b') or 0
            if rev_now and rev_prev and rev_prev != 0:
                rev_growth = (rev_now - rev_prev) / rev_prev * 100
                if rev_growth > 15:
                    thesis['bull'].append(f"Revenue growing +{rev_growth:.0f}% YoY (${rev_now:.1f}B latest)")
                elif rev_growth < -10:
                    thesis['bear'].append(f"Revenue declining {rev_growth:.0f}% YoY — post-patent or volume loss")
            rd = inc[-1].get('rd_expense_b') or 0
            rev = inc[-1].get('revenue_b') or 1
            rd_pct = rd / rev * 100 if rev else 0
            if rd_pct > 25:
                thesis['bull'].append(f"High R&D intensity {rd_pct:.0f}% of revenue — pipeline investment")
            net_m = inc[-1].get('net_margin') or 0
            if net_m and net_m > 25:
                thesis['bull'].append(f"Strong net margin {net_m:.0f}% — pricing power")
            elif net_m and net_m < 0:
                thesis['bear'].append(f"Unprofitable (net margin {net_m:.0f}%) — cash burn risk")

        bs = fins.get('balance_sheet', [])
        if bs:
            cash = bs[-1].get('cash_b') or 0
            debt = bs[-1].get('lt_debt_b') or 0
            if cash > 5:
                thesis['bull'].append(f"Strong cash position ${cash:.1f}B — M&A/buyback capacity")
            if debt > 0 and cash > 0 and debt / (cash + 0.01) > 2:
                thesis['bear'].append(f"Elevated debt-to-cash ratio {debt/cash:.1f}x")

    # Pipeline depth
    ph3 = [t for t in trials if t.get('phase') in ('PHASE3', 'PHASE4')]
    ph2 = [t for t in trials if t.get('phase') == 'PHASE2']
    recruiting = [t for t in trials if t.get('status') == 'RECRUITING']
    if len(ph3) > 5:
        thesis['bull'].append(f"Deep late-stage pipeline: {len(ph3)} Phase 3/4 trials active")
    if len(recruiting) > 0:
        thesis['catalysts'].append(f"{len(recruiting)} trials actively recruiting — readouts expected")

    # Patent cliff
    high_risk = [d for d in fda_drugs if d.get('cliff_risk') == 'High']
    if high_risk:
        brands = [d['brand_names'][0] for d in high_risk if d.get('brand_names')][:3]
        thesis['bear'].append(f"Patent cliff risk: {', '.join(brands)} exclusivity expiring soon")
        thesis['risks'].append(f"Biosimilar / generic competition for: {', '.join(brands)}")
    med_risk = [d for d in fda_drugs if d.get('cliff_risk') == 'Medium']
    if med_risk:
        brands = [d['brand_names'][0] for d in med_risk if d.get('brand_names')][:2]
        thesis['risks'].append(f"Upcoming LOE (3-6yr): {', '.join(brands)}")

    return thesis

def run():
    results = {}
    for ticker, info in COMPANIES.items():
        if ticker in results: continue  # skip duplicates
        print(f"  {ticker} ({info['name']})...", flush=True)

        print(f"    ClinicalTrials...", end=' ', flush=True)
        trials = pull_ct_trials(info['ct_sponsor'], max_results=60)
        time.sleep(0.3)
        print(f"{len(trials)} trials")

        print(f"    FDA drugs@fda...", end=' ', flush=True)
        fda_drugs = pull_fda_drugs(info['fda_name'])
        time.sleep(0.3)
        print(f"{len(fda_drugs)} approved products")

        # Load financials
        try:
            fins_all = json.load(open('/workspace/signal/data/company_financials.json'))
            fins = fins_all.get(ticker, {})
        except:
            fins = {}

        thesis = estimate_investment_thesis(ticker, fins, trials, fda_drugs)

        # Phase summary
        phase_counts = {}
        for t in trials:
            ph = t.get('phase', 'Unknown')
            phase_counts[ph] = phase_counts.get(ph, 0) + 1

        # Status summary
        status_counts = {}
        for t in trials:
            st = t.get('status', 'Unknown')
            status_counts[st] = status_counts.get(st, 0) + 1

        # Upcoming readouts (trials completing soon)
        today_str = datetime.date.today().isoformat()
        upcoming = []
        for t in trials:
            pc = t.get('primary_completion', '') or t.get('completion_date', '')
            if pc and pc >= today_str and pc <= str(datetime.date.today().year + 2) + '-12':
                upcoming.append({'nct_id': t['nct_id'], 'title': t['title'][:60], 'date': pc, 'conditions': t['conditions'][:2]})
        upcoming.sort(key=lambda x: x['date'])

        def trim_trial(t):
            return {
                'nct_id':             t['nct_id'],
                'title':              t['title'][:70],
                'phase':              t.get('phase',''),
                'status':             t.get('status',''),
                'overall_status':     t.get('status',''),
                'conditions':         t.get('conditions',[])[:2],
                'drug_names':         t.get('drug_names',[])[:3],
                'primary_endpoint':   t.get('primary_endpoint','')[:200],
                'secondary_endpoints':[ep[:110] for ep in t.get('secondary_endpoints',[])[:4]],
                'arms':               [{'label':a['label'][:40],'type':a['type'],'desc':a['desc'][:90]} for a in t.get('arms',[])[:3]],
                'enrollment':         t.get('enrollment'),
                'start_date':         t.get('start_date',''),
                'completion_date':    t.get('completion_date',''),
                'primary_completion': t.get('primary_completion',''),
                'brief_summary':      t.get('brief_summary','')[:500],
                'study_design':       t.get('study_design',''),
                'masking':            t.get('masking',''),
                'location_count':     t.get('location_count',0),
            }

        results[ticker] = {
            'ticker':         ticker,
            'name':           info['name'],
            'trials':         [trim_trial(t) for t in trials[:40]],
            'fda_approved':   fda_drugs[:20],
            'phase_counts':   phase_counts,
            'status_counts':  status_counts,
            'trial_count':    len(trials),
            'approved_count': len(fda_drugs),
            'upcoming_readouts': upcoming[:10],
            'thesis':         thesis,
        }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"✅ company_drugs.json: {len(results)} companies")

if __name__ == '__main__':
    run()
