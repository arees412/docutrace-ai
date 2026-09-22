# DocuTrace security and privacy

This document describes implemented controls and residual risk. It is not a
compliance certification, legal opinion, malware scanner, or claim that arbitrary
documents are safe.

## Trust boundary

Documents are untrusted. The governed API accepts explicit local bytes after
the caller has chosen the file. It does not accept or follow URLs. It does not
execute macros, scripts, embedded programs, or document-provided commands.
Macro-enabled Office extensions and active-content members are rejected.

Ingestion verifies a conservative extension/MIME match, maximum byte and page
counts, PDF encryption markers, Office container identity, member count,
uncompressed size, compression ratio, traversal names, and active-content
markers. These checks reduce risk but do not prove a file benign. Run production
conversion with OS/container isolation, resource quotas, patched dependencies,
and least privilege.

## Parser and model boundary

The Docling adapter uses an in-memory stream, passes byte/page limits, disables
remote services, and disables external plugins. A model-backed PDF profile fails
closed unless an operator supplies a local artifacts directory. This prevents
an implicit first-run model download through DocuTrace. Model files are not
vendored, modified, or covered by the core MIT license merely because they are
used by Docling. See [`UPSTREAM.md`](../UPSTREAM.md).

## Sensitive data

The privacy module detects selected email, phone, payment-card-like, and
credential-like patterns. Sensitive chunks are excluded and explicitly marked
fields are redacted in exports by default. Pattern matching can have false
positives and false negatives; deployments handling regulated or high-risk data
need domain-specific detection, retention, access, deletion, and incident
controls.

Audit events record identifiers, hashes, counts, statuses, and component names.
Keys suggesting raw document bytes, content, passwords, secrets, or tokens are
replaced with `[OMITTED]`. Raw source bytes remain in the in-memory result object
for the caller and must not be logged.

## Prompt injection and external providers

Document text is data, never an instruction channel. The deterministic provider
does not invoke an LLM. The external-provider boundary is disabled and has no
implementation. Any future implementation must use explicit opt-in, minimized
and redacted context, strict structured outputs, evidence validation, bounded
timeouts/retries, vendor retention review, and no tool execution driven by
document text.

## Known residual risks

- MIME sniffing and Office checks are not complete file-format validation.
- PDF page counting at ingestion is conservative; the parser remains
  authoritative after conversion.
- A parsing dependency may contain vulnerabilities or consume excessive CPU or
  memory before a cooperative timeout is observed.
- Regex privacy detection is not sufficient for every identifier or locale.
- Audit hashes make in-process tampering evident but are not signatures and do
  not provide external immutable storage.

Use the inherited private disclosure process in [`.github/SECURITY.md`](../.github/SECURITY.md)
for vulnerabilities. Do not include private documents, credentials, or exploit
details in a public issue.
