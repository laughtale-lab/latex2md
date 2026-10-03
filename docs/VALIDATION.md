# Verification and release gates

A source conversion that exits successfully is necessary but not sufficient.
The release contract is the HTML produced by the fixed mdBook renderer. The generated
book disables mdBook's concatenated print page so registered IDs remain unique across
canonical HTML pages.

## Local/unit gates

```bash
python -m compileall -q src tests
python -m unittest discover -s tests -v
latex2md build --source /path/to/diabat-manual --output /tmp/diabat-book
latex2md-verify \
  --report /tmp/diabat-book/conversion-report.json \
  --baseline docs/diabat-2.0-baseline.json
```

Unit tests cover balanced parsing, heading binding, native heading attributes,
standalone targets, Script/Example numbering, keyword/citation targets, broken
references, duplicates, missing files, path confinement, accents and the HTML
auditor's fail-closed behavior.

## Mandatory real mdBook 0.4.52 gates

The GitHub Actions workflow has two independent renderer checks after Python
unit tests:

1. **`mdbook-fixture`** converts `tests/fixtures/mdbook-manual`, confirms
   `mdbook v0.4.52`, renders the two-chapter fixture, and runs
   `latex2md-audit-html` against the real generated HTML. The fixture exercises
   native chapter/section/subsection IDs, a cross-page reference, keyword,
   standalone target, Script, Example and bibliography citation.
2. **`manual-smoke`** checks out the public `diabat-manual` current `main`, runs
   the reviewed content baseline, renders the entire generated book with the
   same mdBook 0.4.52, and runs the same final HTML target/link/resource audit.
   The complete rendered preview is uploaded as an artifact for visual review.

A new tag must **not** be created unless both jobs pass. The final browser review
must additionally inspect navigation, search, MathJax, code highlighting,
Script/Example captions, keyword jumps, bibliography and example downloads.

## Manual-repository production gate

When a converter release is later integrated into `diabat-manual`, the Manual
repository must pin its **full reviewed converter commit SHA**, compile/validate
PDF first, build Markdown and mdBook second, then run the rendered HTML auditor
on the final staged site **without** exempting `diabat.pdf`. Pages deployment is
allowed only after all stages succeed, so a failed conversion/audit leaves the
previous successful website live.
