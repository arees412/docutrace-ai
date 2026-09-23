# Upstream and license audit

Audit date: 2026-09-22

## Source baseline

- Upstream repository: <https://github.com/docling-project/docling>
- Default branch: `main`
- Audited and inherited commit: `b078ea34921eafe181141e6179e87885196497c3`
- Core source license: MIT, with `LICENSE` preserved byte-for-byte at the audited
  baseline. Audited SHA-256:
  `5548fe5439075583606b3ce553c5c18f2397fb0abf0ad6b9c37dd6db7f137e85`.
- Core copyright notice: `Copyright The Docling Contributors`.
- Python requirement: `>=3.10,<4.0` in `pyproject.toml`.

This derivative must remain a GitHub fork. It does not rewrite upstream history,
remove attribution, or imply endorsement by the Docling maintainers.

## Architecture audited

`DocumentConverter` is the principal conversion entry point. It creates an
`InputDocument`, selects a format backend and pipeline, and returns a
`ConversionResult` containing a `DoclingDocument`. The standard PDF path is a
staged pipeline: preprocessing and PDF parsing, layout analysis, OCR where
configured, layout post-processing, table structure, assembly, reading order,
heading hierarchy, and optional enrichment. The model-free native PDF pipeline
is a separate option with reduced structural behavior.

The upstream API accepts local paths, in-memory streams, and URLs. DocuTrace's
governed adapter accepts validated in-memory bytes only. It does not expose URL
fetching, enables neither remote services nor external plugins, and requires an
explicit local artifacts path before a model-backed PDF profile may run.

## Tests, CI, and security boundaries audited

The inherited repository uses `pytest`, Ruff, ty, Tach, pre-commit hooks, and
separate fast, model-backed, and external-service lanes. Existing CI includes a
trusted-base `pull_request_target` fast-check design. The DocuTrace lane uses no
secrets, network services, paid provider, or model download at test time. Its
fixtures are generated locally and carry an explicit synthetic marker.

Upstream security documentation directs private vulnerability reports through
GitHub Private Vulnerability Reporting or the listed maintainer address. The
DocuTrace threat model and non-claims are documented in
[`docs/security.md`](docs/security.md).

## Model and optional-asset boundaries

The MIT repository license applies to the repository code, not automatically to
every separately downloaded model, OCR weight, tokenizer, dataset, or other
asset. The audit found no model weights copied into this derivative and no
model asset modified by DocuTrace.

The following table records upstream-published license metadata only. The linked
model card or repository remains authoritative at download and use time.

| Optional component | Published boundary observed | DocuTrace treatment |
| --- | --- | --- |
| `docling-models` bundle | CDLA-Permissive-2.0 and Apache-2.0 files | Not copied; user must review per-file terms |
| `docling-ibm-models` code | MIT repository | Not modified |
| `docling-layout-heron` | Apache-2.0 model card/files | Not copied |
| Granite Docling 258M | Apache-2.0 model card | Not copied |
| RapidOCR | Apache-2.0 code; README attributes OCR models separately | Code/model terms must be checked independently |
| EasyOCR | Package metadata reports Apache-2.0 | Not copied; verify downloaded weights separately |
| Tesseract | Apache-2.0; Leptonica has its own BSD-2-Clause terms | External system component only |
| NVIDIA Nemotron OCR v1 | NVIDIA Open Model License metadata | Not copied or enabled in deterministic CI |

Authoritative links:

- <https://huggingface.co/docling-project/docling-models/tree/main>
- <https://github.com/docling-project/docling-ibm-models>
- <https://huggingface.co/docling-project/docling-layout-heron/tree/main>
- <https://huggingface.co/ibm-granite/granite-docling-258M>
- <https://github.com/RapidAI/RapidOCR/blob/main/README.md>
- <https://github.com/JaidedAI/EasyOCR/blob/master/setup.py>
- <https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE>
- <https://huggingface.co/nvidia/nemotron-ocr-v1/tree/main>

No statement above is a legal opinion. Operators are responsible for checking
the current license, acceptable-use terms, export controls, and data terms for
every optional asset they choose to obtain.
