"""Balanced BibTeX entry reader; only fields used in displayed references matter.
Unknown BibTeX fields are retained, not evaluated as TeX programs.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .parser import ParseError


@dataclass
class Entry:
    key: str
    kind: str
    fields: dict[str, str]


def _block(text: str, start: int, opener: str = '{') -> tuple[str, int]:
    closer = '}' if opener == '{' else ')'
    if text[start] != opener:
        raise ParseError(f'expected {opener} in BibTeX entry')
    depth, in_quote, escaped = 1, False, False
    i = start + 1
    while i < len(text):
        c = text[i]
        if escaped: escaped = False
        elif c == '\\': escaped = True
        elif c == '"': in_quote = not in_quote
        elif not in_quote and c == opener: depth += 1
        elif not in_quote and c == closer:
            depth -= 1
            if not depth: return text[start + 1:i], i + 1
        i += 1
    raise ParseError('unclosed BibTeX entry')


def _split_top(raw: str) -> list[str]:
    out, start, depth, quoted, escaped = [], 0, 0, False, False
    for i, c in enumerate(raw):
        if escaped: escaped = False; continue
        if c == '\\': escaped = True; continue
        if c == '"' and depth == 0: quoted = not quoted
        elif c == '{' and not quoted: depth += 1
        elif c == '}' and not quoted: depth -= 1
        elif c == ',' and depth == 0 and not quoted:
            out.append(raw[start:i]); start = i + 1
    out.append(raw[start:])
    return out


def parse_bib(text: str, source: str) -> dict[str, Entry]:
    result: dict[str, Entry] = {}
    i = 0
    while i < len(text):
        if text[i] != '@': i += 1; continue
        i += 1
        start = i
        while i < len(text) and text[i].isalpha(): i += 1
        kind = text[start:i].lower()
        while i < len(text) and text[i].isspace(): i += 1
        if i == len(text) or text[i] not in '{(': continue
        if kind in {'comment', 'preamble', 'string'}:
            _, i = _block(text, i, text[i]); continue
        raw, i = _block(text, i, text[i])
        parts = _split_top(raw)
        key = parts[0].strip()
        if not key: raise ParseError(f'{source}: blank BibTeX key')
        if key in result: raise ParseError(f'{source}: duplicate BibTeX key {key}')
        fields = {}
        for part in parts[1:]:
            if not part.strip(): continue
            if '=' not in part: raise ParseError(f'{source}: malformed BibTeX field for {key}: {part[:50]}')
            name, value = part.split('=', 1)
            val = value.strip()
            if val.startswith('{') and val.endswith('}') or val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            fields[name.strip().lower()] = val
        result[key] = Entry(key, kind, fields)
    return result


def load_bibs(paths: list[Path]) -> dict[str, Entry]:
    entries: dict[str, Entry] = {}
    for path in paths:
        if not path.is_file(): raise ParseError(f'missing BibTeX file {path}')
        for key, entry in parse_bib(path.read_text(encoding='utf-8', errors='replace'), str(path)).items():
            if key in entries:
                raise ParseError(f'duplicate BibTeX key {key} in {path}')
            entries[key] = entry
    return entries
