"""Embeddings for policy retrieval (Person 2).

Preferred: Sentence Transformers (all-MiniLM-L6-v2). Fallback when the package or model
is unavailable (e.g. offline): a TF-IDF vectoriser fitted on the policy corpus. Both return
L2-normalised vectors so cosine similarity is a dot product.
"""
from __future__ import annotations

import logging

import numpy as np

from config import Settings

log = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.backend = "tfidf"
        self._model = None
        self._vectorizer = None
        wanted = settings.embedding_backend
        if wanted in ("auto", "sentence_transformers"):
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                self._model = SentenceTransformer(settings.embedding_model)
                self.backend = "sentence_transformers"
            except Exception as exc:  # package missing or model download blocked
                if wanted == "sentence_transformers":
                    raise
                log.info("Sentence Transformers unavailable (%s); using TF-IDF embeddings.", exc)

    @property
    def name(self) -> str:
        return self.settings.embedding_model if self.backend == "sentence_transformers" else "tfidf-1-2gram"

    @property
    def min_score(self) -> float:
        """Similarity threshold below which a chunk is not considered evidence."""
        return 0.30 if self.backend == "sentence_transformers" else 0.06

    def fit(self, texts: list[str]) -> None:
        if self.backend == "tfidf":
            from sklearn.feature_extraction.text import TfidfVectorizer

            self._vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1)
            self._vectorizer.fit(texts)

    def embed(self, texts: list[str]) -> np.ndarray:
        if self.backend == "sentence_transformers":
            vecs = np.asarray(self._model.encode(texts, normalize_embeddings=True), dtype=np.float32)
            return vecs
        if self._vectorizer is None:
            raise RuntimeError("TF-IDF embedding service must be fitted on the corpus first.")
        mat = self._vectorizer.transform(texts).toarray().astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    # TF-IDF state must be saved with the index so queries use the same vocabulary.
    def state(self) -> dict:
        return {"backend": self.backend, "vectorizer": self._vectorizer}

    def load_state(self, state: dict) -> None:
        if state.get("backend") == "tfidf":
            self.backend = "tfidf"
            self._vectorizer = state.get("vectorizer")
