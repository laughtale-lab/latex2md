# Changelog

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
