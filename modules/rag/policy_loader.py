"""Load policy documents (Markdown with YAML front matter) from the knowledge base (Person 2)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PolicyDocument:
    doc_id: str
    title: str
    version: str
    segments: list[str]
    path: str
    text: str
    sha256: str
    meta: dict[str, Any] = field(default_factory=dict)


def parse_front_matter(raw: str) -> tuple[dict[str, Any], str]:
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            return yaml.safe_load(parts[1]) or {}, parts[2].lstrip("\n")
    return {}, raw


def load_policy_documents(folder: Path | str) -> list[PolicyDocument]:
    docs: list[PolicyDocument] = []
    for path in sorted(Path(folder).glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = parse_front_matter(raw)
        docs.append(PolicyDocument(
            doc_id=str(meta.get("doc_id", path.stem)),
            title=str(meta.get("title", path.stem.replace("_", " ").title())),
            version=str(meta.get("version", "1.0")),
            segments=[str(s) for s in (meta.get("segments") or ["ALL"])],
            path=str(path),
            text=body,
            sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            meta=meta,
        ))
    return docs
