"""Independent baseline gate for a known, reviewed Manual revision.

Never use a frozen baseline to prohibit ordinary manual changes by default.
Call this gate in version-qualified CI or release review, then update the
reviewed reference counts when the source changes intentionally.
"""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    p=argparse.ArgumentParser(description='Compare a conversion report with a reviewed fixture baseline')
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        actual=json.loads(args.report.read_text(encoding='utf8'))['statistics']
        expected=json.loads(args.baseline.read_text(encoding='utf8'))
    except (OSError,ValueError,KeyError) as exc:
        print(f'BASELINE ERROR: {exc}',file=sys.stderr)
        return 1
    diffs=[f'{key}: expected {n}, received {actual.get(key,"MISSING")}'
           for key,n in sorted(expected.items()) if actual.get(key)!=n]
    if diffs:
        print('BASELINE MISMATCH:\n'+'\n'.join(diffs),file=sys.stderr)
        return 1
    print(f'BASELINE OK: {len(expected)} reviewed metrics match.')
    return 0

if __name__=='__main__': raise SystemExit(main())
