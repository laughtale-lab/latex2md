"""Check that mdBook really rendered *every* registered LaTeX anchor.

A source-level link check cannot prove that CommonMark kept raw HTML or
heading attributes. Run this after ``mdbook build`` as an independent gate.
"""
from __future__ import annotations
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import sys


class _IDs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: Counter[str] = Counter()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == 'id' and value:
                self.ids[value] += 1


def audit(book: Path) -> tuple[int, int]:
    book = book.expanduser().resolve(strict=True)
    site = book / 'book'
    report = json.loads((book / 'conversion-report.json').read_text(encoding='utf8'))
    labels = report['labels']
    if not labels:
        raise ValueError('Conversion report contains no labels')
    ids_by_page: dict[Path, Counter[str]] = {}

    def parse_ids(relative: Path) -> Counter[str]:
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'Unsafe reported page name: {relative}')
        # mdBook converts README.md to index.html.
        if relative == Path('README.md'):
            relative = Path('index.html')
        elif relative.suffix == '.md':
            relative = relative.with_suffix('.html')
        else:
            raise ValueError(f'Expected a Markdown page in report: {relative}')
        path = (site / relative).resolve()
        if not path.is_relative_to(site.resolve()) or not path.is_file():
            raise ValueError(f'Rendered page missing or outside book: {relative}')
        if path not in ids_by_page:
            parser = _IDs()
            parser.feed(path.read_text(encoding='utf8'))
            ids_by_page[path] = parser.ids
        return ids_by_page[path]

    for label, target in sorted(labels.items()):
        occurrences = parse_ids(Path(target['page']))[label]
        if occurrences != 1:
            raise ValueError(f'Rendered label {label!r} in {target["page"]!r}: '
                             f'expected 1 HTML ID, found {occurrences}')

    # Bibliography targets are created in addition to the registered labels.
    # They are referenced with a `cite-` fragment from ordinary prose.
    from .converter import slug
    citations = report['citations']
    for citation in citations:
        label = 'cite-' + slug(citation)
        occurrences = parse_ids(Path('references.md'))[label]
        if occurrences != 1:
            raise ValueError(f'Rendered bibliography target {label!r}: '
                             f'expected 1 HTML ID, found {occurrences}')

    print(f'RENDERED HTML LABELS OK: {len(labels)} source labels, '
          f'{len(citations)} bibliography anchors, {len(ids_by_page)} checked HTML pages')
    return len(labels), len(citations)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Verify all latex2md labels in rendered mdBook HTML')
    parser.add_argument('--book', type=Path, required=True, help='book root containing book/ and conversion-report.json')
    args = parser.parse_args(argv)
    try:
        audit(args.book)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f'RENDERED HTML LABEL AUDIT FAILED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
