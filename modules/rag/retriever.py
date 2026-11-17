"""Policy index build + retrieval with metadata filtering (Person 2)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from backend.schemas.models import PolicySource, Strategy
from config import Settings
from modules.rag.document_processor import Chunk, chunk_document
from modules.rag.embedding_service import EmbeddingService
from modules.rag.policy_loader import load_policy_documents
from modules.rag.vector_store import make_vector_store

log = logging.getLogger(__name__)


class PolicyRetriever:
    def __init__(self, settings: Settings, kb_dir: Path | None = None, store_dir: Path | None = None):
        self.settings = settings
        self.kb_dir = Path(kb_dir or settings.knowledge_base_dir / "policies")
        self.store_dir = Path(store_dir or settings.vector_store_dir)
        self.embedder = EmbeddingService(settings)
        self.store = make_vector_store(settings.vector_backend, self.store_dir)
        self.docs = []
        self._ensure_index()

    # ------------------------------------------------------------------ indexing
    def _ensure_index(self) -> None:
        docs = load_policy_documents(self.kb_dir)
        fingerprint = {d.doc_id: d.sha256 for d in docs}
        if self.store.load() and self.store.extra.get("fingerprint") == fingerprint \
                and self.store.extra.get("embedder") == self.embedder.name:
            self.embedder.load_state(self.store.extra.get("embedding_state", {}))
            self.docs = docs
            return
        self.build(docs)

    def build(self, docs=None) -> dict[str, Any]:
        docs = docs or load_policy_documents(self.kb_dir)
        chunks: list[Chunk] = [c for d in docs for c in chunk_document(d)]
        texts = [c.text for c in chunks]
        self.embedder.fit(texts)
        vectors = self.embedder.embed(texts)
        self.store.reset()
        self.store.add(chunks, vectors)
        self.store.extra = {
            "fingerprint": {d.doc_id: d.sha256 for d in docs},
            "embedder": self.embedder.name,
            "embedding_state": self.embedder.state(),
            "versions": {d.doc_id: d.version for d in docs},
        }
        self.store.save()
        self.docs = docs
        log.info("Indexed %s chunks from %s policy documents", len(chunks), len(docs))
        return {"documents": len(docs), "chunks": len(chunks), "embedder": self.embedder.name,
                "vector_store": self.store.backend,
                "suspicious_chunks": [c.chunk_id for c in chunks if c.suspicious]}

    # ------------------------------------------------------------------ retrieval
    def retrieve(self, query: str, top_k: int = 4, segments: Iterable[str] | None = None,
                 doc_ids: Iterable[str] | None = None, min_score: float | None = None) -> list[PolicySource]:
        seg_filter = set(segments or [])
        doc_filter = set(doc_ids or [])
        current = self.store.extra.get("versions", {})

        def where(ch: Chunk) -> bool:
            if current and current.get(ch.doc_id) not in (None, ch.version):
                return False  # only current policy versions
            if doc_filter and ch.doc_id not in doc_filter:
                return False
            if seg_filter and not (seg_filter & set(ch.segments) or "ALL" in ch.segments):
                return False
            return True

        vec = self.embedder.embed([query])[0]
        threshold = self.embedder.min_score if min_score is None else min_score
        hits = self.store.query(vec, top_k=top_k, where=where)
        return [
            PolicySource(doc_id=ch.doc_id, doc_name=ch.doc_name, section=ch.section, version=ch.version,
                         excerpt=ch.text.split("\n", 1)[-1][:600], score=round(score, 4))
            for ch, score in hits if score >= threshold
        ]

    def retrieve_for_strategy(self, strategy: Strategy, top_k: int = 3) -> list[PolicySource]:
        """Soft guidance for the writer: tone, wording and required-content rules."""
        parts = [strategy.objective or "", (strategy.tone or "").lower(), "tone", "email", "guidance"]
        if strategy.objective == "REMIND":
            parts += ["payment reminder stage", str(strategy.reminder_stage), "required content dispute"]
        if strategy.offer:
            parts += ["offer", strategy.offer.name, "terms expiry"]
        segs = [strategy.primary_segment] if strategy.primary_segment else None
        return self.retrieve(" ".join(parts), top_k=top_k, segments=segs, min_score=0.0)

    def stats(self) -> dict[str, Any]:
        return {"documents": len(self.docs), "chunks": self.store.count(), "embedder": self.embedder.name,
                "vector_store": self.store.backend}
