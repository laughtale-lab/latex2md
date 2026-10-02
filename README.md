# latex2md — structured LaTeX → mdBook conversion

[![MIT licensed](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

`latex2md` is a standalone, **fail-closed** Python converter for the current
[Diabat User Manual](https://github.com/laughtale-lab/diabat-manual). It generates
mdBook-compatible Markdown from the Manual's existing LaTeX without modifying
any LaTeX macros, chapter sources, artwork, example files, or print layout.
The Manual's LaTeX repository remains its **only editable document source**.

> **Release status:** `0.1.3` candidate. Verified locally against the supplied
> Diabat 2.0 LaTeX snapshot. Review the independent repository's GitHub Actions
> smoke test against its *current* public Manual before tagging a stable release.
> This repository alone does **not** publish the official Manual website.

## Install and run

Python **3.11+**; **no third-party runtime Python dependencies**. Use a
virtual environment if you prefer:

```bash
python -m pip install .
latex2md --version
latex2md build --source ../diabat-manual --output /tmp/diabat-book
# Optional preview; use tested mdBook 0.4.52 for now:
mdbook build /tmp/diabat-book
mdbook serve /tmp/diabat-book --open
```

The output directory must be empty or absent. The command exits nonzero with
its source location when a required file, known macro, cross-reference or
bibliography entry is missing or inconsistent. The generated output remains
**unpublished** until the independent Manual's Actions verifies all stages.

The generated mdBook project contains:

```text
/tmp/diabat-book/
  book.toml
  conversion-report.json
  src/
    README.md                  # HTML welcome page; refers to /diabat-manual/diabat.pdf
    SUMMARY.md                 # automatic chapter and appendix navigation
    *.md                       # generated, never manually edited
    references.md              # bibliography entries actually cited
    example-inputs.md          # download index for original .inp / .gjf
    assets/                    # source-verified cover and content artwork
    downloads/examples/        # copied original inputs, byte-for-byte
    diabat.css                 # manual's semantic palette
    diabat-highlight.js        # custom script language highlighting
```

The rendered website is only a **preview** until phase 3 integrates mdBook
into `diabat-manual`'s single PDF+HTML GitHub Pages release. The `diabat.pdf`
link deliberately targets the root of that future combined published site.

## What is supported

- Nested `\input`/`\include` and the original chapter/appendix organization.
- Nested LaTeX groups and in-text/display math with MathJax-compatible output.
- Chapter/section numbering; `\label`, `\ref`, `\Sec`,
  `\script`, `\example`, and `\keyref` link targets across chapters.
- Nine-field `\keyword` tables and `\keyitem` overview links.
- Separate Script and Example counters, including `@...@` escape markers
  in both inline listings and included **presentation-only `.lst` files**.
- Original `.inp`/`.gjf` inputs copied separately from display files.
  **Not all copied inputs can run without additional calculation data.**
- Technical tables, ordered/unordered lists, inline formatting, hyperlinks,
  bibliography entries and cited-only reference numbering.
- Script theme CSS and JavaScript highlighting: blue `$`, pink-purple job/
  block names, red strings, light green comments, gray caption numbers.
- mdBook-native `{#id}` headings for all labeled chapters/sections/appendices,
  plus preserved stable IDs for keywords, Script/Example captions and citations.
  `latex2md.html_audit` verifies every label in the **rendered HTML**, not just
  in the intermediate Markdown. No Manual-repository anchor-rewrite step.
- Two-pass registration; explicit errors for unsupported active markup,
  duplicate/unresolved IDs, invalid source paths and missing resources.

**Scope:** This is a purpose-built structural parser and a small collection of
explicit adapters, not a full TeX interpreter or a drop-in converter for
arbitrary LaTeX projects. The source compatibility contract and extension
points are documented in [DESIGN.md](docs/DESIGN.md). Notably, print styling
commands are explicitly ignored; they are not reimplemented for the web.
Future macros need their own parser spec, renderer handler and regression test.

## Test and audit

```bash
python -m unittest discover -s tests -v
latex2md build --source /path/to/Diabat-manual --output /tmp/clean-book
latex2md-verify --report /tmp/clean-book/conversion-report.json \
  --baseline docs/diabat-2.0-baseline.json
mdbook build /tmp/clean-book
python -m latex2md.html_audit --book /tmp/clean-book
```

The frozen baseline corresponds to the supplied 2.0 LaTeX **snapshot**, not
a universal requirement for future revised Manuals. Update that baseline only
after reviewing the content change. This repo's CI also runs integration and
HTML preview against the public Manual's current `main` without publishing it.

See [DESIGN](docs/DESIGN.md), [VALIDATION](docs/VALIDATION.md),
[Manual integration instructions](docs/INTEGRATION.md), and the
[Chinese quickstart](docs/README.zh-CN.md).

## License

`latex2md` source code: **MIT** (see [LICENSE](LICENSE)). The Diabat Manual
text and Manual assets remain governed by their **separate** CC BY 4.0 and
third-party notices. This repository contains tests only, not a forked or
separately maintained copy of the Manual.
