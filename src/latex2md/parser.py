"""Balanced single-pass TeX reader for the *content* subset in Diabat.

A deliberately explicit structural parser: no whole-document regexp substitution.
TeX is a programming language, not a generic markup format. Unexpected active
commands fail in the renderer; the lexer only understands the documented subset.
This is not a general TeX engine and does not evaluate user-defined macros.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Node:
    kind: str
    value: str
    location: str
    args: list[list['Node']] = field(default_factory=list)
    option: str | None = None
    children: list['Node'] = field(default_factory=list)


class ParseError(ValueError):
    pass


# Content rendered literally; TeX listings escape markers are resolved by renderer.
VERBATIM = {'lst-script', 'lst-installation', 'lstlisting', 'DiabatScript',
            'ShellBlock', 'lst-script*'}
TABLES = {'longtable', 'tabular', 'tabularx'}
ARGS = {
    'input': 1, 'include': 1, 'chapter': 1, 'section': 1,
    'subsection': 1, 'subsubsection': 1, 'paragraph': 1,
    'label': 1, 'ref': 1, 'pageref': 1, 'Sec': 1, 'cite': 1,
    'keyref': 2, 'keyitem': 3, 'keyword': 9, 'outputfile': 2,
    'script': 2, 'example': 2, 'scriptnum': 1, 'examplenum': 1,
    'textbf': 1, 'textit': 1, 'texttt': 1, 'emph': 1, 'underline': 1,
    'url': 1, 'href': 2, 'hyperlink': 2, 'hypertarget': 2,
    'textcolor': 2, 'includegraphics': 1, 'path': 1,
    'exampleheading': 1, 'examplepath': 1, 'footnote': 1,
    'addcontentsline': 3, 'addtocontents': 2, 'setlength': 2,
    'fontsize': 2, 'vspace': 1, 'hspace': 1, 'setstretch': 1,
    'thispagestyle': 1, 'pagestyle': 1, 'renewcommand': 2,
    'titleformat': 1, 'MakeUppercase': 1, 'raisebox': 2,
    'caption': 1, 'centering': 0, 'lstinputlisting': 1,
    'InternalNote': 1,
}


class Reader:
    def __init__(self, text: str, source: str):
        self.text = text
        self.source = source
        self.i = 0
        self.n = len(text)

    def loc(self, pos: int | None = None) -> str:
        p = self.i if pos is None else pos
        return f'{self.source}:{self.text.count(chr(10), 0, p) + 1}'

    def error(self, message: str) -> ParseError:
        return ParseError(f'{self.loc()}: {message}')

    def ws(self) -> None:
        while self.i < self.n and self.text[self.i].isspace():
            self.i += 1

    def group_raw(self, opening: str, closing: str) -> str:
        if self.i >= self.n or self.text[self.i] != opening:
            raise self.error(f'expected {opening}')
        start = self.i + 1
        self.i += 1
        depth = 1
        while self.i < self.n:
            c = self.text[self.i]
            if c == '\\':
                self.i += 1
                if self.i < self.n:
                    if self.text[self.i].isalpha():
                        while self.i < self.n and self.text[self.i].isalpha():
                            self.i += 1
                    else:
                        self.i += 1
                continue
            if c == '%':
                # A comment may contain unmatched braces.
                j = self.text.find('\n', self.i)
                self.i = self.n if j < 0 else j
                continue
            if c == opening:
                depth += 1
            if c == closing:
                depth -= 1
                if depth == 0:
                    val = self.text[start:self.i]
                    self.i += 1
                    return val
            self.i += 1
        raise self.error(f'unterminated {opening} group')

    def argument(self) -> list[Node]:
        self.ws()
        if self.i >= self.n or self.text[self.i] != '{':
            raise self.error('expected mandatory {...} argument')
        raw = self.group_raw('{', '}')
        return Reader(raw, self.loc()).parse()

    def optional(self) -> str | None:
        self.ws()
        return self.group_raw('[', ']') if self.i < self.n and self.text[self.i] == '[' else None

    def command(self) -> str:
        assert self.text[self.i] == '\\'
        self.i += 1
        if self.i >= self.n:
            raise self.error('trailing backslash')
        if self.text[self.i].isalpha():
            start = self.i
            while self.i < self.n and self.text[self.i].isalpha():
                self.i += 1
            name = self.text[start:self.i]
            # Starred forms are structurally the same for supported formatting.
            if name in {'chapter', 'section', 'subsection', 'subsubsection',
                        'paragraph', 'vspace', 'hspace'} and self.i < self.n and self.text[self.i] == '*':
                name += '*'
                self.i += 1
            return name
        name = self.text[self.i]
        self.i += 1
        return name

    def math(self, end: str, display: bool, start: int) -> Node:
        content_start = self.i
        while self.i < self.n:
            if self.text[self.i] == '\\':
                # An escaped math delimiter is not an end delimiter.
                if self.text.startswith(end, self.i):
                    raw = self.text[content_start:self.i]
                    self.i += len(end)
                    return Node('math-display' if display else 'math', raw.strip(), self.loc(start))
                self.i += 2
                continue
            if self.text.startswith(end, self.i):
                raw = self.text[content_start:self.i]
                self.i += len(end)
                return Node('math-display' if display else 'math', raw.strip(), self.loc(start))
            self.i += 1
        raise self.error('unterminated math expression')

    def raw_environment(self, name: str, start: int, option: str | None) -> Node:
        marker = r'\end{' + name + '}'
        j = self.text.find(marker, self.i)
        if j < 0:
            raise self.error(f'unterminated verbatim/table environment {name}')
        content = self.text[self.i:j]
        self.i = j + len(marker)
        return Node('verbatim' if name in VERBATIM else 'table', name, self.loc(start),
                    option=option, children=[Node('raw', content, self.loc(start))])

    def parse(self, until_env: str | None = None) -> list[Node]:
        result: list[Node] = []
        buf: list[str] = []
        bufpos = self.i

        def flush():
            nonlocal bufpos
            if buf:
                result.append(Node('text', ''.join(buf), self.loc(bufpos)))
                buf.clear()
            bufpos = self.i

        while self.i < self.n:
            c = self.text[self.i]
            if c == '%':
                flush()
                j = self.text.find('\n', self.i)
                self.i = self.n if j < 0 else j + 1
                # Keep a single newline to prevent concatenating words.
                result.append(Node('text', '\n', self.loc()))
                continue
            if c == '$' and (self.i == 0 or self.text[self.i - 1] != '\\'):
                flush()
                start = self.i
                display = self.text.startswith('$$', self.i)
                self.i += 2 if display else 1
                result.append(self.math('$$' if display else '$', display, start))
                continue
            if c == '{':
                flush()
                start = self.i
                raw = self.group_raw('{', '}')
                result.append(Node('group', '', self.loc(start), children=Reader(raw, self.loc(start)).parse()))
                continue
            if c == '}':
                raise self.error('unmatched closing brace')
            if c != '\\':
                if not buf:
                    bufpos = self.i
                buf.append(c)
                self.i += 1
                continue
            flush()
            start = self.i
            name = self.command()
            if name in ('[', '('):
                result.append(self.math(r'\]' if name == '[' else r'\)', name == '[', start))
                continue
            if name in (']', ')'):
                raise self.error(f'unexpected closing math delimiter \\{name}')
            if name == 'begin':
                self.ws()
                env = self.group_raw('{', '}').strip()
                opt = self.optional() if env in VERBATIM | TABLES else None
                if env in TABLES:
                    self.ws()
                    # tabularx has width and columns arguments; others only columns.
                    if env == 'tabularx':
                        self.group_raw('{', '}')
                        self.ws()
                    self.group_raw('{', '}')
                if env in VERBATIM | TABLES:
                    result.append(self.raw_environment(env, start, opt))
                else:
                    child = self.parse(until_env=env)
                    result.append(Node('env', env, self.loc(start), children=child))
                continue
            if name == 'end':
                self.ws()
                env = self.group_raw('{', '}').strip()
                if env == until_env:
                    return result
                raise self.error(f'unexpected \\end{{{env}}}; expected {until_env or "no end"}')
            if name == '\\':
                result.append(Node('break', '', self.loc(start)))
                continue
            if name == 'fancyhead':
                # Running heads are print-only. Consume both location and
                # formatted content rather than leaking them into Markdown.
                self.optional()
                self.argument()
                result.append(Node('macro', name, self.loc(start)))
                continue
            if name == 'printbibliography':
                self.optional()  # References are rendered from cited .bib IDs.
                result.append(Node('macro', name, self.loc(start)))
                continue
            if name == 'titleformat':
                # This is TeX layout code, *not* chapter content. A macro
                # reference such as {\chapter} must not consume a title arg.
                self.ws()
                self.group_raw('{', '}')
                self.optional()
                for _ in range(4):
                    self.ws()
                    self.group_raw('{', '}')
                result.append(Node('macro', name, self.loc(start)))
                continue
            if name in {'lstinputlisting', 'includegraphics'}:
                opt = self.optional()
                result.append(Node('macro', name, self.loc(start), args=[self.argument()], option=opt))
                continue
            base = name[:-1] if name.endswith('*') else name
            opt = self.optional() if base in {'chapter', 'section', 'subsection', 'subsubsection'} else None
            args = [self.argument() for _ in range(ARGS.get(base, 0))]
            result.append(Node('macro', name, self.loc(start), args=args, option=opt))
        if until_env is not None:
            raise self.error(f'missing \\end{{{until_env}}}')
        flush()
        return result


def plain(nodes: list[Node]) -> str:
    """Raw-ish TeX value of a braced argument without losing nested groups."""
    out = []
    for n in nodes:
        if n.kind in {'text', 'raw'}: out.append(n.value)
        elif n.kind == 'group': out.append('{' + plain(n.children) + '}')
        elif n.kind == 'macro': out.append('\\' + n.value + ''.join('{' + plain(a) + '}' for a in n.args))
        elif n.kind.startswith('math'): out.append('$' + n.value + '$')
        elif n.kind == 'break': out.append(r'\\')
        else: raise ParseError(f'{n.location}: cannot flatten {n.kind}')
    return ''.join(out)
