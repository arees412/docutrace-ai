# DocuTrace derivative changes

DocuTrace AI is a substantial, opt-in derivative layer on the inherited Docling
conversion architecture. It is not an upstream rename and does not replace or
hide the Docling APIs.

## Added capability

- Fail-closed local ingestion with extension/MIME agreement, byte/page limits,
  encrypted-PDF rejection, safe Office-container checks, and macro/active-content
  rejection.
- Explicit processing profiles and an adapter over `DocumentConverter` that
  disables remote services and external plugins and blocks implicit model
  downloads.
- Deterministic evidence-backed classification and versioned sample invoice and
  contract extraction schemas.
- Typed normalization, field and cross-field validators, confidence states,
  human-review routing, and correction records that retain the original value.
- Table normalization with typed cells, merged-cell awareness, and row-level
  provenance.
- Citation anchors that are checked against document, page, element, text span,
  and bounding box.
- Configurable privacy detection and redaction, sensitive-context exclusion, and
  an explicit disabled-by-default external-provider boundary.
- RAG-ready, section-aware chunks with source element IDs and citation anchors;
  no vector database is prescribed.
- Metadata-only tamper-evident audit events, provenance fingerprints,
  idempotency, bounded retry classification, lifecycle events, and operational
  metrics.
- Deterministic golden evaluation, more than thirty focused regression tests,
  two end-to-end fixtures, a local CLI, and a dedicated CI workflow.

## Deliberate non-capabilities

DocuTrace does not claim certified extraction accuracy, regulatory compliance,
customer adoption, production volume, model ownership, malware detection, or a
complete sandbox. It does not execute document macros or scripts, follow
document URLs, upload documents, or enable a paid/external extraction provider.

## Attribution and maintenance

Inherited files retain their original copyright and SPDX notices. New DocuTrace
files use the MIT license and identify their new-file copyright. The root
`LICENSE` is preserved. Upstream history and fork relationship are required;
updates should be merged from the `upstream` remote without rebasing away or
squashing inherited history.
