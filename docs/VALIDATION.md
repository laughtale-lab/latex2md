# Verification and release gates

## Offline checks on the provided 2.0 Manual snapshot

- Parser, bibliography, deterministic output, broken reference, duplicate ID,
  missing input, path confinement, and atomic failure are tested in
  `tests/test_parser.py` and `tests/test_converter.py`.
- The CLI's full-manual conversion was exercised on the original uploaded
  **156-member** LaTeX source archive (not a fabricated stripped test case).
- Conversion reports an independent index of labels/citations and a list of
  source files read, so reviewers can see exactly which source revision was
  processed. `docs/diabat-2.0-baseline.json` records reviewed counts.
- The preview outputs must be regarded as generated artifacts; do not copy
  edited Markdown back into the Manual repository.

## Online tests to run before tagging a stable converter

1. Push this repository to a new public `laughtale-lab/latex2md` repository;
   Actions are read-only by default. Review the `tests` matrix on supported
   Python 3.11, 3.12 and 3.13.
2. Review `manual-smoke`: it checks out the real public Manual's current `main`,
   generates Markdown and invokes **mdBook 0.4.52**. No output is published by
   this repository's workflow; its artifact is review material only.
3. Inspect the generated HTML manually, especially the FPHD keyword links,
   Appendix references, math display, all 68 code blocks, Script/Example
   numbering, DOI links, downloadable original `.inp` files, and the custom
   syntax highlighter with search working.
4. Tag a reviewed converter SHA (for example `v0.1.0`) only after all tests
   pass. The Manual build must check out that **full commit SHA**. Upgrades
   go through PR review + full PDF/Markdown/mdBook regression and single
   Pages deployment. Do not track the converter's moving `main` in production.

The local sandbox used to prepare the initial package had Python, Pandoc,
Node.js and the original manual, but did **not** contain an mdBook executable
or network package installer. Hence no local claim is made that a real mdBook
HTML build or browser rendering has already passed; the Actions job checks
that separately when the repository is available online.


## Rendered HTML anchor gate

A successful Markdown source audit alone does not prove that mdBook preserved
any raw HTML anchors. After running the pinned mdBook builder (0.4.52), run:

```bash
python -m latex2md.html_audit --book /path/to/generated-book
```

This independent gate verifies each label in `conversion-report.json` and each
cited bibliography ID occurs exactly once in the appropriate generated HTML
page. Missing pages, lost heading IDs and duplicate targets fail CI. It runs in
the independent converter's `manual-smoke` GitHub Actions job. The separate
Manual repository should also audit final link destinations and PDF identity.
