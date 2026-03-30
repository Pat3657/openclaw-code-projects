#!/usr/bin/env python3
"""
clinical_trials.py — ClinicalTrials.gov V2 API scraper
"""
import sys, os, json, urllib.request, urllib.parse, time
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

OUT = '/workspace/signal/data/clinical_trials.json'
BASE = 'https://clinicaltrials.gov/api/v2/studies'

def fetch(url, label=''):
    print(f"  Fetching {label}...")
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 SignalDashboard/1.0',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  Error: {e}")
        return None

def parse_studies(data):
    studies = []
    if not data or 'studies' not in data:
        return studies
    for s in data['studies']:
        proto  = s.get('protocolSection', {})
        ident  = proto.get('identificationModule', {})
        status = proto.get('statusModule', {})
        design = proto.get('designModule', {})
        sponsor= proto.get('sponsorCollaboratorsModule', {})
        cond   = proto.get('conditionsModule', {})
        desc   = proto.get('descriptionModule', {})
        enroll = design.get('enrollmentInfo', {})
        phases = design.get('phases', [])
        lead   = sponsor.get('leadSponsor', {})
        studies.append({
            'nct_id':     ident.get('nctId', ''),
            'title':      ident.get('briefTitle', '')[:120],
            'conditions': cond.get('conditions', [])[:3],
            'sponsor':    lead.get('name', 'Unknown'),
            'phase':      ', '.join(phases) if phases else 'N/A',
            'status':     status.get('overallStatus', ''),
            'start_date': status.get('startDateStruct', {}).get('date', ''),
            'primary_completion': status.get('primaryCompletionDateStruct', {}).get('date', ''),
            'enrollment': enroll.get('count', 0),
            'brief_summary': (desc.get('briefSummary', '') or '')[:200],
        })
    return studies

def run():
    all_studies = []

    # aggFilters syntax: phase:phase3  status:recruiting,active
    queries = [
        ('cancer',                    'phase:phase3', 'status:recruiting'),
        ('cancer',                    'phase:phase3', 'status:active'),
        ('rare disease',              'phase:phase3', 'status:recruiting'),
        ('cardiovascular',            'phase:phase3', 'status:recruiting'),
        ('alzheimer neurodegeneration','phase:phase3', 'status:recruiting'),
        ('autoimmune immunology',     'phase:phase3', 'status:recruiting'),
        ('oncology hematology',       'phase:phase3', 'status:active'),
    ]

    for cond_q, phase_f, status_f in queries:
        params = urllib.parse.urlencode({
            'query.cond': cond_q,
            'aggFilters': f'{phase_f},{status_f}',
            'pageSize': '40',
            'format': 'json',
        })
        url = f"{BASE}?{params}"
        data = fetch(url, f"{cond_q}")
        studies = parse_studies(data)
        all_studies.extend(studies)
        print(f"    → {len(studies)} studies")
        time.sleep(0.5)

    # Dedupe by nct_id
    seen, unique = set(), []
    for s in all_studies:
        if s['nct_id'] not in seen:
            seen.add(s['nct_id'])
            unique.append(s)

    unique.sort(key=lambda x: x.get('enrollment') or 0, reverse=True)

    by_status = {}
    for s in unique:
        by_status[s['status']] = by_status.get(s['status'], 0) + 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump({'count': len(unique), 'by_status': by_status, 'studies': unique[:120]}, f, indent=2)
    print(f"✅ clinical_trials.json: {len(unique)} unique studies")

if __name__ == '__main__':
    run()
