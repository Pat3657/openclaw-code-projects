#!/usr/bin/env python3
"""
build_dashboard.py v2 — reads template.html, injects data, writes index.html
"""
import sys, os, json, datetime
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

DATA_DIR  = '/workspace/signal/data'
TMPL_FILE = '/workspace/signal/template.html'
OUT_HTML  = '/workspace/signal/index.html'

def load(name):
    try:
        with open(os.path.join(DATA_DIR, name)) as f: return json.load(f)
    except Exception as e:
        print(f"  Warning: {name}: {e}"); return {}

def build():
    print("Loading data...")
    pipeline = load('pipeline_summary.json')
    pdufa    = load('pdufa.json')
    trials   = load('clinical_trials.json')
    pubmed   = load('pubmed.json')
    sec      = load('sec_filings.json')
    bls      = load('bls_macro.json')
    sectors  = load('sector_signals.json')
    fred     = load('fred_macro.json')
    fins     = load('company_financials.json')
    drugs    = load('company_drugs.json')
    comml    = load('drug_commercial.json')
    intel    = load('signal_intel.json') if os.path.exists(os.path.join(DATA_DIR, 'signal_intel.json')) else {}

    # Trim trial data to keep HTML under ~500KB
    for tk, co in drugs.items():
        slim = []
        for t in (co.get('trials') or [])[:20]:   # 20 trials per company
            slim.append({
                'nct_id':             t.get('nct_id',''),
                'title':              (t.get('title',''))[:65],
                'phase':              t.get('phase',''),
                'status':             t.get('status','') or t.get('overall_status',''),
                'overall_status':     t.get('status','') or t.get('overall_status',''),
                'conditions':         (t.get('conditions') or [])[:2],
                'drug_names':         (t.get('drug_names') or [])[:3],
                'primary_endpoint':   (t.get('primary_endpoint',''))[:180],
                'secondary_endpoints':[(ep)[:90] for ep in (t.get('secondary_endpoints') or [])[:3]],
                'arms':               [{'label':(a.get('label',''))[:30],'type':a.get('type',''),'desc':(a.get('desc',''))[:70]} for a in (t.get('arms') or [])[:2]],
                'enrollment':         t.get('enrollment'),
                'start_date':         t.get('start_date',''),
                'completion_date':    t.get('completion_date',''),
                'primary_completion': t.get('primary_completion',''),
                'brief_summary':      (t.get('brief_summary',''))[:280],
                'study_design':       t.get('study_design',''),
                'masking':            t.get('masking',''),
                'location_count':     t.get('location_count',0),
            })
        co['trials'] = slim
    now      = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    # ── BLS helpers ──────────────────────────────────────────────
    def bv(sid):
        s = bls.get(sid, {})
        return (s.get('latest_value', 0) or 0,
                s.get('latest_label', ''),
                s.get('yoy_pct', 0) or 0,
                s.get('mom_pct', 0) or 0,
                s.get('history', []))

    unemp_v,  unemp_l,  unemp_yoy,  unemp_mom,  unemp_h   = bv('LNS14000000')
    cpi_v,    cpi_l,    cpi_yoy,    _,           cpi_h     = bv('CUUR0000SA0')
    ppi_v,    ppi_l,    ppi_yoy,    _,           _         = bv('WPUFD49104')
    payroll_v,payroll_l,payroll_yoy,_,           payroll_h = bv('CES0000000001')
    lfp_v,    lfp_l,    lfp_yoy,    _,           _         = bv('LNS11300000')
    earn_v,   earn_l,   _,          earn_mom,    earn_h    = bv('CES0500000003')
    hours_v,  hours_l,  hours_yoy,  _,           _         = bv('CES0500000007')
    mfg_v,    mfg_l,    mfg_yoy,    mfg_mom,    mfg_h      = bv('CEU3000000001')
    mfg_hrs_v,_,        _,          _,           mfg_hrs_h = bv('CES3000000007')
    imp_v,    imp_l,    imp_yoy,    _,           imp_h     = bv('EIUIR')
    cpi_food_v,_,       cpi_food_yoy,_,          _         = bv('CUUR0000SAF')
    cpi_shelt_v,_,      cpi_shelt_yoy,_,         _         = bv('CUUR0000SAH')
    cpi_nrg_v, _,       cpi_nrg_yoy, _,          _         = bv('CUUR0000SACE')
    u27_v,    _,        u27_yoy,    _,           u27_h     = bv('LNS13023621')
    ppi_int_v,_,        ppi_int_yoy,_,           _         = bv('WPUFD4')

    payroll_mom_k = round(bls.get('CES0000000001', {}).get('mom_change', 0) or 0, 0)

    def hl(h): return [p['label'] for p in h]
    def hv(h): return [p['value'] for p in h]

    phillips    = bls.get('_phillips_curve', [])

    # ── Yield curve ──────────────────────────────────────────────
    curve       = fred.get('curve_snapshot', {})
    spread      = fred.get('spread_10y2y', 0) or 0
    spread_h    = fred.get('spread_history', [])
    t10_series  = fred.get('treasury_1y', {}).get('10Y', [])
    t3m_series  = fred.get('treasury_1y', {}).get('3M', [])
    sp500_series= fred.get('sp500_series', [])

    spread_label = 'Normal' if spread >= 0.5 else ('Flat' if spread >= 0 else 'INVERTED ⚠️')
    spread_color = '#22d3a5' if spread >= 0.5 else ('#f7b94f' if spread >= 0 else '#f74f4f')

    # ── Sector helpers ───────────────────────────────────────────
    sector_list = sectors.get('sectors', [])
    def find_etf(sym): return next((s for s in sector_list if s.get('symbol') == sym), {})
    spy_1m   = find_etf('SPY').get('change_1m') or 0
    ibb_ytd  = find_etf('IBB').get('change_ytd') or 0
    lead_etf = sector_list[0] if sector_list else {}
    lag_etf  = sector_list[-1] if sector_list else {}

    # ── Pipeline ─────────────────────────────────────────────────
    top_ta   = list(pipeline.get('top_indications', {}).items())[:10]
    top_mod  = list(pipeline.get('modality_counts', {}).items())[:8]
    top_tgt  = list(pipeline.get('top_targets', {}).items())[:15]
    phase_c  = pipeline.get('phase_counts', {})
    top_p3   = pipeline.get('top_phase3_assets', [])[:25]
    heatmap  = pipeline.get('heatmap', {})

    # ── All JSON data bundle for the dashboard ───────────────────
    data_bundle = {
        # Biopharma
        'pdufa':      [c for c in pdufa.get('catalysts', []) if (c.get('days_away') or -999) >= -7][:28],
        'p3assets':   top_p3,
        'phaseLabels': list(phase_c.keys()),
        'phaseData':   list(phase_c.values()),
        'taLabels':   [k for k,v in top_ta],
        'taData':     [v for k,v in top_ta],
        'modLabels':  [k for k,v in top_mod],
        'modData':    [v for k,v in top_mod],
        'tgtLabels':  [k for k,v in top_tgt],
        'tgtData':    [v for k,v in top_tgt],
        'heatmap':    heatmap,
        'hmMods':     pipeline.get('heatmap_modalities', []),
        'hmInds':     pipeline.get('heatmap_indications', []),
        'trials':     trials.get('studies', [])[:60],
        'trialsByStatus': trials.get('by_status', {}),
        'trialsCount': trials.get('count', 0),
        'papers':     pubmed.get('papers', [])[:50],
        'tgtCounts':  pubmed.get('target_counts', {}),
        'pubmedCount': pubmed.get('count', 0),
        'filings':    sec.get('filings', [])[:60],
        'secCount':   sec.get('count', 0),
        # Pipeline KPIs
        'kpi': {
            'total_programs':   pipeline.get('total_programs', 0),
            'phase3_count':     pipeline.get('phase3_count', 0),
            'disruptive_count': pipeline.get('disruptive_count', 0),
            'pipeline_rnpv_b':  pipeline.get('pipeline_rnpv_b', 0),
            'pdufa_total':      pdufa.get('count_total', 0),
            'pdufa_90d':        pdufa.get('count_90d', 0),
            'pdufa_180d':       pdufa.get('count_180d', 0),
        },
        # BLS
        'bls': {
            'unemp':     {'v': unemp_v,  'l': unemp_l,  'yoy': unemp_yoy,  'mom': unemp_mom,  'h_labels': hl(unemp_h),  'h_vals': hv(unemp_h)},
            'cpi':       {'v': cpi_v,    'l': cpi_l,    'yoy': cpi_yoy,                        'h_labels': hl(cpi_h),    'h_vals': hv(cpi_h)},
            'ppi':       {'v': ppi_v,    'l': ppi_l,    'yoy': ppi_yoy},
            'payroll':   {'v': payroll_v,'l': payroll_l,'yoy': payroll_yoy,'mom_k': payroll_mom_k,'h_labels': hl(payroll_h),'h_vals': hv(payroll_h)},
            'lfp':       {'v': lfp_v,    'l': lfp_l,    'yoy': lfp_yoy},
            'earn':      {'v': earn_v,   'l': earn_l,   'mom': earn_mom,    'h_labels': hl(earn_h),   'h_vals': hv(earn_h)},
            'hours':     {'v': hours_v,  'l': hours_l,  'yoy': hours_yoy},
            'mfg':       {'v': mfg_v,    'l': mfg_l,    'yoy': mfg_yoy,    'mom': mfg_mom,    'h_labels': hl(mfg_h),    'h_vals': hv(mfg_h)},
            'mfg_hrs':   {'v': mfg_hrs_v,'h_labels': hl(mfg_hrs_h),'h_vals': hv(mfg_hrs_h)},
            'imp':       {'v': imp_v,    'l': imp_l,    'yoy': imp_yoy,    'h_labels': hl(imp_h),    'h_vals': hv(imp_h)},
            'cpi_food':  {'v': cpi_food_v,'yoy': cpi_food_yoy},
            'cpi_shelt': {'v': cpi_shelt_v,'yoy': cpi_shelt_yoy},
            'cpi_nrg':   {'v': cpi_nrg_v,'yoy': cpi_nrg_yoy},
            'u27':       {'v': u27_v,    'yoy': u27_yoy},
            'ppi_int':   {'v': ppi_int_v,'yoy': ppi_int_yoy},
        },
        'phillips': [{'u': p['unemployment'], 'cpi': p['cpi_yoy'], 'label': p['label']} for p in phillips],
        # Yield curve
        'yield': {
            'curve':         curve,
            'spread':        spread,
            'spread_label':  spread_label,
            'spread_color':  spread_color,
            'spread_history': [{'date': p['date'], 'v': p['spread']} for p in spread_h[-60:]],
            't10_series':    [{'date': p['date'], 'v': p['value']} for p in t10_series[-60:]],
            't3m_series':    [{'date': p['date'], 'v': p['value']} for p in t3m_series[-60:]],
            'sp500_series':  [{'date': p['date'], 'v': p['value']} for p in sp500_series[-90:]],
        },
        # Sectors
        'sectors':    sector_list,
        'sectorKpi': {
            'spy_1m':    spy_1m,
            'ibb_ytd':   ibb_ytd,
            'lead_sym':  lead_etf.get('symbol', '—'),
            'lead_name': lead_etf.get('name', ''),
            'lead_1m':   lead_etf.get('change_1m') or 0,
            'lag_sym':   lag_etf.get('symbol', '—'),
            'lag_name':  lag_etf.get('name', ''),
            'lag_1m':    lag_etf.get('change_1m') or 0,
        },
        'meta': {
            'built': now,
        },
        'companyFins': fins,
        'companyDrugs': drugs,
        'drugCommercial': comml,
        'signalIntel': intel,
    }

    # Read template and inject data
    with open(TMPL_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    data_js = 'const D = ' + json.dumps(data_bundle, separators=(',', ':')) + ';'
    html = html.replace('/*__SIGNAL_DATA__*/', data_js)
    html = html.replace('__BUILD_TIME__', now)

    os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    size = os.path.getsize(OUT_HTML) / 1024
    print(f'✅ index.html built — {size:.0f} KB')

if __name__ == '__main__':
    build()
