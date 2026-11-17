"""Chunk policy documents by section and neutralise embedded instructions (Person 2).

Retrieved documents are untrusted content: lines that try to instruct the model
("ignore previous instructions", "you are now ...") are removed before indexing and the
chunk is flagged, so a poisoned document cannot override system rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from modules.rag.policy_loader import PolicyDocument

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)",
    r"disregard (all |any )?(previous|prior|above|the) ",
    r"you are now",
    r"system prompt",
    r"override (the )?(policy|rules|validator)",
    r"approve (this|all) (message|email|draft)s? automatically",
    r"do not (validate|check)",
]
_INJ = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_name: str
    section: str
    version: str
    segments: list[str]
    text: str
    suspicious: bool = False
    removed_lines: list[str] = field(default_factory=list)

    def metadata(self) -> dict[str, Any]:
        return {"doc_id": self.doc_id, "doc_name": self.doc_name, "section": self.section,
                "version": self.version, "segments": ",".join(self.segments), "suspicious": self.suspicious}


def sanitize(text: str) -> tuple[str, list[str]]:
    kept, removed = [], []
    for line in text.splitlines():
        (removed if _INJ.search(line) else kept).append(line)
    return "\n".join(kept).strip(), removed


def chunk_document(doc: PolicyDocument, max_chars: int = 1200) -> list[Chunk]:
    """One chunk per '## ' section; very long sections are split on paragraph boundaries."""
    sections: list[tuple[str, str]] = []
    current_title, buf = "Overview", []
    for line in doc.text.splitlines():
        if line.startswith("## "):
            if "".join(buf).strip():
                sections.append((current_title, "\n".join(buf)))
            current_title, buf = line[3:].strip(), []
        elif line.startswith("> SYNTHETIC"):
            continue  # disclaimer is kept in the document, not repeated in every chunk
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append((current_title, "\n".join(buf)))

    chunks: list[Chunk] = []
    for idx, (title, body) in enumerate(sections):
        clean, removed = sanitize(body)
        parts = [clean] if len(clean) <= max_chars else _split(clean, max_chars)
        for j, part in enumerate(parts):
            if not part.strip():
                continue
            chunks.append(Chunk(
                chunk_id=f"{doc.doc_id}::{idx}.{j}", doc_id=doc.doc_id, doc_name=doc.title, section=title,
                version=doc.version, segments=doc.segments,
                text=f"{doc.title} - {title}\n{part.strip()}", suspicious=bool(removed), removed_lines=removed,
            ))
    return chunks


def _split(text: str, max_chars: int) -> list[str]:
    out, buf = [], ""
    for para in re.split(r"\n\s*\n|(?<=\.)\s+", text):
        if len(buf) + len(para) + 1 > max_chars and buf:
            out.append(buf)
            buf = para
        else:
            buf = f"{buf} {para}".strip()
    if buf:
        out.append(buf)
    return out
