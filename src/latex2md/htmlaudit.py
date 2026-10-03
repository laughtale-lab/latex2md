"""Strict audit of HTML produced by the pinned mdBook renderer.

Markdown is an intermediate format.  This module treats the rendered mdBook
HTML as the publication contract: every converter-registered target must exist
exactly once on the expected page, and every local HTML link/resource must
resolve to a real file and, when present, a real fragment ID.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import sys
from urllib.parse import unquote, urlsplit


class HtmlAuditError(ValueError):
    pass


@dataclass
class HtmlDocument:
    ids: Counter[str] = field(default_factory=Counter)
    links: list[tuple[str, str]] = field(default_factory=list)
    elements: dict[str, list[tuple[str, str]]] = field(default_factory=dict)


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.document = HtmlDocument()

    def handle_starttag(self, tag: str, attrs) -> None:
        fields = dict(attrs)
        anchor = fields.get('id')
        if anchor:
            self.document.ids[anchor] += 1
            self.document.elements.setdefault(anchor, []).append((tag, fields.get('class', '')))
        href = fields.get('href')
        src = fields.get('src')
        if href is not None:
            self.document.links.append(('href', href))
        if src is not None:
            self.document.links.append(('src', src))


def parse_html(path: Path) -> HtmlDocument:
    parser = Collector()
    parser.feed(path.read_text(encoding='utf-8', errors='strict'))
    parser.close()
    return parser.document


def markdown_to_html(page: str) -> str:
    path = Path(page)
    if path.name == 'README.md':
        return str(path.with_name('index.html')).replace('\\', '/')
    if path.suffix != '.md':
        raise HtmlAuditError(f'target report contains non-Markdown page: {page}')
    return str(path.with_suffix('.html')).replace('\\', '/')


def _normalise_site_path(current: str, raw_path: str, site_prefix: str) -> str:
    decoded = unquote(raw_path)
    if '\x00' in decoded or '\\' in decoded:
        raise HtmlAuditError(f'unsafe local URL path: {raw_path!r}')
    rooted = False
    if site_prefix and decoded.startswith(site_prefix):
        decoded = decoded[len(site_prefix):]
        rooted = True
    elif decoded.startswith('/'):
        # Root-relative paths outside the configured Pages site are not local
        # to this generated book, so they must not be silently reinterpreted.
        raise HtmlAuditError(f'root-relative URL is outside site prefix {site_prefix!r}: {raw_path}')
    if decoded == '':
        return 'index.html' if rooted else current
    directory_link = decoded.endswith('/') or decoded in {'.', './'}
    base = '' if rooted else posixpath.dirname(current)
    candidate = posixpath.normpath(posixpath.join(base, decoded))
    if candidate == '..' or candidate.startswith('../'):
        raise HtmlAuditError(f'local URL escapes rendered site: {current} -> {raw_path}')
    if directory_link:
        candidate = posixpath.join(candidate if candidate != '.' else '', 'index.html')
    return candidate


def audit_html(report_path: Path, html_root: Path, *, site_prefix: str = '/diabat-manual/',
               allow_missing: set[str] | None = None) -> dict[str, int]:
    allow_missing = set(allow_missing or ())
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        targets = report['targets']
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        raise HtmlAuditError(f'cannot read conversion target report: {exc}') from exc
    if not isinstance(targets, dict) or not targets:
        raise HtmlAuditError('conversion report has no targets')

    html_root = html_root.resolve()
    if not html_root.is_dir():
        raise HtmlAuditError(f'HTML root does not exist: {html_root}')
    pages: dict[str, HtmlDocument] = {}
    for path in sorted(html_root.rglob('*.html')):
        relative = path.relative_to(html_root).as_posix()
        pages[relative] = parse_html(path)
    if not pages:
        raise HtmlAuditError(f'no rendered HTML pages under {html_root}')

    # The converter guarantees globally unique IDs for its own targets.  A
    # target is valid only if mdBook preserved it on exactly the expected page.
    global_expected = Counter()
    for document in pages.values():
        for anchor, count in document.ids.items():
            if anchor in targets:
                global_expected[anchor] += count

    kind_counts = Counter()
    for anchor, target in targets.items():
        if target.get('name') != anchor:
            raise HtmlAuditError(f'target key/name mismatch: {anchor}')
        if not target.get('render'):
            raise HtmlAuditError(f'target lacks render contract: {anchor}')
        expected_page = markdown_to_html(target['page'])
        if expected_page not in pages:
            raise HtmlAuditError(f'target {anchor} expects missing rendered page {expected_page}')
        count = pages[expected_page].ids[anchor]
        if count != 1:
            raise HtmlAuditError(
                f'target {anchor} must occur exactly once in {expected_page}; found {count}'
            )
        if global_expected[anchor] != 1:
            raise HtmlAuditError(
                f'target {anchor} must be globally unique across rendered HTML; '
                f'found {global_expected[anchor]}'
            )
        element = pages[expected_page].elements[anchor][0]
        tag, classes = element
        if target['render'] == 'heading':
            expected_tags = {
                'chapter': 'h1', 'section': 'h2', 'subsection': 'h3',
                'subsubsection': 'h4', 'paragraph': 'h5',
            }
            expected_tag = expected_tags.get(target['kind'])
            if expected_tag is None or tag != expected_tag:
                raise HtmlAuditError(
                    f'heading target {anchor} must render as {expected_tag}; got <{tag}>'
                )
        elif target['render'] == 'raw-html':
            if tag != 'div':
                raise HtmlAuditError(f'raw target {anchor} must render as <div>; got <{tag}>')
            if target['kind'] in {'script', 'example'} and 'listing-caption' not in classes.split():
                raise HtmlAuditError(f'{target["kind"]} target {anchor} lost listing-caption semantics')
        else:
            raise HtmlAuditError(f'unknown rendered target contract for {anchor}: {target["render"]}')
        kind_counts[target['kind']] += 1

    checked_links = 0
    checked_resources = 0
    for current, document in pages.items():
        for attr, raw in document.links:
            if not raw or raw.startswith('//'):
                continue
            parsed = urlsplit(raw)
            if parsed.scheme:
                # Network and data URLs cannot be validated offline here.
                continue
            local = _normalise_site_path(current, parsed.path, site_prefix)
            if local in allow_missing or parsed.path in allow_missing:
                continue
            target_path = html_root / local
            if not target_path.is_file():
                raise HtmlAuditError(f'missing local {attr} target: {current} -> {raw} ({local})')
            if parsed.fragment and target_path.suffix.lower() == '.html':
                if local not in pages:
                    pages[local] = parse_html(target_path)
                fragment = unquote(parsed.fragment)
                count = pages[local].ids[fragment]
                if count != 1:
                    raise HtmlAuditError(
                        f'HTML link fragment must resolve exactly once: {current} -> {raw}; found {count}'
                    )
            if attr == 'href':
                checked_links += 1
            else:
                checked_resources += 1

    # CSS is part of the rendered site contract too. Validate local url(...)
    # references such as bundled fonts/images so a copied stylesheet cannot
    # silently point at a missing resource.
    for css_path in sorted(html_root.rglob('*.css')):
        current = css_path.relative_to(html_root).as_posix()
        css = css_path.read_text(encoding='utf-8', errors='strict')
        for match in re.finditer(r'url\(\s*(["\']?)([^"\')]+)\1\s*\)', css):
            raw = match.group(2).strip()
            if not raw or raw.startswith('#'):
                continue
            parsed = urlsplit(raw)
            if parsed.scheme or raw.startswith('//'):
                continue
            local = _normalise_site_path(current, parsed.path, site_prefix)
            if local in allow_missing or parsed.path in allow_missing:
                continue
            if not (html_root / local).is_file():
                raise HtmlAuditError(f'missing CSS resource: {current} -> {raw} ({local})')
            checked_resources += 1

    result = {
        'html_pages': len(pages),
        'targets': len(targets),
        'links': checked_links,
        'resources': checked_resources,
    }
    summary = ', '.join(f'{key}={value}' for key, value in result.items())
    kinds = ', '.join(f'{key}={value}' for key, value in sorted(kind_counts.items()))
    print(f'HTML AUDIT OK: {summary}; target kinds: {kinds}')
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Audit real mdBook HTML against latex2md conversion-report targets.'
    )
    parser.add_argument('--report', type=Path, required=True,
                        help='conversion-report.json generated by latex2md')
    parser.add_argument('--html', type=Path, required=True,
                        help='mdBook rendered HTML directory (normally BOOK_ROOT/book)')
    parser.add_argument('--site-prefix', default='/diabat-manual/',
                        help='configured mdBook site-url prefix for root-relative links')
    parser.add_argument('--allow-missing', action='append', default=[],
                        help='explicit co-deployed file allowed to be absent in standalone converter CI')
    options = parser.parse_args(argv)
    try:
        audit_html(options.report, options.html, site_prefix=options.site_prefix,
                   allow_missing=set(options.allow_missing))
    except HtmlAuditError as exc:
        print(f'HTML AUDIT FAILED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
