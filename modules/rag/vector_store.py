"""Vector storage for policy chunks (Person 2).

ChromaDB is used when installed (VECTOR_BACKEND=auto|chroma); otherwise a small local
NumPy store persisted to disk. Both expose the same `add / query / count / reset` API.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from modules.rag.document_processor import Chunk

log = logging.getLogger(__name__)


class LocalVectorStore:
    backend = "local"

    def __init__(self, folder: Path):
        self.path = Path(folder) / "local_store.pkl"
        self.chunks: list[Chunk] = []
        self.matrix: np.ndarray | None = None
        self.extra: dict[str, Any] = {}

    def reset(self) -> None:
        self.chunks, self.matrix, self.extra = [], None, {}

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        self.chunks.extend(chunks)
        self.matrix = vectors if self.matrix is None else np.vstack([self.matrix, vectors])

    def count(self) -> int:
        return len(self.chunks)

    def query(self, vector: np.ndarray, top_k: int = 4, where: Any = None) -> list[tuple[Chunk, float]]:
        if self.matrix is None or not self.chunks:
            return []
        scores = self.matrix @ vector.reshape(-1)
        order = np.argsort(-scores)
        out = []
        for i in order:
            ch = self.chunks[int(i)]
            if where and not where(ch):
                continue
            out.append((ch, float(scores[int(i)])))
            if len(out) >= top_k:
                break
        return out

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("wb") as fh:
            pickle.dump({"chunks": self.chunks, "matrix": self.matrix, "extra": self.extra}, fh)

    def load(self) -> bool:
        if not self.path.exists():
            return False
        with self.path.open("rb") as fh:  # file is written only by this application
            data = pickle.load(fh)
        self.chunks, self.matrix, self.extra = data["chunks"], data["matrix"], data.get("extra", {})
        return True


class ChromaVectorStore:
    backend = "chroma"

    def __init__(self, folder: Path, collection: str = "policies"):
        import chromadb  # type: ignore

        self._client = chromadb.PersistentClient(path=str(Path(folder) / "chroma"))
        self._name = collection
        self._col = self._client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})
        self.extra: dict[str, Any] = {}
        self._chunks: dict[str, Chunk] = {}
        self._meta_path = Path(folder) / "chroma_chunks.pkl"

    def reset(self) -> None:
        try:
            self._client.delete_collection(self._name)
        except Exception:
            pass
        self._col = self._client.get_or_create_collection(self._name, metadata={"hnsw:space": "cosine"})
        self._chunks = {}

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        self._col.add(ids=[c.chunk_id for c in chunks], embeddings=[v.tolist() for v in vectors],
                      documents=[c.text for c in chunks], metadatas=[c.metadata() for c in chunks])
        self._chunks.update({c.chunk_id: c for c in chunks})

    def count(self) -> int:
        return self._col.count()

    def query(self, vector: np.ndarray, top_k: int = 4, where: Any = None) -> list[tuple[Chunk, float]]:
        res = self._col.query(query_embeddings=[vector.tolist()], n_results=min(max(top_k * 4, 8), max(self.count(), 1)))
        out = []
        for cid, dist in zip(res["ids"][0], res["distances"][0]):
            ch = self._chunks.get(cid)
            if ch is None or (where and not where(ch)):
                continue
            out.append((ch, 1.0 - float(dist)))
            if len(out) >= top_k:
                break
        return out

    def save(self) -> None:
        with self._meta_path.open("wb") as fh:
            pickle.dump({"chunks": self._chunks, "extra": self.extra}, fh)

    def load(self) -> bool:
        if not self._meta_path.exists() or self.count() == 0:
            return False
        with self._meta_path.open("rb") as fh:
            data = pickle.load(fh)
        self._chunks, self.extra = data["chunks"], data.get("extra", {})
        return True


def make_vector_store(backend: str, folder: Path) -> LocalVectorStore | ChromaVectorStore:
    if backend in ("auto", "chroma"):
        try:
            return ChromaVectorStore(folder)
        except Exception as exc:
            if backend == "chroma":
                raise
            log.info("ChromaDB unavailable (%s); using local vector store.", exc)
    return LocalVectorStore(folder)
