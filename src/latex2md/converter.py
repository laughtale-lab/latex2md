"""Diabat content adapters, cross-reference registry, renderer and strict auditing.

No regex-driven whole-document rewriting: the parser yields structured nodes.
Only a small, documented TeX content vocabulary is supported. Report errors
instead of guessing at author intent when that vocabulary changes.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, replace
import html
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote, urlsplit

from . import __version__
from .bib import Entry, load_bibs
from .parser import Node, ParseError, Reader, plain


@dataclass(frozen=True)
class Target:
    name: str
    page: str
    number: str
    kind: str
    display: str
    render: str
    source: str


@dataclass
class Page:
    filename: str
    title: str
    number: str
    nodes: list[Node]
    anchor: str | None = None


ALIASES = {
    'progname': 'Diabat', 'ProgramName': 'Diabat', 'exec': 'diabat',
    'ExecutableName': 'diabat', 'manualversion': '2.0',
    'OpTrue': '.true.', 'OpFalse': '.false.', 'OpInt': 'INTEGER',
    'OpReal': 'REAL', 'OpLogic': 'LOGICAL', 'OpString': 'STRING',
    'OpIntseq': 'INTEGER SEQUENCE', 'OpRealseq': 'REAL SEQUENCE',
    'OpNone': 'NONE', 'OpOptional': 'OPTIONAL', 'OpRequired': 'REQUIRED',
}
# TeX-only styling commands; adding semantic content here must be reviewed.
SKIP = {
    'frontmatter', 'mainmatter', 'par', 'noindent', 'medskip', 'bigskip', 'smallskip', 'clearpage',
    'cleardoublepage', 'newpage', 'pagebreak', 'nobreak', 'phantomsection',
    'null', 'vfill', 'centering', 'begingroup', 'endgroup',
    'small', 'large', 'Large', 'LARGE', 'huge', 'Huge', 'bfseries',
    'itshape', 'ttfamily', 'rmfamily', 'selectfont', 'fontfamily',
    'pagestyle', 'thispagestyle', 'setlength', 'setstretch',
    'vspace', 'hspace', 'fontsize', 'addtocontents', 'enlargethispage',
    'renewcommand', 'titleformat', 'tableofcontents',
    'cftchappresnum', 'cftchapaftersnum', 'cftchapnumwidth', 'thechapter',
    'chaptername', 'appendixname', 'baselineskip', 'textwidth',
    'paperwidth', 'protect', 'nouppercase', 'fancyhead', 'leftmark',
}
ESCAPES = {'_': '_', '%': '%', '#': '#', '&': '&', '$': '$',
           '{': '{', '}': '}', '~': '~', ' ': ' ', ',': ' ', ';': ' ',
           '!': '', '\\': '  \n', '-': '', '/': ''}
STYLE = {'textbf': ('**', '**'), 'textit': ('*', '*'), 'emph': ('*', '*'),
         'texttt': ('`', '`'), 'underline': ('<u>', '</u>')}
SUPPORTED_ENVS = {'enumerate', 'itemize', 'quote', 'center', 'titlepage', 'document', 'keywordoverview'}
# The only TeX accents seen in the current manual / cited entries.
ACCENTS = {'o': 'ö', 'O': 'Ö', 'u': 'ü', 'U': 'Ü', 'a': 'ä', 'A': 'Ä',
           'e': 'ë', 'E': 'Ë', 'i': 'ï', 'I': 'Ï'}
RE_ESCAPE = re.compile(r'@([^@\n]+)@')  # Targeted documented listings escape marker only
RE_CAPTION = re.compile(r'^\\(scriptnum|examplenum)\{([\w-]+)\}(?:\\enlargethispage\{[^}]+\})?$')
RE_MATH_EXPR = re.compile(r'\$(?!\$)([^\n]+?)\$(?!\$)')  # Only BibTeX prose math
RE_OUTPUT_FILENAME = re.compile(r'^[a-zA-Z0-9_./-]+$')
RE_HTML_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')


class ConversionError(ValueError):
    pass


def slug(text: str) -> str:
    v = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return v or 'untitled'


def safe_url(value: str, location: str) -> str:
    value = value.strip()
    u = urlsplit(value)
    if u.scheme not in {'https', 'http', 'mailto'}:
        raise ConversionError(f'{location}: unsupported URL scheme in {value}')
    return value.replace(' ', '%20')


def clean_source_text(s: str) -> str:
    return s.replace('~', '\u00a0').replace('--', '–').replace('``', '“').replace("''", '”')


class Converter:
    def __init__(self, source: Path, *, main: str = 'main.tex'):
        self.root = source.expanduser().resolve(strict=True)
        self.main = main
        self.labels: dict[str, Target] = {}
        self.pages: list[Page] = []
        self.citations: list[str] = []
        self.references: dict[str, Entry] = {}
        self.assets: set[Path] = set()
        self.stats = Counter()
        self._chapter = 0
        self._appendix = False
        self._script = 0
        self._example = 0
        self._section = 0
        self._subsection = 0
        self._output = 0
        self._current_page: Page | None = None
        self._current_heading: str = ''
        self._files_read: set[Path] = set()
        # Heading labels are bound structurally before registration. The key is
        # the identity of the parsed heading node, not title text or line number.
        self._heading_labels: dict[int, str] = {}
        self._heading_kinds: dict[str, str] = {}
        self._heading_nodes_by_label: dict[str, int] = {}
        self._heading_label_nodes: set[int] = set()
        self._citation_targets: dict[str, Target] = {}

    def inside(self, raw: str, extension: str = '') -> Path:
        candidate = self.root / (raw if not extension or Path(raw).suffix else raw + extension)
        candidate = candidate.resolve()
        if not candidate.is_relative_to(self.root):
            raise ConversionError(f'path outside manual root: {raw}')
        if not candidate.is_file():
            raise ConversionError(f'missing required source file: {candidate}')
        return candidate

    def _open(self, path: Path) -> list[Node]:
        self._files_read.add(path)
        return Reader(path.read_text(encoding='utf-8', errors='replace'),
                      str(path.relative_to(self.root))).parse()

    def _include(self, nodes: list[Node], stack: tuple[Path, ...] = ()) -> list[Node]:
        out = []
        for n in nodes:
            if n.kind == 'macro' and n.value in {'include', 'input'}:
                raw = plain(n.args[0]).strip()
                if raw in {'frontmatter/titlepage', 'frontmatter/toc'}:
                    # Cover graphics and TeX-generated TOC have semantic
                    # equivalents: book intro and mdBook SUMMARY.md.
                    continue
                path = self.inside(raw, '.tex')
                if path in stack:
                    raise ConversionError(f'{n.location}: cyclic input: {" -> ".join(map(str, stack + (path,)))}')
                part = self._include(self._open(path), stack + (path,))
                if raw == 'frontmatter/cite':
                    out.append(Node('virtual-chapter', 'How to Cite Diabat', n.location))
                elif raw == 'frontmatter/links':
                    out.append(Node('virtual-chapter', 'Official Resources', n.location))
                out.extend(part)
                continue
            if n.kind == 'env':
                out.append(replace(n, children=self._include(n.children, stack)))
            else:
                out.append(n)
        return out

    def _macro_simple(self, raw: str) -> str:
        """Plain title/metadata without hyperlinks or script state mutations."""
        # Preserve balanced subgroups and known inline typography; fail on
        # unknown semantic macros as with the main renderer.
        rendered = self.inline(Reader(raw, 'title').parse(), dry=True)
        return ' '.join(html.unescape(rendered.replace('**','').replace('*','').replace('`','').replace('<code>','').replace('</code>','')).split())

    def load(self) -> None:
        edition=self.root/'config/edition-public.tex'
        if edition.exists():
            # TeX conditionals are executable logic, not document markup.
            # Do not silently drop \InternalNote in an internal edition.
            raw=edition.read_text(encoding='utf8')
            active='\n'.join(line.split('%',1)[0] for line in raw.splitlines())
            if r'\internalmanualtrue' in active or r'\publicmanualfalse' in active:
                raise ConversionError(f'{edition}: only the public manual edition is supported')
        main = self.inside(self.main)
        raw = main.read_text(encoding='utf-8', errors='replace')
        first = raw.find(r'\begin{document}')
        last = raw.rfind(r'\end{document}')
        if first < 0 or last < first:
            raise ConversionError(f'{main}: expected \\begin{{document}} / \\end{{document}}')
        self._files_read.add(main)
        nodes = self._include(Reader(raw[first + len(r'\begin{document}'):last], self.main).parse(), (main,))
        self.references = load_bibs([self.inside('references-build.bib')])
        # An additional bibliography can be supplied, but conflicting IDs
        # are diagnosed and unused references are not displayed.
        extra = self.root / 'references-diabat.bib'
        if extra.exists():
            other = load_bibs([extra]); self._files_read.add(extra)
            for key, entry in other.items():
                if key not in self.references:
                    self.references[key] = entry
        self._files_read.add(self.root / 'references-build.bib')
        self._bind_heading_labels(nodes)
        self._register(nodes)
        self._register_citation_targets()
        self._gather_cover_images()
        self.stats['tex_files'] = len([p for p in self._files_read if p.suffix == '.tex'])

    @staticmethod
    def _blank_node(node: Node) -> bool:
        return node.kind == 'text' and not node.value.strip()

    def _bind_heading_labels(self, nodes: list[Node]) -> None:
        """Bind a label only when it structurally follows one heading.

        Whitespace/comment-derived blank text may occur between the heading and
        ``\\label``. Any other node ends the binding opportunity. This prevents
        later prose labels from being guessed as title labels.
        """
        heading_names = {'chapter', 'section', 'subsection', 'subsubsection', 'paragraph'}
        for index, node in enumerate(nodes):
            if node.kind == 'env':
                self._bind_heading_labels(node.children)
            if node.kind != 'macro' or node.value.rstrip('*') not in heading_names:
                continue
            cursor = index + 1
            while cursor < len(nodes) and self._blank_node(nodes[cursor]):
                cursor += 1
            if cursor >= len(nodes):
                continue
            candidate = nodes[cursor]
            if candidate.kind != 'macro' or candidate.value != 'label':
                continue
            key = plain(candidate.args[0]).strip()
            if not key:
                raise ConversionError(f'{candidate.location}: empty heading label')
            if key in self._heading_nodes_by_label:
                raise ConversionError(f'{candidate.location}: heading label bound twice: {key}')
            node_id = id(node)
            self._heading_labels[node_id] = key
            self._heading_kinds[key] = node.value.rstrip('*')
            self._heading_nodes_by_label[key] = node_id
            self._heading_label_nodes.add(id(candidate))

    def _add_label(self, key: str, kind: str, number: str, display: str,
                   location: str, *, render: str, counter: str) -> None:
        key = key.strip()
        if not key:
            raise ConversionError(f'{location}: empty label')
        if not RE_HTML_ID.fullmatch(key):
            raise ConversionError(f'{location}: label is not a safe stable HTML id: {key}')
        if key in self.labels:
            old = self.labels[key]
            raise ConversionError(f'{location}: duplicate label {key} (first in {old.page})')
        assert self._current_page
        self.labels[key] = Target(key, self._current_page.filename, number, kind,
                                  display, render, location)
        self.stats[f'{counter}_labels'] += 1

    def _register_citation_targets(self) -> None:
        for key in self.citations:
            anchor = 'cite-' + slug(key)
            if anchor in self.labels or anchor in self._citation_targets:
                raise ConversionError(f'duplicate generated citation target: {anchor}')
            self._citation_targets[anchor] = Target(
                anchor, 'references.md', '', 'citation', key, 'raw-html', f'bib:{key}'
            )

    def _new_page(self, name: str, virtual=False, loc='') -> None:
        if virtual:
            filename = ('how-to-cite.md' if name.startswith('How to Cite') else
                        'official-resources.md')
            number = ''
        else:
            self._chapter += 1
            self._script = self._example = self._section = self._subsection = self._output = 0
            number = chr(64 + self._chapter) if self._appendix else str(self._chapter)
            filename = ('appendix-' if self._appendix else '') + slug(name) + '.md'
        if any(p.filename == filename for p in self.pages):
            raise ConversionError(f'{loc}: duplicate page slug {filename}')
        self._current_page = Page(filename, name, number, [])
        self.pages.append(self._current_page)
        self._current_heading = number
        self.stats['chapters'] += int(not virtual)

    def _register_listing(self, contents: str, loc: str) -> None:
        # Process only documented @\scriptnum{}@ / @\examplenum{}@ tokens.
        for token in RE_ESCAPE.findall(contents):
            match = RE_CAPTION.fullmatch(token.strip())
            if match:
                kind, key = match.groups()
                if not self._current_page or not self._current_page.number:
                    raise ConversionError(f'{loc}: numbered listing before a chapter: {key}')
                if kind == 'scriptnum':
                    self._script += 1
                    num = self._script
                    labelkind = 'script'
                else:
                    self._example += 1
                    num = self._example
                    labelkind = 'example'
                self._add_label(
                    key, labelkind, str(num), f'{self._current_page.number}-{num}', loc,
                    render='raw-html', counter=labelkind
                )
            elif token == r'\textcolor{mygreen}{\$}':
                pass
            else:
                raise ConversionError(f'{loc}: unknown TeX listing escape: @{token}@')

    def _register(self, nodes: list[Node]) -> None:
        # The first chapter marker sets the first page; early frontmatter
        # virtual chapters remain independent mdBook pages.
        for n in nodes:
            if n.kind == 'virtual-chapter':
                self._new_page(n.value, virtual=True, loc=n.location)
            elif n.kind == 'macro':
                name = n.value.rstrip('*')
                if name == 'appendix':
                    self._appendix = True
                    self._chapter = 0
                    continue
                if name == 'chapter':
                    self._new_page(self._macro_simple(plain(n.args[0])).strip(), loc=n.location)
                elif name in {'section', 'subsection', 'subsubsection'}:
                    if self._current_page and self._current_page.number and not n.value.endswith('*'):
                        if name == 'section':
                            self._section += 1
                            self._subsection = 0
                            self._output = 0
                            self._current_heading = f'{self._current_page.number}.{self._section}'
                        elif name == 'subsection':
                            self._subsection += 1
                            self._current_heading = f'{self._current_page.number}.{self._section}.{self._subsection}'
                        # TeX book class defaults to unnumbered subsubsections.

                heading_key = self._heading_labels.get(id(n))
                if heading_key is not None:
                    if not self._current_page:
                        raise ConversionError(f'{n.location}: heading label outside a page: {heading_key}')
                    self._add_label(
                        heading_key, name, self._current_heading or self._current_page.number,
                        self._current_heading or self._current_page.number, n.location,
                        render='heading', counter='section'
                    )
                    if name == 'chapter':
                        self._current_page.anchor = heading_key
                if name == 'label':
                    key = plain(n.args[0]).strip()
                    if id(n) in self._heading_label_nodes:
                        # This exact label node is rendered by the preceding heading.
                        pass
                    elif key == 'app-divider':
                        if key in self.labels:
                            raise ConversionError(f'{n.location}: duplicate app-divider')
                        self.labels[key] = Target(
                            key, 'appendices.md', '', 'appendix', 'Appendices',
                            'raw-html', n.location
                        )
                    else:
                        if not self._current_page:
                            raise ConversionError(f'{n.location}: label outside chapter')
                        number = self._current_heading or self._current_page.number
                        self._add_label(
                            key, 'standalone', number, number, n.location,
                            render='raw-html', counter='section'
                        )
                elif name == 'includegraphics':
                    self._register_image(plain(n.args[0]).strip(), n.location)
                elif name == 'keyword':
                    self._add_label(
                        plain(n.args[0]), 'keyword', '', self._macro_simple(plain(n.args[1])),
                        n.location, render='raw-html', counter='keyword'
                    )
                    self.stats['keywords'] += 1
                elif name == 'cite':
                    self._citation_keys(plain(n.args[0]), n.location)
                elif name == 'lstinputlisting':
                    path = self.inside(plain(n.args[0]).strip())
                    self._register_listing(path.read_text(encoding='utf-8', errors='replace'),
                                           str(path.relative_to(self.root)))
                    self._files_read.add(path)
                    self.stats['external_listings'] += 1
                elif name in {'scriptnum', 'examplenum'}:
                    # Outside the listings environment, explicitly supported.
                    self._register_listing('@\\' + name + '{' + plain(n.args[0]) + '}@', n.location)
                if self._current_page is not None:
                    self._current_page.nodes.append(n)
            elif n.kind == 'verbatim':
                self._register_listing(n.children[0].value, n.location)
                if self._current_page:
                    self._current_page.nodes.append(n)
            elif n.kind == 'env':
                if n.value not in SUPPORTED_ENVS | {'equation', 'align', 'align*'}:
                    raise ConversionError(f'{n.location}: unsupported environment {n.value}')
                # Register labels/cites inside list items, mathematical
                # references can be handled independently if labels used.
                saved = self._current_page
                self._register(n.children)
                # Avoid rendering children twice. Turn the original env into
                # a wrapper rather than append its already-registered children.
                if saved:
                    child_set = set(map(id, n.children))
                    saved.nodes[:] = [x for x in saved.nodes if id(x) not in child_set]
                    saved.nodes.append(n)
            elif n.kind in {'group', 'math', 'math-display', 'text', 'table', 'break'}:
                if self._current_page:
                    self._current_page.nodes.append(n)
            else:
                raise ConversionError(f'{n.location}: unsupported node {n.kind}')
        for key in self.citations:
            if key not in self.references:
                raise ConversionError(f'missing BibTeX citation {key}')

    def _register_image(self, name: str, location: str) -> None:
        filename=Path(name).name
        candidate=self.inside('assets/'+filename)
        self.assets.add(candidate)

    def _gather_cover_images(self) -> None:
        # The print cover is omitted structurally, not lost. Relevant logo
        # and banner images are copied for the HTML introduction page.
        cover=self.root/'frontmatter/titlepage.tex'
        if not cover.is_file(): return
        tokens=Reader(cover.read_text(encoding='utf8'), str(cover.relative_to(self.root))).parse()
        def scan(nodes):
            for node in nodes:
                if node.kind=='macro' and node.value=='includegraphics':
                    self._register_image(plain(node.args[0]).strip(),node.location)
                for arg in node.args: scan(arg)
                if node.children: scan(node.children)
        scan(tokens)

    def _citation_keys(self, keys: str, loc: str) -> None:
        for key in keys.split(','):
            k = key.strip()
            if not k: raise ConversionError(f'{loc}: empty citation')
            if k not in self.citations: self.citations.append(k)

    def _link(self, key: str, text: str, dry: bool, loc: str) -> str:
        if dry:
            return text
        target = self.labels.get(key)
        if not target:
            raise ConversionError(f'{loc}: unresolved internal reference: {key}')
        assert self._render_page
        href = ('#' if target.page == self._render_page.filename else target.page + '#') + quote(key)
        self.stats['resolved_links'] += 1
        return f'[{text}]({href})'

    def inline(self, nodes: list[Node], dry=False) -> str:
        out = []
        for n in nodes:
            if n.kind == 'text': out.append(clean_source_text(n.value))
            elif n.kind == 'group': out.append(self.inline(n.children, dry))
            elif n.kind == 'break': out.append('  \n')
            elif n.kind.startswith('math'):
                if n.kind == 'math': out.append('\\\\(' + n.value + '\\\\)')
                else: out.append('\\\\[\n' + n.value + '\n\\\\]')
                self.stats['math_expressions'] += int(not dry)
            elif n.kind == 'macro':
                name = n.value.rstrip('*')
                arg = lambda i=0: self.inline(n.args[i], dry)
                rawarg = lambda i=0: plain(n.args[i])
                if name in ALIASES: out.append(ALIASES[name])
                elif name in ESCAPES: out.append(ESCAPES[name])
                elif name in STYLE:
                    start, end = STYLE[name]
                    val = arg().strip()
                    if name == 'texttt':
                        out.append('<code>' + html.escape(val.replace('`', '')) + '</code>')
                    else: out.append(start + val + end)
                elif name in {'path', 'url'}:
                    value = rawarg().replace(r'\_', '_')
                    if name == 'url': out.append(f'<{safe_url(value, n.location)}>')
                    else: out.append('<code>' + html.escape(value) + '</code>')
                elif name == 'includegraphics':
                    path=Path(rawarg()).name
                    if not dry:
                        self._register_image(path,n.location)
                    out.append(f'![{html.escape(Path(path).stem)}](assets/{quote(path)})')
                elif name == 'href':
                    url = safe_url(rawarg(), n.location)
                    out.append(f'[{arg(1)}]({url})')
                elif name in {'keyref', 'hyperlink'}:
                    out.append(self._link(rawarg(), arg(1), dry, n.location))
                elif name == 'ref':
                    key = rawarg()
                    number = self.labels[key].number if key in self.labels else '?' 
                    out.append(self._link(key, number, dry, n.location))
                elif name == 'pageref':
                    key = rawarg()
                    out.append(self._link(key, 'section', dry, n.location))
                elif name == 'Sec':
                    key = rawarg()
                    number = self.labels[key].number if key in self.labels else '?'
                    out.append('Sec. ' + self._link(key, number, dry, n.location))
                elif name in {'script', 'example'}:
                    chap, key = rawarg(0), rawarg(1)
                    if not dry:
                        ch = self.labels.get(chap)
                        target = self.labels.get(key)
                        if ch is None or target is None:
                            raise ConversionError(f'{n.location}: invalid {name} reference: {chap}, {key}')
                        if ch.number != target.display.split('-')[0]:
                            raise ConversionError(f'{n.location}: {name} reference points to wrong chapter: {key}')
                        show = ('Script ' if name == 'script' else 'Example ') + target.display
                    else: show = name.title()
                    out.append(self._link(key, show, dry, n.location))
                elif name == 'cite':
                    keys = [k.strip() for k in rawarg().split(',')]
                    def c(k):
                        if dry: return 'citation'
                        if k not in self.citations: raise ConversionError(f'{n.location}: citation not indexed {k}')
                        return f'[{self.citations.index(k)+1}](references.md#cite-{slug(k)})'
                    out.append('[' + ', '.join(c(k) for k in keys) + ']')
                    self.stats['citation_occurrences'] += int(not dry)
                elif name in {'L', 'l'}: out.append('Ł' if name == 'L' else 'ł')
                elif name == '"':
                    letter = arg().strip()
                    if letter not in ACCENTS:
                        raise ConversionError(f'{n.location}: unsupported TeX diaeresis accent: {letter}')
                    out.append(ACCENTS[letter])
                elif name == 'MakeUppercase': out.append(arg().upper())
                elif name == 'textcolor': out.append(arg(1))
                elif name == 'InternalNote':
                    # The supplied manual is explicitly public edition.
                    # Do not guess for arbitrary future conditional macros.
                    pass
                elif name in SKIP: pass
                elif name in {'label', 'item', 'section', 'subsection', 'subsubsection'}:
                    raise ConversionError(f'{n.location}: block command \\{name} in inline context')
                elif name == 'thechapter': out.append('')
                else:
                    raise ConversionError(f'{n.location}: unsupported active inline command \\{name}')
            else:
                raise ConversionError(f'{n.location}: unexpected {n.kind} in inline context')
        return ''.join(out)

    def _convert_escape(self, match: re.Match, loc: str) -> str:
        token = match.group(1).strip()
        if token == r'\textcolor{mygreen}{\$}': return '$'
        if RE_CAPTION.fullmatch(token): return ''
        raise ConversionError(f'{loc}: unknown code escape: @{token}@')

    def _listing(self, text: str, loc: str, language: str) -> str:
        found = []
        for match in RE_ESCAPE.finditer(text):
            cap = RE_CAPTION.fullmatch(match.group(1).strip())
            if cap: found.append((cap.group(1), cap.group(2)))
        if len(found) > 1: raise ConversionError(f'{loc}: multiple captions in one code block')
        caption = ''
        if found:
            kind, key = found[0]
            target = self.labels.get(key)
            if target is None: raise ConversionError(f'{loc}: caption not indexed: {key}')
            label = 'Script' if kind == 'scriptnum' else 'Example'
            caption = f'<div class="listing-caption" id="{html.escape(key)}">{label} {target.display}</div>\n\n'
        content = RE_ESCAPE.sub(lambda m: self._convert_escape(m, loc), text).strip('\n')
        # Only the listing files under `examples/display` have TeX escape
        # sequences. Never rewrite or execute inputs under examples/release.
        if '\\' in content and re.search(r'\\(?:scriptnum|examplenum)\b', content):
            raise ConversionError(f'{loc}: unconverted caption left in listing')
        fence = '`' * (max([len(g) for g in re.findall(r'`+', content)] or [2]) + 1)
        self.stats['listings'] += 1
        return caption + f'{fence}{language}\n{content}\n{fence}\n\n'

    def _table(self, node: Node) -> str:
        raw = node.children[0].value.strip()
        # TeX table rows are detected at the top brace depth. The parser
        # understands nested TeX groups, not a 'replace ampersands' regex.
        rows: list[list[str]] = []
        current: list[str] = []
        buf = []
        i, depth, comment = 0, 0, False
        while i < len(raw):
            c = raw[i]
            if c == '\n': comment = False
            if comment: i += 1; continue
            if c == '%': comment = True; i += 1; continue
            if c == '\\':
                if raw.startswith('\\\\', i) and depth == 0:
                    current.append(''.join(buf).strip());buf=[]
                    rows.append(current);current=[]
                    i += 2
                    continue
                # Escape punctuation is just part of the current TeX cell.
                if i + 1 < len(raw) and not raw[i + 1].isalpha():
                    buf.extend(raw[i:i+2]);i+=2;continue
            if c == '{': depth += 1
            if c == '}': depth -= 1
            if c == '&' and depth == 0:
                current.append(''.join(buf).strip());buf=[]
            else: buf.append(c)
            i += 1
        if ''.join(buf).strip() or current:
            current.append(''.join(buf).strip());rows.append(current)
        cooked=[]
        for row in rows:
            # The current hand-edited technical table has precisely two cells;
            # trailing hlines and rowcolor are purely presentational.
            cells=[]
            for cell in row:
                cell = re.sub(r'\\(?:hline|toprule|midrule|bottomrule)\b', '', cell)
                cell = re.sub(r'\\rowcolor\{[^}]+\}', '', cell).strip()
                if cell:
                    value = self.inline(Reader(cell, node.location).parse()).strip()
                    cells.append(value.replace('|', r'\|').replace('\n', ' '))
            if cells:
                cooked.append(cells)
        if not cooked:
            raise ConversionError(f'{node.location}: empty longtable')
        cols = len(cooked[0])
        for row in cooked:
            if len(row) != cols:
                raise ConversionError(f'{node.location}: inconsistent table row length: {len(row)} vs {cols}: {row}')
        self.stats['tables'] += 1
        return '| ' + ' | '.join(cooked[0]) + ' |\n| ' + ' | '.join(['---']*cols) + ' |\n' + ''.join(
            '| ' + ' | '.join(row) + ' |\n' for row in cooked[1:]) + '\n'

    def _env(self, node: Node) -> str:
        if node.value in {'equation', 'align', 'align*'}:
            raw = plain(node.children).strip()
            self.stats['math_expressions'] += 1
            return '\\\\[\n' + (r'\begin{aligned}' + raw + r'\end{aligned}' if node.value.startswith('align') else raw) + '\n\\\\]\n\n'
        if node.value in {'center', 'quote', 'titlepage', 'document'}:
            body = self.blocks(node.children).strip()
            if node.value == 'center' and self._render_page is not None and not self._render_page.number:
                # These two frontmatter files render their print headings
                # manually; mdBook has already supplied the corresponding H1.
                if body.startswith(self._render_page.title):
                    body=body[len(self._render_page.title):].lstrip()
            if node.value == 'quote':
                return '\n'.join('> ' + line if line else '>' for line in body.splitlines()) + '\n\n'
            return body + '\n\n'
        if node.value in {'enumerate', 'itemize'}:
            groups=[]
            current=[]
            for inner in node.children:
                if inner.kind == 'macro' and inner.value == 'item':
                    if any(node.kind!='text' or node.value.strip() for node in current): groups.append(current)
                    current=[]
                else: current.append(inner)
            if any(node.kind!='text' or node.value.strip() for node in current): groups.append(current)
            if not groups: raise ConversionError(f'{node.location}: empty list')
            items=[]
            groups=[part for part in groups if any(node.kind!='text' or node.value.strip() for node in part)]
            for index, part in enumerate(groups):
                content=self.blocks(part).strip()
                marker=(f'{index+1}.' if node.value == 'enumerate' else '-') + ' '
                lines=content.splitlines()
                if not lines:
                    raise ConversionError(f'{node.location}: empty rendered list item')
                # CommonMark list continuation blocks must be indented to the
                # content column established by the marker.  A fixed two-space
                # indent is wrong for ordered items such as ``8. `` (3 columns)
                # and ``10. `` (4 columns), and can make a nested closing fence
                # start a brand-new outer code block that consumes later
                # sections.  Preserve every continuation line at that column.
                continuation=' ' * len(marker)
                rendered=[marker + lines[0]]
                rendered.extend(continuation + line if line else continuation
                                for line in lines[1:])
                items.append('\n'.join(rendered))
            self.stats['lists'] += 1
            return '\n'.join(items) + '\n\n'
        raise ConversionError(f'{node.location}: unhandled environment {node.value}')

    def _keyword(self, n: Node) -> str:
        key = plain(n.args[0]).strip()
        caption = self.inline(n.args[1]).strip()
        values = [self.inline(a).strip().replace('|', r'\|').replace('\n', ' ') for a in n.args[2:]]
        # A Markdown definition table avoids rendering Markdown inside HTML
        # table cells, which pulldown-cmark does not guarantee to parse.
        headings = ['Description', 'Necessity', 'Data Type', 'Default',
                    'Options', 'Suggestion', 'Example']
        if len(values) != len(headings): raise ConversionError(f'{n.location}: keyword field mismatch')
        rows = [f'| **Identifier** | <code>{html.escape(caption)}</code> |', '| --- | --- |']
        rows.extend(f'| **{heading}** | {value} |' for heading,value in zip(headings, values))
        return (f'<div class="target-anchor keyword-target" id="{html.escape(key)}"></div>\n\n'
                + '\n'.join(rows) + '\n\n')

    def _overview(self, n: Node) -> str:
        rows=['| Keyword | Purpose |', '| --- | --- |']
        for entry in n.children:
            if entry.kind == 'macro' and entry.value == 'keyitem':
                key=plain(entry.args[0])
                keyword=self.inline(entry.args[1])
                purpose=self.inline(entry.args[2]).strip().replace('|',r'\|')
                rows.append('| ' + self._link(key, '<code>' + html.escape(keyword) + '</code>', False, entry.location) + ' | ' + purpose + ' |')
                self.stats['overview_items'] += 1
            elif entry.kind == 'text' and not entry.value.strip(): pass
            else: raise ConversionError(f'{entry.location}: only \\keyitem allowed in keywordoverview')
        return '\n'.join(rows)+'\n\n'

    def blocks(self, nodes: list[Node]) -> str:
        out=[]; inline=[]
        def flush():
            if inline:
                contents=self.inline(inline).strip()
                if contents: out.append(contents+'\n\n')
                inline.clear()
        for n in nodes:
            if n.kind in {'text','group','math','math-display','break'}:
                inline.append(n); continue
            if n.kind == 'macro':
                name=n.value.rstrip('*')
                if name in {'chapter','section','subsection','subsubsection','paragraph'}:
                    flush()
                    if name != 'chapter':
                        depth={'section':2,'subsection':3,'subsubsection':4,'paragraph':5}[name]
                        title=self.inline(n.args[0]).strip()
                        if name == 'section' and not n.value.endswith('*'):
                            self._section_render+=1
                            self._subsection_render=0
                            title=f'{self._render_page.number}.{self._section_render} '+title
                        elif name == 'subsection' and not n.value.endswith('*'):
                            self._subsection_render+=1
                            title=f'{self._render_page.number}.{self._section_render}.{self._subsection_render} '+title
                        anchor = self._heading_labels.get(id(n))
                        suffix = f' {{ #{anchor} }}' if anchor else ''
                        out.append('#'*depth+' '+title+suffix+'\n\n')
                    continue
                if name == 'label':
                    key=plain(n.args[0]).strip();flush()
                    if key not in self.labels: raise ConversionError(f'{n.location}: unknown label {key}')
                    target = self.labels[key]
                    if target.render == 'heading':
                        # The preceding heading carries the native mdBook ID.
                        continue
                    if target.page != self._render_page.filename:
                        # TeX's appendix divider becomes a dedicated mdBook page.
                        continue
                    out.append(
                        f'<div class="target-anchor standalone-target" id="{html.escape(key)}"></div>\n\n'
                    );continue
                if name in {'appendix','printbibliography','addcontentsline','addtocontents'}:
                    flush();continue
                if name == 'keyword': flush();out.append(self._keyword(n));continue
                if name == 'outputfile':
                    flush();self._output_render += 1
                    title=self.inline(n.args[0]).strip()
                    desc=self.inline(n.args[1]).strip()
                    out.append(f'**{self._output_render}. <code>{html.escape(title)}</code>**  \n{desc}\n\n')
                    self.stats['output_files']+=1;continue
                if name == 'keyitem': raise ConversionError(f'{n.location}: keyitem outside keywordoverview')
                if name in {'exampleheading','examplepath'}:
                    flush();content=self.inline(n.args[0]).strip()
                    out.append(('**'+content+'**' if name=='exampleheading' else '<small><code>'+html.escape(content)+'</code></small>')+'\n\n')
                    continue
                if name == 'lstinputlisting':
                    flush()
                    rawpath=plain(n.args[0]).strip()
                    path=self.inside(rawpath)
                    raw=path.read_text(encoding='utf-8',errors='replace')
                    out.append(self._listing(raw,rawpath,'diabat'))
                    continue
                if name in {'scriptnum','examplenum'}:
                    flush();key=plain(n.args[0]);t=self.labels.get(key)
                    if t is None: raise ConversionError(f'{n.location}: missing numbered caption {key}')
                    label='Script' if name=='scriptnum' else 'Example'
                    out.append(f'<div class="listing-caption" id="{html.escape(key)}">{label} {t.display}</div>\n\n')
                    continue
                if name in {'hline','rowcolor'}: continue
                inline.append(n)
                continue
            if n.kind == 'verbatim':
                flush()
                lang='bash' if n.value in {'ShellBlock','lst-installation'} else ('diabat' if n.value in {'lst-script','DiabatScript'} else 'text')
                out.append(self._listing(n.children[0].value,n.location,lang))
                continue
            if n.kind == 'table':flush();out.append(self._table(n));continue
            if n.kind == 'env':
                flush()
                if n.value=='keywordoverview':out.append(self._overview(n))
                else:out.append(self._env(n))
                continue
            raise ConversionError(f'{n.location}: unknown block {n.kind}')
        flush()
        return ''.join(out)

    def _render_reference(self, entry: Entry, order: int) -> str:
        f=entry.fields
        title=self._bib_text(f.get('title',''))
        author=self._bib_text(f.get('author', ''))
        journal=self._bib_text(f.get('journal') or f.get('journaltitle') or
                               f.get('booktitle') or f.get('publisher',''))
        year=self._bib_text(f.get('year',''))
        vol=self._bib_text(f.get('volume',''))
        pages=self._bib_text(f.get('pages','')).replace('--','–')
        notes=self._bib_text(f.get('note',''))
        bits=[s for s in [author, f'**{title}**' if title else '', journal,
                            f'{vol} ({year})' if vol and year else year or vol,
                            pages, notes] if s]
        url=f.get('doi')
        if url: bits.append(f'[DOI](https://doi.org/{quote(url.strip())})')
        elif f.get("url"):
            url = safe_url(f["url"], "bib:" + entry.key)
            bits.append(f"[Link]({url})")
        if not bits: raise ConversionError(f'empty bibliography entry: {entry.key}')
        anchor = 'cite-' + slug(entry.key)
        return (f'<div class="target-anchor citation-target" id="{anchor}"></div>\n\n'
                + f'{order}. ' + '; '.join(bits) + '.\n\n')

    def _bib_text(self, raw: str) -> str:
        # Strip protective BibTeX braces as groups, not global substitutions.
        # Common accent syntax in names is retained as Unicode.
        raw=raw.replace(r'\"{u}','ü').replace(r'\"{o}','ö').replace(r'\"u','ü').replace(r'\"o','ö')
        raw=raw.replace('{','').replace('}','').replace(r'\&','&').replace('~',' ')
        return RE_MATH_EXPR.sub(lambda m: '\\\\('+m.group(1)+'\\\\)',raw).strip()

    def _copy_examples(self, out: Path) -> str:
        # Copy original input files byte-for-byte; not presentation-only .lst.
        base=self.root/'examples'
        if not base.is_dir(): return ''
        files=[]
        for sub in ('release','tutorials','templates'):
            folder=base/sub
            if not folder.is_dir(): continue
            for src in sorted(folder.rglob('*')):
                if src.is_symlink(): raise ConversionError(f'symlinked input not allowed: {src}')
                if src.is_file() and src.suffix.lower() in {'.inp','.gjf'}:
                    relative=src.relative_to(self.root)
                    dest=out/'downloads'/relative
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(src,dest)
                    if dest.read_bytes()!=src.read_bytes():
                        raise ConversionError(f'copied source input differs: {relative}')
                    files.append(relative)
        self.stats['original_input_files']=len(files)
        if not files:return ''
        contents=['# Original example input files','',
            'Files below are copied **byte-for-byte** from the Manual source. '
            'They differ from the annotated `.lst` files used only for display. '
            'Some inputs need external programs, orbital files or additional datasets before they can run.', '']
        contents.extend(f'- [{html.escape(str(file))}](downloads/{quote(str(file),safe="/")})' for file in files)
        (out/'example-inputs.md').write_text('\n'.join(contents)+'\n',encoding='utf8')
        return 'example-inputs.md'

    def _copy_assets(self, out: Path) -> None:
        dest=out/'assets';dest.mkdir(parents=True,exist_ok=True)
        for src in sorted(self.assets):
            # Src is rooted under source/assets. Keep basename because
            # includegraphics resolves via source \graphicspath{{assets/}}.
            shutil.copy2(src,dest/src.name)
        self.stats['images']=len(self.assets)

    def _render_page_body(self, page: Page) -> str:
        self._render_page=page
        self._output_render=0
        self._section_render=0
        body=self.blocks(page.nodes)
        anchor = f' {{ #{page.anchor} }}' if page.anchor else ''
        prefix=('# '+(page.number+' ' if page.number else '')+page.title+anchor+'\n\n')
        return prefix+body

    def _all_targets(self) -> dict[str, Target]:
        targets = dict(self.labels)
        for anchor, target in self._citation_targets.items():
            if anchor in targets:
                raise ConversionError(f'duplicate target id across labels/citations: {anchor}')
            targets[anchor] = target
        return targets

    def _audit(self, dest: Path) -> None:
        """Audit generated Markdown before invoking mdBook.

        This catches missing source-level destinations early. The authoritative
        contract is verified later against *rendered* mdBook HTML by
        ``latex2md-audit-html``.
        """
        targets = self._all_targets()
        for anchor, target in targets.items():
            page = dest / target.page
            if not page.is_file():
                raise ConversionError(f'target {anchor} points to missing Markdown page: {page}')
            text = page.read_text(encoding='utf-8')
            if target.render == 'heading':
                count = len(re.findall(
                    rf'^#{{1,6}} .+ \{{ #{re.escape(anchor)} \}}\s*$', text,
                    flags=re.MULTILINE
                ))
            elif target.render == 'raw-html':
                count = text.count(f'id="{anchor}"')
            else:
                raise ConversionError(f'unknown target render mode {target.render}: {anchor}')
            if count != 1:
                raise ConversionError(
                    f'Markdown target {anchor} must occur exactly once in {target.page}; found {count}'
                )
        for page in dest.glob('*.md'):
            contents=page.read_text(encoding='utf-8')
            for link in re.findall(r'\]\(([^)]+)\)',contents):
                if urlsplit(link).scheme:
                    continue
                if '#' in link:
                    other,anchor=link.split('#',1)
                    if other and not (dest/other).is_file():
                        raise ConversionError(f'{page}: missing linked Markdown page {other}')
                    if anchor and anchor not in targets:
                        raise ConversionError(f'{page}: link points to unregistered target #{anchor}')
                    if anchor and other and targets[anchor].page != other:
                        raise ConversionError(
                            f'{page}: target #{anchor} is registered in {targets[anchor].page}, not {other}'
                        )
                elif link.endswith('.md') and not (dest/link).is_file():
                    raise ConversionError(f'{page}: missing linked Markdown page {link}')

    def _add_html_assets(self, out: Path) -> None:
        import importlib.resources
        package=importlib.resources.files('latex2md')
        for name in ('diabat.css','diabat-highlight.js'):
            (out/name).write_bytes(package.joinpath('resources',name).read_bytes())

    def write(self, destination: Path) -> dict:
        if not self.pages: raise ConversionError('empty document (did you call load()?)')
        out=destination.expanduser().resolve()
        if out==self.root or out.is_relative_to(self.root):
            # A generated tree nested in the manual repository is safe only
            # when explicitly ignored; refuse direct overwrite of LaTeX.
            if out==self.root: raise ConversionError('output may not replace the source root')
        if out.exists() and any(out.iterdir()):
            raise ConversionError(f'output must be an empty directory: {out}')
        out.mkdir(parents=True,exist_ok=True)
        self._render_page=None
        for page in self.pages:
            self._section_render=0
            body=self._render_page_body(page)
            (out/page.filename).write_text(body,encoding='utf8')
        ref=''.join(self._render_reference(self.references[key],i+1)
                    for i,key in enumerate(self.citations))
        (out/'references.md').write_text('# References\n\n'+ref,encoding='utf8')
        summary=['# Summary','', '[Welcome](README.md)','','---','']
        main_chapters=[p for p in self.pages if p.number and p.number[0].isdigit()]
        appendix=[p for p in self.pages if p.number and p.number[0].isalpha()]
        front=[p for p in self.pages if not p.number]
        for p in front:summary.append(f'- [{p.title}]({p.filename})')
        for p in main_chapters:summary.append(f'- [{p.number} {p.title}]({p.filename})')
        if appendix:
            summary.extend(['','---','','- [Appendices](appendices.md)'])
            for p in appendix:summary.append(f'    - [Appendix {p.number}: {p.title}]({p.filename})')
            (out/'appendices.md').write_text(
                '# Appendices\n\n<div class="target-anchor standalone-target" id="app-divider"></div>\n\n'
                + '\n'.join(
                f'- [Appendix {p.number}: {p.title}]({p.filename})' for p in appendix)+'\n',encoding='utf8')
        originals=self._copy_examples(out)
        if originals:
            summary.append('- [Original example inputs](example-inputs.md)')
        summary.append('- [References](references.md)')
        (out/'SUMMARY.md').write_text('\n'.join(summary)+'\n',encoding='utf8')
        cover = ''
        if any(src.name=='banner-cover-trimmed.png' for src in self.assets):
            cover += '![Diabat Manual banner](assets/banner-cover-trimmed.png)\n\n'
        if any(src.name=='diabat-logo.png' for src in self.assets):
            cover += '![Diabat logo](assets/diabat-logo.png)\n\n'
        (out/'README.md').write_text('# Diabat 2.0 User Manual\n\n'+cover+
             'This online edition is generated from the **LaTeX source**.\n\n'
             '- [Read the manual](%s)\n' % (main_chapters[0].filename if main_chapters else self.pages[0].filename) +
             '- <a href="diabat.pdf">Latest PDF</a>\n' +
             ('- [Original example input files](example-inputs.md)\n' if originals else '') +
             '\n'
             'For the definitive print layout, consult the PDF edition.\n',encoding='utf8')
        (destination.parent/'book.toml').write_text('''[book]
title = "Diabat 2.0 User Manual"
authors = ["Diabat contributors"]
language = "en"
src = "src"

[output.html]
mathjax-support = true
no-section-label = true
additional-css = ["src/diabat.css"]
additional-js = ["src/diabat-highlight.js"]
site-url = "/diabat-manual/"

[output.html.print]
enable = false

[output.html.search]
enable = true
''',encoding='utf8')
        self._add_html_assets(out)
        self._copy_assets(out)
        self._audit(out)
        self.stats['references_used']=len(self.citations)
        self.stats['pages']=len(self.pages)+2+int(bool(appendix))+int(bool(originals)) # README + References + appendix navigation
        report={'version':__version__, 'source_entry':self.main, 'statistics':dict(sorted(self.stats.items())),
                'labels':{k:vars(v) for k,v in sorted(self.labels.items())},
                'targets':{k:vars(v) for k,v in sorted(self._all_targets().items())},
                'citations':self.citations,
                'source_files':sorted(str(x.relative_to(self.root)) for x in self._files_read)}
        (destination.parent/'conversion-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
        return report


def convert(source: Path, destination: Path, *, main='main.tex') -> dict:
    """Write a self-contained mdBook input directory; commit nothing to source.

    A staging directory guarantees that failures cannot leave partial output.
    The caller passes the *book root*: e.g. `/tmp/diabat-book`, containing
    `book.toml` and `src/`. The root must not contain previous output.
    """
    destination=destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ConversionError(f'output directory is not empty: {destination}')
    c=Converter(source,main=main)
    c.load()
    # The staging tree is next to the eventual root to preserve rename
    # atomicity when both locations share a filesystem.
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.latex2md-',dir=destination.parent) as tmp:
        stage=Path(tmp)/'book'
        stage.mkdir()
        result=c.write(stage/'src')
        if destination.exists():
            destination.rmdir()
        stage.rename(destination)
        return result
