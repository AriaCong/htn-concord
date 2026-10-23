"""Read local project assets and save aggregate findings without exporting patient rows."""
from pathlib import Path
import collections
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # project root (PhD GenAI)


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    inventory = []
    for folder in sorted(ROOT.iterdir()):
        if not folder.is_dir() or folder == HERE or folder.name.startswith('.'):
            continue
        files = [p for p in folder.rglob('*') if p.is_file()
                 and not any(part in ('.git', '.venv', '__pycache__', '.pytest_cache')
                             for part in p.parts)]
        inventory.append({'folder': folder.name, 'file_count': len(files),
                          'extensions': dict(collections.Counter(p.suffix or '(none)' for p in files))})
    cases_path = ROOT / '03_cv-llm/rulebench/pilot/out/cases.jsonl'
    calls_path = ROOT / '03_cv-llm/rulebench/pilot/out/calls.jsonl'
    cases = load_jsonl(cases_path)
    b = {c['seqn']: c for c in cases if c['set'] == 'B'}
    bcalls = [c for c in load_jsonl(calls_path) if c['set'] == 'B']
    audit = {
        'date': '2026-10-19',
        'scope': 'Aggregate audit of stored local artifacts; no model calls or label regeneration',
        'input_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (cases_path, calls_path)},
        'A_case_sources': dict(collections.Counter(c['group'] + '/' + c['source']
                                                  for c in cases if c['set'] == 'A')),
        'B_cases': len(b),
        'B_diabetes_true': sum(c['diabetes'] for c in b.values()),
        'B_on_bp_meds_true': sum(c['on_bp_meds'] for c in b.values()),
        'B_either_true': sum(c['diabetes'] or c['on_bp_meds'] for c in b.values()),
        'B_stored_calls': len(bcalls),
        'B_calls_diabetes_contradiction': sum(bool(b[c['seqn']]['diabetes'])
            and 'No diabetes.' in c['prompt'] for c in bcalls),
        'B_calls_medication_contradiction': sum(bool(b[c['seqn']]['on_bp_meds'])
            and 'Not taking blood-pressure medication.' in c['prompt'] for c in bcalls),
        'B_calls_either_contradiction': sum(
            (bool(b[c['seqn']]['diabetes']) and 'No diabetes.' in c['prompt'])
            or (bool(b[c['seqn']]['on_bp_meds'])
                and 'Not taking blood-pressure medication.' in c['prompt']) for c in bcalls),
    }
    (HERE / 'folder-inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2))
    (HERE / 'local-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
