# Changelog

## 0.2.0 — rendered HTML target contract (candidate, 2026-10-03)

- Bind LaTeX labels that structurally follow chapter/section/subsection headings
  to mdBook native heading attributes (`{ #label }`) instead of separate anchors.
- Distinguish chapter, section, subsection, standalone, keyword, Script, Example,
  appendix and bibliography targets in `conversion-report.json`.
- Render non-heading targets as explicit stable HTML `<div id=...>` elements while
  preserving gray Script/Example caption semantics.
- Add `latex2md-audit-html`, which treats rendered mdBook HTML as the publication
  contract and requires every registered target to occur exactly once on the
  expected page, with correct heading/caption element semantics.
- Audit all local rendered links, fragments and resources; broken or duplicate
  targets fail the build.
- Add a minimal two-chapter LaTeX fixture and a CI job that runs the real pinned
  mdBook 0.4.52 renderer before auditing its HTML.
- Extend the full Manual CI job to run the same real mdBook 0.4.52 HTML audit.
- Preserve the existing Manual source baseline and all LaTeX input/layout rules.

**Release gate:** do not tag this candidate until both the real mdBook fixture job
and the complete current Manual mdBook/HTML audit pass in GitHub Actions.

## 0.1.2 — diaeresis and conversion-report version fix (candidate)

- Treat `\"o` and `\"{o}` as TeX accent commands rather than literal quotes.
- Add parser and end-to-end regression tests for accented Manual prose and keyword tables.
- Fail on unsupported diaeresis letters instead of silently losing markup.
- Report the actual installed package version in `conversion-report.json`.
- No changes to the existing Manual LaTeX source or the link/numbering model.

## 0.1.1 — CI syntax hotfix (2026-10-02)

- Fixed invalid nested quoting in the bibliography URL fallback under Python 3.11.
- Added regression tests for bibliography URLs and rejected URL schemes.
- Run syntax compilation before Python unit tests in each supported CI version.
- No changes to LaTeX source format or converter output for documents that use DOI references.

## 0.1.0 — initial candidate (2026-10-01)

- Added a standalone structured, dependency-free Python content parser.
- Implemented Diabat-specific keyword table and overview transformations,
  separate numbered Script and Example caption handling, citations,
  bibliography, links and math.
- Added automatic mdBook project generation, CSS and script highlighter,
  and source-backed download links for original input files.
- Added strict converter failures, per-conversion JSON reports, frozen 2.0
  source audit baseline, CI unit tests and an independent Manual smoke job.
- This is a release **candidate** until GitHub CI and browser/mdBook inspection
  run against the currently published Manual repository.
