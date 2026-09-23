# SPDX-FileCopyrightText: The Docling Contributors
# SPDX-License-Identifier: MIT

# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Local-only command line interface for one governed document run."""

from __future__ import annotations

import argparse
from pathlib import Path

from docling.docutrace.adapters import DeterministicFixtureParser, DoclingParserAdapter
from docling.docutrace.exports import result_to_json
from docling.docutrace.ingestion import load_local_file
from docling.docutrace.pipeline import DocuTracePipeline, PipelineConfig


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m docling.docutrace")
    parser.add_argument("input", type=Path)
    parser.add_argument("--profile", default="fast")
    parser.add_argument("--schema")
    parser.add_argument("--artifacts-path", type=Path)
    parser.add_argument("--fixture-parser", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    path = args.input.resolve(strict=True)
    data = load_local_file(path, allowed_root=path.parent)
    adapter = (
        DeterministicFixtureParser()
        if args.fixture_parser
        else DoclingParserAdapter(artifacts_path=args.artifacts_path)
    )
    pipeline = DocuTracePipeline(
        parser=adapter,
        config=PipelineConfig(parser_profile=args.profile),
    )
    result = pipeline.process(path.name, data, schema_id=args.schema)
    print(result_to_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
