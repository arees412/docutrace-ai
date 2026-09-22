# SPDX-FileCopyrightText: 2026 Arees Shah
# SPDX-License-Identifier: MIT

"""Repository-policy checks for the deterministic DocuTrace CI lane."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DOCS = (
    ROOT / "UPSTREAM.md",
    ROOT / "FORK_CHANGES.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "security.md",
    ROOT / "docs" / "development.md",
)
EXPECTED_LICENSE_SHA256 = (
    "5548fe5439075583606b3ce553c5c18f2397fb0abf0ad6b9c37dd6db7f137e85"
)
MODEL_SUFFIXES = {".bin", ".ckpt", ".onnx", ".pt", ".pth", ".safetensors"}
SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
)
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def _check_local_links(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for target in MARKDOWN_LINK.findall(text):
        clean = target.split("#", maxsplit=1)[0]
        if not clean or "://" in clean or clean.startswith("mailto:"):
            continue
        resolved = (path.parent / clean).resolve()
        if not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: missing local link {target}")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED_DOCS:
        if not path.is_file() or path.stat().st_size < 200:
            errors.append(f"required documentation is missing or empty: {path}")
            continue
        errors.extend(_check_local_links(path))

    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    if architecture.count("```mermaid") != 1 or architecture.count("```") % 2:
        errors.append("architecture Mermaid block is missing or unbalanced")

    license_bytes = (ROOT / "LICENSE").read_bytes()
    if hashlib.sha256(license_bytes).hexdigest() != EXPECTED_LICENSE_SHA256:
        errors.append("root LICENSE differs from the audited upstream license")
    if b"Copyright The Docling Contributors" not in license_bytes:
        errors.append("upstream copyright notice is missing")

    for path in (ROOT / "docling" / "docutrace").rglob("*"):
        if path.is_file() and path.suffix.casefold() in MODEL_SUFFIXES:
            errors.append(f"model asset is not allowed in DocuTrace source: {path}")

    scan_roots = (
        ROOT / "docling" / "docutrace",
        ROOT / "tests" / "docutrace",
        *REQUIRED_DOCS,
    )
    for scan_root in scan_roots:
        paths = scan_root.rglob("*.py") if scan_root.is_dir() else (scan_root,)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    errors.append(f"possible credential in {path.relative_to(ROOT)}")

    upstream = (ROOT / "UPSTREAM.md").read_text(encoding="utf-8")
    for required in (
        "docling-project/docling",
        "b078ea34921eafe181141e6179e87885196497c3",
        "Copyright The Docling Contributors",
    ):
        if required not in upstream:
            errors.append(f"UPSTREAM.md is missing attribution token: {required}")

    if errors:
        print("DocuTrace policy checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("DocuTrace policy checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
