"""Command line interface: latex2md build --source PATH --output PATH."""
import argparse
import json
from pathlib import Path
import sys
from . import __version__, convert, ConversionError
from .parser import ParseError


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(prog='latex2md', description='Strict LaTeX -> mdBook source converter for Diabat')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    p=parser.add_subparsers(dest='command', required=True)
    build=p.add_parser('build',help='convert a manual into a clean mdBook project directory')
    build.add_argument('--source',type=Path,required=True,help='manual repository root')
    build.add_argument('--output',type=Path,required=True,help='new or empty mdBook project root')
    build.add_argument('--main',default='main.tex',help='main TeX filename in source')
    options=parser.parse_args(argv)
    try:
        report=convert(options.source,options.output,main=options.main)
    except (ConversionError,ParseError,OSError,ValueError) as exc:
        print(f'latex2md: ERROR: {exc}',file=sys.stderr)
        return 1
    print(json.dumps(report['statistics'],indent=2,sort_keys=True))
    return 0


if __name__=='__main__': raise SystemExit(main())
