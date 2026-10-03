# Structural design and rendered-target contract

The public Manual is a documented **subset of LaTeX**, not an arbitrary TeX
program. `latex2md` therefore uses an explicit balanced reader and semantic
adapters rather than broad whole-document regular-expression substitution.
The Manual LaTeX remains the only editable documentation source.

## Conversion passes

1. Read `main.tex`, recursively expand root-confined `\input`/`\include`, and
   reject missing files, cycles and path escapes.
2. Before numbering, structurally bind a heading label only when `\label{...}`
   follows a chapter/section/subsection heading with nothing except whitespace
   between them. This exact parsed-node relationship is recorded; title text is
   never used to infer a label later.
3. Register every semantic target with its page, displayed number, kind, source
   location and render contract. Current target kinds are chapter, section,
   subsection, standalone, appendix, keyword, Script, Example and citation.
4. Render heading-bound labels using mdBook heading attributes, for example:

   ```markdown
   ### 2.2.1 Standard output and error output { #sec-stdout }
   ```

   mdBook 0.4.52 documents heading attributes as the mechanism for stable custom
   heading HTML IDs. The explicit LaTeX label therefore remains stable even if
   the visible heading wording changes.
5. Render non-heading targets as explicit HTML `<div id="...">` elements.
   Script/Example IDs live directly on their gray `.listing-caption` elements;
   keyword, standalone and bibliography targets use `.target-anchor` blocks.
6. Generate per-chapter Markdown, `SUMMARY.md`, `book.toml`, copied assets and
   byte-identical original example inputs. Run a source-level Markdown audit.
7. Write `conversion-report.json`, including both the backwards-compatible
   `labels` table and a complete `targets` table that also contains citation
   anchors. A failed conversion never replaces an existing output directory.
8. Disable mdBook's concatenated `print.html` (`[output.html.print] enable = false`)
   so converter-owned IDs occur only on their canonical chapter pages.
9. **After mdBook renders**, run `latex2md-audit-html`. Rendered HTML is the final
   publication contract, not Markdown text.

## Rendered HTML audit

`latex2md-audit-html` parses the actual mdBook output with Python's HTML parser.
For every registered target it requires:

- the expected `.html` page exists;
- the target `id` occurs exactly once on that page and exactly once across the
  rendered site for converter-owned target IDs;
- chapter/section/subsection targets are on `h1`/`h2`/`h3` (and the matching
  deeper heading level if later used);
- Script/Example targets are `<div class="listing-caption" ...>` elements;
- other raw targets are `<div>` elements;
- every rendered local link/resource resolves to a real file;
- every local HTML fragment resolves exactly once.

External network URLs are outside this offline audit. `diabat.pdf` is explicitly
allowed to be absent only in standalone `latex2md` CI because the PDF is
co-deployed later by the Manual repository; production Manual integration must
run the auditor again after PDF + HTML staging without this exception.

## Numbering and link rules

The converter preserves separate Script and Example counters and validates the
chapter supplied by `\script{...}{...}` / `\example{...}{...}`. Cross-page
Markdown links use `.md#label`; mdBook converts the page suffix to `.html`.
Citations receive stable `cite-<slug>` targets independent of their temporary
first-citation display number.

## Strictness boundary

Print-only pagination, float placement, fonts and box layout are intentionally
not reproduced. Unknown semantic macros, duplicate IDs, malformed labels,
missing resources, unresolved references or a target lost by mdBook are errors.
New semantic LaTeX constructs require parser/renderer handling, unit tests and,
when they affect links/targets, a real mdBook fixture regression.

## Fixed renderer

The compatibility target is **mdBook 0.4.52**. CI verifies `mdbook --version`
exactly before rendering. Deliberate mdBook upgrades require a separate review
of the fixture, complete Manual HTML audit and browser appearance before the
production Manual changes its pinned version.
