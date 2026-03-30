#!/usr/bin/env python3
"""
pubmed.py — Drug-level PubMed searches for biopharma signal dashboard
Searches by drug name + target instead of generic targets
"""
import sys, os, json, urllib.request, urllib.parse, datetime, time
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

OUT = '/workspace/signal/data/pubmed.json'
BASE_SEARCH  = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
BASE_SUMMARY = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi'
BASE_FETCH   = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'

# (search_term, ticker, target, therapeutic_area, drug_display_name)
DRUG_SEARCHES = [
    # LLY
    ('tirzepatide',                  'LLY',  'GLP-1/GIP',        'Metabolic',    'Tirzepatide (Mounjaro/Zepbound)'),
    ('donanemab alzheimer',          'LLY',  'Amyloid-β (N3pG)', 'Neurology',    'Donanemab'),
    ('lebrikizumab atopic dermatitis','LLY',  'IL-13',            'Immunology',   'Lebrikizumab'),
    ('mirikizumab',                  'LLY',  'IL-23',            'Immunology',   'Mirikizumab'),
    # ABBV
    ('risankizumab',                 'ABBV', 'IL-23 p19',        'Immunology',   'Risankizumab (Skyrizi)'),
    ('upadacitinib',                 'ABBV', 'JAK1',             'Immunology',   'Upadacitinib (Rinvoq)'),
    # REGN
    ('dupilumab',                    'REGN', 'IL-4Rα',           'Immunology',   'Dupilumab (Dupixent)'),
    ('fianlimab LAG-3',              'REGN', 'LAG-3',            'Oncology',     'Fianlimab'),
    ('itepekimab IL-33',             'REGN', 'IL-33',            'Respiratory',  'Itepekimab'),
    # VRTX
    ('elexacaftor tezacaftor ivacaftor cystic fibrosis', 'VRTX', 'CFTR', 'Rare Disease', 'Trikafta/Kaftrio'),
    ('VX-548 pain',                  'VRTX', 'Nav1.8',           'Neurology',    'VX-548'),
    # AMGN
    ('evolocumab PCSK9',             'AMGN', 'PCSK9',            'Metabolic',    'Evolocumab (Repatha)'),
    ('denosumab RANKL',              'AMGN', 'RANKL',            'Metabolic',    'Denosumab (Prolia/Xgeva)'),
    ('AMG 133 obesity',              'AMGN', 'GLP-1/GIP',        'Metabolic',    'AMG 133 (Maridebart)'),
    # GILD
    ('bictegravir emtricitabine HIV','GILD', 'HIV Integrase',    'Infectious',   'Biktarvy'),
    ('lenacapavir HIV',              'GILD', 'HIV Capsid',       'Infectious',   'Lenacapavir (Sunlenca)'),
    # BMY
    ('nivolumab immunotherapy',      'BMY',  'PD-1',             'Oncology',     'Nivolumab (Opdivo)'),
    ('apixaban anticoagulant',       'BMY',  'Factor Xa',        'Metabolic',    'Apixaban (Eliquis)'),
    ('CEL-SCI immuno-oncology',      'BMY',  'Multi-target',     'Oncology',     'Milvexian'),
    # PFE
    ('tafamidis ATTR amyloid',       'PFE',  'TTR Stabilizer',   'Rare Disease', 'Tafamidis (Vyndaqel)'),
    ('nirmatrelvir COVID',           'PFE',  'SARS-CoV-2 3CL',   'Infectious',   'Paxlovid'),
    ('sasanlimab PD-1',              'PFE',  'PD-1',             'Oncology',     'Sasanlimab'),
    # MRNA
    ('mRNA-1273 vaccine',            'MRNA', 'mRNA Vaccine',     'Infectious',   'Spikevax (mRNA-1273)'),
    ('mRNA cancer vaccine',          'MRNA', 'mRNA Vaccine',     'Oncology',     'mRNA-4157/V940'),
    # BIIB
    ('lecanemab BAN2401 alzheimer',  'BIIB', 'Amyloid-β',        'Neurology',    'Lecanemab (Leqembi)'),
    ('felzartamab IgA nephropathy',  'BIIB', 'CD38',             'Rare Disease', 'Felzartamab'),
    # ALNY
    ('patisiran TTR siRNA',          'ALNY', 'TTR siRNA',        'Rare Disease', 'Patisiran (Onpattro)'),
    ('vutrisiran TTR',               'ALNY', 'TTR siRNA',        'Rare Disease', 'Vutrisiran (Amvuttra)'),
    ('zilebesiran hypertension RNA', 'ALNY', 'Angiotensinogen',  'Metabolic',    'Zilebesiran'),
    # INCY
    ('ruxolitinib myelofibrosis',    'INCY', 'JAK1/2',           'Oncology',     'Ruxolitinib (Jakafi)'),
    ('pemigatinib FGFR',             'INCY', 'FGFR',             'Oncology',     'Pemigatinib (Pemazyre)'),
    # Broad themes for context
    ('KRAS G12C inhibitor sotorasib adagrasib', None, 'KRAS G12C', 'Oncology',  'KRAS G12C Inhibitors'),
    ('CAR-T cell therapy solid tumor', None,    'CAR-T',          'Oncology',    'CAR-T Therapies'),
    ('GLP-1 obesity clinical trial',   None,    'GLP-1',          'Metabolic',   'GLP-1 Class'),
    ('antibody drug conjugate ADC',    None,    'ADC',            'Oncology',    'ADC Landscape'),
    ('bispecific antibody tcell',      None,    'Bispecific mAb', 'Oncology',    'Bispecifics'),
]

def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'SignalDashboard/1.0'})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return None

def run():
    all_papers = []
    target_counts = {}
    ta_counts = {}
    drug_counts = {}
    company_counts = {}
    errors = []

    for (search_term, ticker, target, ta, drug_display) in DRUG_SEARCHES:
        print(f'  Searching: {drug_display} ...')
        params = urllib.parse.urlencode({
            'db': 'pubmed', 'term': search_term,
            'retmax': 12,
            'retmode': 'json', 'sort': 'date',
            'datetype': 'pdat', 'reldate': 365,
        })
        data = fetch_json(f'{BASE_SEARCH}?{params}')
        if not data:
            errors.append(f'search failed: {search_term}')
            time.sleep(0.5)
            continue

        ids = data.get('esearchresult', {}).get('idlist', [])
        count = int(data.get('esearchresult', {}).get('count', 0))
        print(f'    → {len(ids)} papers (total matches: {count})')

        # Update counts
        target_counts[target] = target_counts.get(target, 0) + len(ids)
        ta_counts[ta] = ta_counts.get(ta, 0) + len(ids)
        drug_counts[drug_display] = drug_counts.get(drug_display, 0) + len(ids)
        if ticker:
            company_counts[ticker] = company_counts.get(ticker, 0) + len(ids)

        if not ids:
            time.sleep(0.4)
            continue

        ids_str = ','.join(ids[:10])
        sum_params = urllib.parse.urlencode({'db': 'pubmed', 'id': ids_str, 'retmode': 'json'})
        sum_data = fetch_json(f'{BASE_SUMMARY}?{sum_params}')
        if not sum_data:
            time.sleep(0.5)
            continue

        result = sum_data.get('result', {})
        for pmid in ids[:10]:
            art = result.get(pmid, {})
            if not art or art.get('error'):
                continue
            authors = art.get('authors', [])
            author_str = ', '.join(a.get('name', '') for a in authors[:3])
            if len(authors) > 3:
                author_str += ' et al.'

            # DOI from articleids
            doi = ''
            for aid in art.get('articleids', []):
                if aid.get('idtype') == 'doi':
                    doi = aid.get('value', '')
                    break

            all_papers.append({
                'pmid':             pmid,
                'title':            art.get('title', '')[:200],
                'authors':          author_str,
                'journal':          art.get('source', '')[:60],
                'pub_date':         art.get('pubdate', '')[:10],
                'doi':              doi,
                'target_tag':       target,
                'drug_name':        drug_display,
                'company':          ticker or 'General',
                'therapeutic_area': ta,
                'pubmed_url':       f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
                'source':           'PubMed E-utilities',
            })
        time.sleep(0.4)

    # Sort by date descending
    all_papers.sort(key=lambda p: p.get('pub_date', ''), reverse=True)

    out = {
        '_source': {
            'source':    'PubMed E-utilities NCBI',
            'url':       'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
            'retrieved': datetime.datetime.utcnow().isoformat() + 'Z',
            'method':    'Drug-name search, last 365 days, clinical trial + review articles',
            'queries':   len(DRUG_SEARCHES),
        },
        'total_papers':      len(all_papers),
        'target_counts':     dict(sorted(target_counts.items(), key=lambda x: -x[1])),
        'drug_counts':       dict(sorted(drug_counts.items(), key=lambda x: -x[1])),
        'company_counts':    dict(sorted(company_counts.items(), key=lambda x: -x[1])),
        'ta_counts':         dict(sorted(ta_counts.items(), key=lambda x: -x[1])),
        'papers':            all_papers,
        'errors':            errors,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2)
    sz = os.path.getsize(OUT)
    print(f'\n✅ pubmed.json: {sz//1024}KB | {len(all_papers)} papers | {len(target_counts)} targets')
    if errors:
        print(f'  ⚠ {len(errors)} errors: {errors[:3]}')
    return out

if __name__ == '__main__':
    run()
