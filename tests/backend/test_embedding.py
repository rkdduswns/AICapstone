
import pytest

from backend.embedding import (
    EMBEDDING_DIMENSION,
    MODEL_NAME,
    EmbeddingService,
)


class FakeVectors(list):
    def __init__(self, values):
        super().__init__(values)
        self.shape = (len(values), EMBEDDING_DIMENSION)


class FakeModel:
    def __init__(self):
        self.received_texts = []
        self.received_kwargs = {}

    def encode(self, texts, **kwargs):
        self.received_texts = texts
        self.received_kwargs = kwargs

        return FakeVectors(
            [[0.01] * EMBEDDING_DIMENSION for _ in texts]
        )


def test_embedding_model_is_loaded_lazily():
    service = EmbeddingService()

    assert service.model_name == MODEL_NAME
    assert service._model is None


def test_embed_passages_adds_passage_prefix():
    service = EmbeddingService()
    fake_model = FakeModel()
    service._model = fake_model

    vectors = service.embed_passages(["ContextTrace 문서 검색"])

    assert fake_model.received_texts == [
        "passage: ContextTrace 문서 검색"
    ]
    assert fake_model.received_kwargs["normalize_embeddings"] is True
    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIMENSION


def test_embed_query_adds_query_prefix():
    service = EmbeddingService()
    fake_model = FakeModel()
    service._model = fake_model

    vector = service.embed_query("문서 검색")

    assert fake_model.received_texts == ["query: 문서 검색"]
    assert len(vector) == EMBEDDING_DIMENSION


def test_embed_passages_returns_empty_list_for_empty_input():
    service = EmbeddingService()

    assert service.embed_passages([]) == []
    assert service._model is None


def test_embed_passages_rejects_empty_text():
    service = EmbeddingService()

    with pytest.raises(ValueError):
        service.embed_passages(["   "])

    assert service._model is None


def test_embed_passages_rejects_non_string_text():
    service = EmbeddingService()

    with pytest.raises(TypeError):
        service.embed_passages([123])

    assert service._model is None


def test_embed_passages_rejects_sensitive_text():
    service = EmbeddingService()

    with pytest.raises(ValueError):
        service.embed_passages(
            ["test@example.com"]
        )

    assert service._model is None
