# DocuTrace development

## Environment

DocuTrace follows the inherited requirement of Python 3.10 or later and uses the
repository's locked `uv` environment.

```bash
uv sync --frozen --only-group dev
```

The deterministic test lane downloads no model weights and calls no external or
paid service.

## Focused checks

```bash
uv run ruff format --check docling/docutrace tests/docutrace scripts/docutrace_ci_check.py
uv run ruff check docling/docutrace tests/docutrace scripts/docutrace_ci_check.py
uv run ty check docling/docutrace
uv run python -m pytest -q tests/docutrace
uv run tach check
uv run python scripts/docutrace_ci_check.py
uv run python -c "import docling.docutrace"
```

The repository-wide checks remain authoritative for inherited code:

```bash
make validate
make check
```

## Local CLI

Use a reviewed local file. The default `fast` profile avoids model-backed PDF
stages. Model-backed profiles require an explicit local artifacts directory.

```bash
uv run python -m docling.docutrace ./document.pdf --profile fast
uv run python -m docling.docutrace ./document.pdf \
  --profile balanced --artifacts-path ./reviewed-model-artifacts
```

Do not pass a URL. JSON is written to standard output so the caller controls
storage and retention.

## Adding schemas and providers

Schemas are versioned `ExtractionSchema` values. Mark examples as samples,
declare types and required fields, attach aliases, and add deterministic field
and cross-field tests. Every non-null extracted value must retain evidence that
resolves to the same document/page/element/text/bounding-box tuple.

External providers require a new adapter; changing `enabled` alone is
insufficient. Add privacy-context tests, output-schema tests, timeout and retry
tests, documentation for data transfer and retention, and an operator-visible
opt-in. Never put provider credentials in source, fixtures, logs, or audit data.

## Pull requests

Keep changes in coherent commits, retain upstream attribution and the root
license, and do not add model weights. A DocuTrace pull request should include
the focused check output, model/asset review, new security assumptions, and an
explicit statement that the PR remains unmerged until reviewed.
