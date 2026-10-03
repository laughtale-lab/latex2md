# Manual-repository integration (phase 3; intentionally not applied yet)

`latex2md` and `diabat-manual` stay separate. There is no Git submodule,
no permanent copy of the converter source under Overleaf, and no converter
checkout from a mutable branch in the Manual's release build.

After the new converter repository is online and its `manual-smoke` and visual
review succeed, tag a reviewed converter commit. Resolve the full, immutable
SHA for that tag. Add these steps to the **existing successful** PDF build
job in the Manual's workflow *after* PDF validation, before staging Pages:

```yaml
- name: Checkout validated latex2md release
  uses: actions/checkout@v4
  with:
    repository: laughtale-lab/latex2md
    # Replace with the reviewed, full (40 hexadecimal) commit SHA.
    ref: <REVIEWED_FULL_COMMIT_SHA>
    path: .ci-tools/latex2md
    persist-credentials: false

- name: Install validated converter
  run: python3 -m pip install .ci-tools/latex2md

- name: Convert all Manual sources, fail on content errors
  run: python3 -m latex2md build --source . --output "$RUNNER_TEMP/diabat-book"

- name: Install the independently tested mdBook version
  uses: taiki-e/install-action@v2
  with:
    tool: mdbook@0.4.52
    fallback: none

- name: Build HTML with no silent fallback
  run: mdbook build "$RUNNER_TEMP/diabat-book"

- name: Audit standalone rendered HTML targets before staging
  run: |
    # The PDF is co-deployed by the Manual repository in the next step.
    latex2md-audit-html \
      --report "$RUNNER_TEMP/diabat-book/conversion-report.json" \
      --html "$RUNNER_TEMP/diabat-book/book" \
      --allow-missing diabat.pdf

- name: Stage PDF and verified HTML together, then audit the final site
  env:
    SITE_SOURCE: ${{ runner.temp }}/diabat-book/book
    SITE_MODE: mdbook
  run: |
    bash tools/stage-pages.sh
    python3 tools/validate-site.py site main.pdf
    latex2md-audit-html \
      --report "$RUNNER_TEMP/diabat-book/conversion-report.json" \
      --html site
```

The existing `tools/stage-pages.sh` copies `main.pdf` as `site/diabat.pdf`
*after* the complete HTML book has built. The Pages upload must occur **only**
after the full PDF/conversion/mdBook/validation pipeline succeeds, preserving
one commit and one live release, with the existing stable URLs unchanged.

Review `.ci-tools/latex2md` as an ignored/ephemeral CI directory; the Manual
repo should not check it in or sync it into Overleaf. Keep CI building on
pull requests without Pages deployment. If the Manual's job uses a TeX
container action, put the Python+mdBook steps on the compatible host, or pass
the verified PDF via an internal workflow artifact to a dependent build job.

**Important:** this snippet is a *phase 3 recipe*, not a change to the
currently operating PDF-only Manual workflow. Do not create a second Pages
workflow in the converter repository.
