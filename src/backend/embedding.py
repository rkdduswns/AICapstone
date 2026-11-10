
"""Semantic embedding generation for ContextTrace search."""

import math

from backend.privacy import PrivacyPolicy

MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSION = 384


class EmbeddingService:
    """Generate normalized semantic embeddings using multilingual E5."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        """Load the embedding model only when it is first needed."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self.model_name,
                device="cpu",
            )

        return self._model

    def _encode(
        self,
        texts: list[str],
        prefix: str,
        privacy_policy: PrivacyPolicy | None = None,
    ) -> list[list[float]]:
        """Encode texts and return normalized embedding vectors."""
        if not isinstance(texts, list):
            raise TypeError("texts must be a list")

        policy = privacy_policy or PrivacyPolicy()

        for text in texts:
            if not isinstance(text, str):
                raise TypeError("each text must be a string")

            if not text.strip():
                raise ValueError("text must not be empty")

            if policy.contains_sensitive_data(text):
                raise ValueError("text contains sensitive information")

        if not texts:
            return []

        model = self._load_model()
        vectors = model.encode(
            [f"{prefix}: {text}" for text in texts],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

        if vectors.shape != (len(texts), EMBEDDING_DIMENSION):
            raise ValueError("unexpected embedding dimensions")

        results = []

        for vector in vectors:
            values = [float(value) for value in vector]

            if not all(math.isfinite(value) for value in values):
                raise ValueError("embedding contains non-finite values")

            results.append(values)

        return results

    def embed_passages(
        self,
        texts: list[str],
        privacy_policy: PrivacyPolicy | None = None,
    ) -> list[list[float]]:
        """Generate embeddings for document or web passages."""
        return self._encode(texts, "passage", privacy_policy)

    def embed_query(
        self,
        text: str,
        privacy_policy: PrivacyPolicy | None = None,
    ) -> list[float]:
        """Generate an embedding for a search query."""
        return self._encode([text], "query", privacy_policy)[0]
