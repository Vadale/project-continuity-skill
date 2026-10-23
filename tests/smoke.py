#!/usr/bin/env python3
"""Synthetic exact-file observer check; does not execute an original project."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    root = work/'project'
    root.mkdir()
    (root/'input.txt').write_bytes(b'new bytes\n')
    baseline = hashlib.sha256(b'old bytes\n').hexdigest()
    manifest = work/'manifest.json'
    manifest.write_text(json.dumps({'version': 1, 'files': [
        {'path': 'input.txt', 'role': 'input', 'expected_sha256': baseline},
        {'path': 'not-delivered.txt', 'role': 'output'}]}))
    script = Path(__file__).resolve().parents[1]/'skills/project-continuity/scripts/observe_files.py'
    result = subprocess.run([sys.executable, str(script), '--root', str(root),
                             '--manifest', str(manifest)], capture_output=True, check=True)
    report = json.loads(result.stdout)
    assert [r['state'] for r in report['results']] == ['changed', 'missing']
    assert report['results'][0]['sha256'] == hashlib.sha256(b'new bytes\n').hexdigest()
    assert report['results'][1]['sha256'] is None
    assert (root/'input.txt').read_bytes() == b'new bytes\n'
    assert not (root/'not-delivered.txt').exists()
    assert not any(k in report for k in ['complete', 'verified'])
    (work/'observations.json').write_bytes(result.stdout)
    print('PASS: changed input and missing output observed; no completion or execution claim.')


if __name__ == '__main__':
    main()
