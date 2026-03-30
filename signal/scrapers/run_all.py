#!/usr/bin/env python3
"""
run_all.py — Master refresh script: runs all scrapers, updates meta.json
"""
import sys, os, json, datetime, traceback, time
sys.path.insert(0, '/workspace/pylib'); sys.path.insert(0, '/workspace/pylib/lib-dynload')

SCRAPERS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRAPERS_DIR, '..', 'data')
META_FILE = os.path.join(DATA_DIR, 'meta.json')

SCRAPERS = [
    ('Pipeline Summary',   'pipeline_summary'),
    ('FDA PDUFA Calendar', 'fda_pdufa'),
    ('Clinical Trials',    'clinical_trials'),
    ('PubMed Signals',     'pubmed'),
    ('SEC Filings',        'sec_edgar'),
    ('BLS Macro',          'bls_macro'),
    ('Sector Signals',     'sector_signals'),
]

def run():
    meta = {}
    errors = []
    start = datetime.datetime.utcnow()
    print(f"\n{'='*60}")
    print(f"SIGNAL Dashboard Refresh — {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    for label, module_name in SCRAPERS:
        print(f"\n[{label}]")
        t0 = time.time()
        try:
            script = os.path.join(SCRAPERS_DIR, f'{module_name}.py')
            # Execute each scraper
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_name, script)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run()
            elapsed = round(time.time() - t0, 1)
            meta[module_name] = {
                'label': label,
                'last_updated': datetime.datetime.utcnow().isoformat() + 'Z',
                'status': 'ok',
                'elapsed_s': elapsed,
            }
            print(f"  Completed in {elapsed}s")
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            err_msg = str(e)
            print(f"  ❌ ERROR: {err_msg}")
            traceback.print_exc()
            errors.append({'scraper': label, 'error': err_msg})
            meta[module_name] = {
                'label': label,
                'last_updated': datetime.datetime.utcnow().isoformat() + 'Z',
                'status': 'error',
                'error': err_msg,
                'elapsed_s': elapsed,
            }

    meta['_refresh_time'] = datetime.datetime.utcnow().isoformat() + 'Z'
    meta['_total_elapsed'] = round(time.time() - start.timestamp(), 1)
    meta['_errors'] = len(errors)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(META_FILE, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Refresh complete — {len(SCRAPERS) - len(errors)}/{len(SCRAPERS)} scrapers succeeded")
    if errors:
        print(f"Errors: {[e['scraper'] for e in errors]}")
    print(f"Total time: {meta['_total_elapsed']}s")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    run()
