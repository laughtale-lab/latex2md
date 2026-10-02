# Structural design and extension contract

The public Manual is a documented **subset of LaTeX**, not an arbitrary TeX
program. Broad regex-based replacement or blind Pandoc conversion cannot
preserve its nine-field `\keyword`, cross-reference semantics, or escaped
listing captions reliably. Accordingly the converter includes a small,
explicit, balanced reader (`parser.py`) with environment-aware verbatim
handling, semantic adapters (`converter.py`), and a balanced BibTeX reader
(`bib.py`). Regex is used only for local, narrowly defined syntax such as the
`@...@` listing markers and terminal reference-link auditing.

## Source and passes

1. Find the document body in `main.tex` and recursively expand `\input` and
   `\include` through root-confined paths. Exclude only TeX-specific cover and
   generated table of contents; incorporate cover artwork into the welcome
   page instead. Reject cyclic includes and missing sources.
2. Walk the parsed tree to register chapter/section identifiers, `\keyword`
   labels, Script and Example caption IDs, bibliography citation order, and
   the resources that need to be copied. Labels store destination filename,
   displayed number and semantic kind.
3. Render a per-chapter Markdown file and explicit link targets, including
   the dedicated appendix index and bibliography. `\keyword` becomes a
   legible field table and `\keyitem` is linked to its true detailed entry.
   Math is passed through to MathJax; print-only spacing is explicitly skipped.
4. Copy original runnable input *files* from the `examples/release`,
   `examples/tutorials`, `examples/templates` trees into download paths,
   **without** treating annotated `.lst` content as original inputs.
5. Verify that every registered source label appears as a destination anchor,
   that local targets exist, that copied assets are present, and that a
   complete `SUMMARY.md` and `book.toml` exist. Emit JSON diagnostics.
6. Work in a temporary build directory. Move it to the user-supplied output
   path only when conversion, all resource checks and link audits succeed.
   A failed conversion never overwrites an existing output tree.

This is fail-closed on **active content commands**, but it does not attempt to
model TeX pagination, floating placements, font families, box formatting or
full user macro evaluation. That boundary is intentional: web typography is
not print typography. Every new *semantic* TeX command must have an adapter,
plus a fixture and an integration test.

## Link rules

For a label such as `key-fphd-refid`, a table contains
`<a id="key-fphd-refid"></a>`. Cross-chapter references use a relative page
path and fragment, e.g. `diabatization.md#key-fphd-refid`; same-page references
use `#key-fphd-refid`. `\script{chap-diabat}{script-fphd-job}` validates both
chapter and caption and formats `Script 4-1` from source counters.
Bibliography entries are numbered in first-citation order, and have stable
`cite-<slug>` anchors independent of that temporary numbering.

## Palette

`diabat.css` + `diabat-highlight.js` are injected via the generated `book.toml`:
blue block `$` markers, purple-pink job/block names, red strings, light green
comments, and gray Script/Example captions. The JS registers a Highlight.js
language when supported and safely falls back to DOM text-node highlighting
for unfamiliar mdBook/highlighter combinations; it never evaluates scripts
from example input.

## Scope of the initial audited revision

The supplied source contains 7 main chapters and 4 appendices; 74 keyword
entries, 106 overview items, 18 numbered Script captions, 26 numbered Example
captions, 25 source `.lst` inclusions, and 41 output-file descriptions. The
reviewed metrics are in `diabat-2.0-baseline.json`, which must be revised when
the Manual changes intentionally. The corresponding report is emitted with
**every** conversion and should be saved with CI test artifacts.

## Known boundaries and intentional follow-up

- This candidate is validated against the uploaded 2.0 LaTeX snapshot; the
  online `diabat-manual/main` may differ and requires its own independent CI run.
- Full HTML/browser appearance and math/highlighter behavior must be inspected
  using pinned mdBook and a real browser before the converter is called stable.
- The current print-only `frontmatter/links.tex` still has an outdated online
  URL placeholder. The converter retains that source prose and adds a working
  *generated landing page* and canonical PDF link. Update the print Manual
  content in the Manual's own future editorial revision if desired.
- A future upstream port can replace this bounded parser with an established
  LaTeX AST library without changing the semantic adapter, link registry, CLI
  or output contract. Avoid changing the Manual merely to suit a converter.
