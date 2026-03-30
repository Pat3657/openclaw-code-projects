#!/usr/bin/env python3
"""
pipeline_summary.py — Richer pipeline data from ClinicalTrials.gov v2 API
Proper target/indication/modality classification per sponsor
"""
import sys, os, json, urllib.request, urllib.parse, datetime, time, re
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

OUT = '/workspace/signal/data/pipeline_summary.json'

COMPANIES = {
    'LLY':  ['Eli Lilly', 'Lilly'],
    'ABBV': ['AbbVie'],
    'REGN': ['Regeneron'],
    'VRTX': ['Vertex Pharmaceuticals', 'Vertex'],
    'AMGN': ['Amgen'],
    'GILD': ['Gilead'],
    'BMY':  ['Bristol-Myers Squibb', 'Bristol Myers'],
    'PFE':  ['Pfizer'],
    'MRNA': ['Moderna'],
    'BIIB': ['Biogen'],
    'ALNY': ['Alnylam'],
    'INCY': ['Incyte'],
}

# ── TA Classification ─────────────────────────────────────────
TA_RULES = [
    ('Oncology',     ['cancer','tumor','carcinoma','leukemia','lymphoma','melanoma','sarcoma',
                      'myeloma','glioma','glioblastoma','mesothelioma','adenocarcinoma',
                      'hepatocellular','renal cell','bladder cancer','lung cancer','breast cancer',
                      'colorectal','ovarian','prostate','pancreatic','cervical','squamous cell']),
    ('Immunology',   ['arthritis','psoriasis','lupus','ibd','crohn','colitis','atopic','eczema',
                      'autoimmune','spondylitis','uveitis','myositis','vasculitis','alopecia',
                      'dermatomyositis','sjogren','prurigo','hidradenitis','vitiligo']),
    ('Metabolic',    ['diabetes','obesity','nash','nafld','lipid','cholesterol','cardiovascular',
                      'hypertension','heart failure','metabolic','dyslipidemia','atherosclerosis',
                      'coronary','myocardial','stroke','venous thromboembolism']),
    ('Neurology',    ['alzheimer','parkinson','als','amyotrophic','multiple sclerosis','epilepsy',
                      'migraine','depression','schizophrenia','bipolar','dementia','huntington',
                      'spinal muscular','neuropathy','neurodegeneration','cognitive']),
    ('Rare Disease', ['rare','orphan','genetic','enzyme deficiency','transthyretin','amyloid',
                      'hemophilia','sickle cell','thalassemia','fabry','gaucher','pompe',
                      'cystic fibrosis','duchenne','spinal muscular atrophy','hereditary']),
    ('Infectious',   ['hiv','covid','sars-cov','rsv','influenza','hepatitis','infection',
                      'bacterial','viral','fungal','pneumonia','sepsis','tuberculosis']),
    ('Respiratory',  ['copd','pulmonary','asthma','respiratory','lung disease','idiopathic',
                      'fibrosis','bronchiectasis']),
    ('Hematology',   ['anemia','myelodysplastic','myelofibrosis','polycythemia','thrombocytopenia',
                      'aplastic','blood disorder','coagulation']),
]

def classify_ta(conditions, title=''):
    text = ' '.join(conditions + [title]).lower()
    for ta, keywords in TA_RULES:
        if any(k in text for k in keywords):
            return ta
    return 'Other'

# ── Modality Classification ───────────────────────────────────
def classify_modality(drug_name, intervention_type, ticker='', summary=''):
    n = (drug_name or '').lower()
    s = (summary or '').lower()
    t = (intervention_type or '').upper()
    if any(n.endswith(x) for x in ['mab','umab','zumab','ximab','limab','numab','imab']):
        if 'bispecific' in s or 'bispecific' in n:  return 'Bispecific Antibody'
        if 'adc' in s or 'antibody-drug conjugate' in s: return 'ADC'
        return 'Monoclonal Antibody'
    if any(n.endswith(x) for x in ['cept','nercept']):
        return 'Fusion Protein'
    if any(n.endswith(x) for x in ['nib','tinib','linib','sitinib','ritinib']):
        return 'Small Molecule'
    if any(n.endswith(x) for x in ['ib','stat','vir','navir','ciclovir']):
        return 'Small Molecule'
    if ticker == 'ALNY' or 'sirna' in s or 'rnai' in s or 'patisiran' in n or 'vutrisiran' in n:
        return 'siRNA / RNAi'
    if ticker == 'MRNA' or 'mrna' in s or 'mrna-' in n:
        return 'mRNA'
    if 'gene therapy' in s or 'aav' in s or 'car-t' in s or 'car t' in s:
        return 'Gene Therapy'
    if 'adc' in s or 'antibody-drug conjugate' in s:
        return 'ADC'
    if t == 'BIOLOGICAL':
        return 'Biologic'
    if t == 'DRUG':
        return 'Small Molecule'
    return 'Other'

# ── Target extraction ─────────────────────────────────────────
KNOWN_TARGETS = {
    'tirzepatide': 'GLP-1/GIP','semaglutide': 'GLP-1','liraglutide': 'GLP-1',
    'donanemab': 'Amyloid-β (N3pG)','lecanemab': 'Amyloid-β','gantenerumab': 'Amyloid-β',
    'dupilumab': 'IL-4Rα','lebrikizumab': 'IL-13','tralokinumab': 'IL-13',
    'risankizumab': 'IL-23 (p19)','guselkumab': 'IL-23','mirikizumab': 'IL-23',
    'upadacitinib': 'JAK1','filgotinib': 'JAK1','tofacitinib': 'JAK1/2','ruxolitinib': 'JAK1/2',
    'evolocumab': 'PCSK9','alirocumab': 'PCSK9',
    'denosumab': 'RANKL',
    'nivolumab': 'PD-1','pembrolizumab': 'PD-1','cemiplimab': 'PD-1',
    'atezolizumab': 'PD-L1','durvalumab': 'PD-L1','avelumab': 'PD-L1',
    'ipilimumab': 'CTLA-4','tremelimumab': 'CTLA-4',
    'trastuzumab': 'HER2','pertuzumab': 'HER2',
    'bictegravir': 'HIV Integrase','cabotegravir': 'HIV Integrase',
    'tafamidis': 'TTR Stabilizer',
    'patisiran': 'TTR siRNA','vutrisiran': 'TTR siRNA','inclisiran': 'PCSK9 siRNA',
    'elexacaftor': 'CFTR','tezacaftor': 'CFTR','ivacaftor': 'CFTR',
    'abatacept': 'CTLA-4-Ig',
    'belimumab': 'BLyS','anifrolumab': 'IFNAR1',
    'ixekizumab': 'IL-17A','secukinumab': 'IL-17A',
    'tocilizumab': 'IL-6R','sarilumab': 'IL-6R',
    'mepolizumab': 'IL-5','benralizumab': 'IL-5',
    'itepekimab': 'IL-33','tezepelumab': 'TSLP',
    'apixaban': 'Factor Xa','rivaroxaban': 'Factor Xa',
    'fianlimab': 'LAG-3',
    'repatha': 'PCSK9',
}

def extract_target(drug_name, conditions, interventions_browse):
    n = (drug_name or '').lower().strip()
    # Direct lookup
    for drug, tgt in KNOWN_TARGETS.items():
        if drug in n:
            return tgt
    # From browse mesh
    if interventions_browse:
        mesh = [m.get('meshTerm','') for m in interventions_browse[:3] if m.get('id')]
        if mesh:
            return mesh[0]
    # Infer from condition
    ta = classify_ta(conditions)
    if ta == 'Oncology':
        return 'Tumor Antigen'
    if ta == 'Immunology':
        return 'Immune Checkpoint'
    return 'Undisclosed'

def fetch(url, retries=2):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'SignalDashboard/1.0', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                return None

def pull_trials(sponsor_name, ticker, phases=None):
    phases = phases or ['PHASE3', 'PHASE2']
    results = []
    seen_ids = set()

    for phase in phases:
        page_token = None
        page_count = 0
        while page_count < 4:  # max 4 pages per phase per sponsor
            url = (
                'https://clinicaltrials.gov/api/v2/studies'
                '?query.spons=' + urllib.parse.quote(sponsor_name) +
                '&filter.advanced=' + phase +
                '&filter.overallStatus=RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED,NOT_YET_RECRUITING' +
                '&pageSize=50'
            )
            if page_token:
                url += '&pageToken=' + urllib.parse.quote(page_token)
            data = fetch(url)
            if not data:
                break
            studies = data.get('studies', [])
            if not studies:
                break
            for study in studies:
                ps = study.get('protocolSection', {})
                id_m    = ps.get('identificationModule', {})
                nct_id  = id_m.get('nctId', '')
                if not nct_id or nct_id in seen_ids:
                    continue
                seen_ids.add(nct_id)

                stat_m  = ps.get('statusModule', {})
                desc_m  = ps.get('descriptionModule', {})
                cond_m  = ps.get('conditionsModule', {})
                des_m   = ps.get('designModule', {})
                arm_m   = ps.get('armsInterventionsModule', {})
                out_m   = ps.get('outcomesModule', {})
                sp_m    = ps.get('sponsorCollaboratorsModule', {})
                browse  = study.get('derivedSection', {})

                title      = id_m.get('briefTitle', '')
                status     = stat_m.get('overallStatus', '')
                conditions = cond_m.get('conditions', [])

                # Interventions
                interventions = arm_m.get('interventions', [])
                drug_ivs  = [iv for iv in interventions if iv.get('type') in ('DRUG', 'BIOLOGICAL')]
                drug_name = drug_ivs[0].get('name', '') if drug_ivs else ''
                iv_type   = drug_ivs[0].get('type', '') if drug_ivs else ''

                # Browse mesh
                int_browse  = browse.get('interventionBrowseModule', {}).get('meshes', [])
                brief_sum   = desc_m.get('briefSummary', '')[:400]

                # Classify
                ta       = classify_ta(conditions, title)
                modality = classify_modality(drug_name, iv_type, ticker, brief_sum)
                target   = extract_target(drug_name, conditions, int_browse)

                # Outcomes
                primary_outcomes   = out_m.get('primaryOutcomes', [])
                secondary_outcomes = out_m.get('secondaryOutcomes', [])
                primary_ep   = primary_outcomes[0].get('measure', '') if primary_outcomes else ''
                secondary_ep = [o.get('measure', '') for o in secondary_outcomes[:3]]

                results.append({
                    'nct_id':             nct_id,
                    'title':              title[:120],
                    'ticker':             ticker,
                    'sponsor':            sp_m.get('leadSponsor', {}).get('name', sponsor_name)[:50],
                    'sponsor_class':      sp_m.get('leadSponsor', {}).get('class', ''),
                    'phase':              phase,
                    'status':             status,
                    'drug_name':          drug_name[:60],
                    'target':             target,
                    'indication':         ta,
                    'therapeutic_area':   ta,
                    'conditions':         conditions[:5],
                    'modality':           modality,
                    'primary_endpoint':   primary_ep[:150],
                    'secondary_endpoints': secondary_ep,
                    'enrollment':         des_m.get('enrollmentInfo', {}).get('count'),
                    'start_date':         stat_m.get('startDateStruct', {}).get('date', ''),
                    'completion_date':    stat_m.get('primaryCompletionDateStruct', {}).get('date', ''),
                    'brief_summary':      brief_sum,
                    'source_url':         f'https://clinicaltrials.gov/study/{nct_id}',
                })
            next_token = data.get('nextPageToken')
            if not next_token:
                break
            page_token = next_token
            page_count += 1
            time.sleep(0.3)
        time.sleep(0.4)
    return results

def run():
    print('Scraping pipeline data from ClinicalTrials.gov...')
    all_trials = []
    co_counts = {}

    for ticker, names in COMPANIES.items():
        co_trials = []
        for name in names:
            trials = pull_trials(name, ticker)
            # Deduplicate by NCT ID
            existing_ids = {t['nct_id'] for t in co_trials}
            new_t = [t for t in trials if t['nct_id'] not in existing_ids]
            co_trials.extend(new_t)
            print(f'  {ticker} ({name}): {len(new_t)} trials')
            time.sleep(0.3)
        all_trials.extend(co_trials)
        co_counts[ticker] = len(co_trials)

    print(f'\nTotal trials: {len(all_trials)}')

    # ── Phase distribution ────────────────────────────────
    phase_counts = {}
    for t in all_trials:
        phase_counts[t['phase']] = phase_counts.get(t['phase'], 0) + 1

    # ── TA distribution ───────────────────────────────────
    ta_counts = {}
    for t in all_trials:
        ta_counts[t['indication']] = ta_counts.get(t['indication'], 0) + 1

    # ── Modality distribution ─────────────────────────────
    mod_counts = {}
    for t in all_trials:
        mod_counts[t['modality']] = mod_counts.get(t['modality'], 0) + 1

    # ── Target frequency ──────────────────────────────────
    tgt_counts = {}
    for t in all_trials:
        tgt = t['target']
        if tgt and tgt not in ('Undisclosed', 'Tumor Antigen', 'Immune Checkpoint'):
            tgt_counts[tgt] = tgt_counts.get(tgt, 0) + 1

    # ── Top Phase 3 assets ────────────────────────────────
    p3 = [t for t in all_trials if t['phase'] == 'PHASE3' and t['status'] in
          ('RECRUITING','ACTIVE_NOT_RECRUITING','COMPLETED','NOT_YET_RECRUITING')]
    p3.sort(key=lambda x: (x['ticker'], x['drug_name']))

    # Estimated PoS and rNPV (simplified heuristic)
    TA_POS = {'Oncology':0.35,'Immunology':0.55,'Metabolic':0.60,'Neurology':0.30,
              'Rare Disease':0.65,'Infectious':0.50,'Respiratory':0.55,'Hematology':0.50,'Other':0.40}
    TA_NPV = {'Oncology':1200,'Immunology':2500,'Metabolic':3000,'Neurology':800,
              'Rare Disease':4000,'Infectious':600,'Respiratory':1800,'Hematology':900,'Other':400}

    for a in p3:
        pos = TA_POS.get(a['indication'], 0.40)
        npv = TA_NPV.get(a['indication'], 500)
        a['pos'] = round(pos * 100)
        a['rnpv_mid_m'] = round(pos * npv)
        a['disruptive'] = a['modality'] in ('siRNA / RNAi','Gene Therapy','mRNA','Bispecific Antibody','ADC')

    # ── Heatmap ───────────────────────────────────────────
    tas   = sorted(ta_counts.keys(), key=lambda x: -ta_counts[x])[:8]
    mods  = sorted(mod_counts.keys(), key=lambda x: -mod_counts[x])[:8]
    heatmap = {mod: {} for mod in mods}
    for t in all_trials:
        m = t['modality']
        ta = t['indication']
        if m in heatmap and ta in tas:
            heatmap[m][ta] = heatmap[m].get(ta, 0) + 1

    out = {
        '_source': {
            'source': 'ClinicalTrials.gov API v2',
            'url': 'https://clinicaltrials.gov/api/v2/studies',
            'retrieved': datetime.datetime.utcnow().isoformat() + 'Z',
            'method': 'Phase 2/3 filter per sponsor, 12 companies',
            'companies': list(COMPANIES.keys()),
        },
        'total_programs':    len(all_trials),
        'phase3_count':      sum(1 for t in all_trials if t['phase'] == 'PHASE3'),
        'phase2_count':      sum(1 for t in all_trials if t['phase'] == 'PHASE2'),
        'disruptive_count':  sum(1 for t in all_trials if t.get('disruptive')),
        'pipeline_rnpv_b':   round(sum(a.get('rnpv_mid_m',0) for a in p3) / 1000, 1),
        'phase_counts':      phase_counts,
        'ta_counts':         dict(sorted(ta_counts.items(), key=lambda x: -x[1])),
        'modality_counts':   dict(sorted(mod_counts.items(), key=lambda x: -x[1])),
        'target_counts':     dict(sorted(tgt_counts.items(), key=lambda x: -x[1])[:30]),
        'company_counts':    co_counts,
        'top_phase3_assets': p3[:50],
        'all_trials':        all_trials,
        'heatmap':           heatmap,
        'heatmap_mods':      mods,
        'heatmap_inds':      tas,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2)
    sz = os.path.getsize(OUT)
    print(f'\n✅ pipeline_summary.json: {sz//1024}KB | {len(all_trials)} trials | {len(p3)} Phase 3 assets')
    return out

if __name__ == '__main__':
    run()
