
"""Tests for the local Ollama answer generator."""

import json
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import pytest

from backend.ollama_answer_generator import OllamaAnswerGenerator
from shared.rag import RAGEvidence


def make_evidence() -> list[RAGEvidence]:
    """Create sample evidence for generation tests."""
    return [
        RAGEvidence(
            id="chunk-1",
            source_kind="web",
            title="ContextTrace 소개",
            text="ContextTrace는 작업 기록을 검색하는 시스템이다.",
            similarity=0.92,
            chunk_index=0,
            captured_at="2026-11-19T10:00:00+09:00",
            url="https://example.com/article",
        )
    ]


def make_ollama_response(
    answer: str = "ContextTrace는 작업 기록 검색 시스템입니다.",
    evidence_ids: list[str] | None = None,
) -> bytes:
    """Build a valid Ollama chat response."""
    generated = {
        "answer": answer,
        "evidence_ids": (
            ["chunk-1"] if evidence_ids is None else evidence_ids
        ),
    }

    response = {
        "message": {
            "content": json.dumps(
                generated,
                ensure_ascii=False,
            )
        }
    }

    return json.dumps(response).encode("utf-8")


def make_mock_response(content: bytes) -> Mock:
    """Create a mock HTTP response context manager."""
    response = Mock()
    response.read.return_value = content
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


def test_default_configuration() -> None:
    """The generator uses the configured local defaults."""
    generator = OllamaAnswerGenerator()

    assert generator.base_url == "http://127.0.0.1:11434"
    assert generator.model == "qwen2.5:3b"
    assert generator.timeout == 120


def test_external_server_url_is_rejected() -> None:
    """The generator must not send evidence to external servers."""
    with pytest.raises(ValueError, match="local loopback"):
        OllamaAnswerGenerator(
            base_url="https://example.com"
        )


@pytest.mark.parametrize(
    "timeout",
    [0, -1, True, 1.5],
)
def test_invalid_timeout_is_rejected(timeout) -> None:
    """Timeout must be a positive integer."""
    with pytest.raises(ValueError, match="timeout"):
        OllamaAnswerGenerator(timeout=timeout)


def test_empty_model_is_rejected() -> None:
    """The model name must not be empty."""
    with pytest.raises(ValueError, match="model"):
        OllamaAnswerGenerator(model="   ")


def test_empty_query_is_rejected() -> None:
    """An empty query must not trigger an HTTP request."""
    generator = OllamaAnswerGenerator()

    with patch(
        "backend.ollama_answer_generator.urlopen"
    ) as mocked_urlopen:
        with pytest.raises(ValueError, match="query"):
            generator.generate("", make_evidence())

    mocked_urlopen.assert_not_called()


def test_no_evidence_does_not_call_ollama() -> None:
    """An empty evidence list returns an insufficient answer locally."""
    generator = OllamaAnswerGenerator()

    with patch(
        "backend.ollama_answer_generator.urlopen"
    ) as mocked_urlopen:
        result = generator.generate(
            "ContextTrace는 무엇인가?",
            [],
        )

    assert result.evidence_ids == []
    assert result.text
    mocked_urlopen.assert_not_called()


def test_generate_sends_local_request_and_parses_answer() -> None:
    """A valid Ollama response becomes a structured RAG answer."""
    generator = OllamaAnswerGenerator()

    response = make_mock_response(
        make_ollama_response()
    )

    with patch(
        "backend.ollama_answer_generator.urlopen",
        return_value=response,
    ) as mocked_urlopen:
        result = generator.generate(
            "ContextTrace는 무엇인가?",
            make_evidence(),
        )

    assert result.text == "ContextTrace는 작업 기록 검색 시스템입니다."
    assert result.evidence_ids == ["chunk-1"]

    mocked_urlopen.assert_called_once()

    request = mocked_urlopen.call_args.args[0]
    timeout = mocked_urlopen.call_args.kwargs["timeout"]

    assert request.full_url == (
        "http://127.0.0.1:11434/api/chat"
    )
    assert request.method == "POST"
    assert timeout == 120

    payload = json.loads(request.data.decode("utf-8"))

    assert payload["model"] == "qwen2.5:3b"
    assert payload["stream"] is False
    assert payload["format"] == "json"
    assert payload["options"]["temperature"] == 0.1

    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"

    user_payload = json.loads(
        payload["messages"][1]["content"]
    )

    assert user_payload["question"] == "ContextTrace는 무엇인가?"
    assert user_payload["evidence"][0]["id"] == "chunk-1"


def test_http_error_is_converted_to_runtime_error() -> None:
    """HTTP failures are reported as Ollama runtime errors."""
    generator = OllamaAnswerGenerator()

    error = HTTPError(
        url="http://127.0.0.1:11434/api/chat",
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=None,
    )

    with patch(
        "backend.ollama_answer_generator.urlopen",
        side_effect=error,
    ):
        with pytest.raises(RuntimeError, match="HTTP 500"):
            generator.generate(
                "질문",
                make_evidence(),
            )


def test_connection_error_is_converted_to_runtime_error() -> None:
    """Connection failures are reported without leaking evidence."""
    generator = OllamaAnswerGenerator()

    with patch(
        "backend.ollama_answer_generator.urlopen",
        side_effect=URLError("connection refused"),
    ):
        with pytest.raises(
            RuntimeError,
            match="Unable to connect",
        ):
            generator.generate(
                "질문",
                make_evidence(),
            )


def test_invalid_http_json_is_rejected() -> None:
    """Malformed HTTP response JSON is rejected."""
    generator = OllamaAnswerGenerator()

    response = make_mock_response(b"not-json")

    with patch(
        "backend.ollama_answer_generator.urlopen",
        return_value=response,
    ):
        with pytest.raises(
            RuntimeError,
            match="invalid response",
        ):
            generator.generate(
                "질문",
                make_evidence(),
            )


def test_invalid_generated_json_is_rejected() -> None:
    """Malformed generated answer JSON is rejected."""
    generator = OllamaAnswerGenerator()

    response_body = json.dumps(
        {
            "message": {
                "content": "not-json",
            }
        }
    ).encode("utf-8")

    response = make_mock_response(response_body)

    with patch(
        "backend.ollama_answer_generator.urlopen",
        return_value=response,
    ):
        with pytest.raises(
            RuntimeError,
            match="invalid answer structure",
        ):
            generator.generate(
                "질문",
                make_evidence(),
            )


def test_empty_generated_answer_is_rejected() -> None:
    """An empty generated answer is invalid."""
    generator = OllamaAnswerGenerator()

    response = make_mock_response(
        make_ollama_response(answer="   ")
    )

    with patch(
        "backend.ollama_answer_generator.urlopen",
        return_value=response,
    ):
        with pytest.raises(
            RuntimeError,
            match="empty answer",
        ):
            generator.generate(
                "질문",
                make_evidence(),
            )

def test_invalid_evidence_references_are_rejected() -> None:
    """Evidence references must be a list of strings."""
    generator = OllamaAnswerGenerator()

    response = make_mock_response(
        make_ollama_response(
            evidence_ids=["chunk-1", 123]
        )
    )

    with patch(
        "backend.ollama_answer_generator.urlopen",
        return_value=response,
    ):
        with pytest.raises(
            RuntimeError,
            match="must be strings",
        ):
            generator.generate(
                "질문",
                make_evidence(),
            )


def test_missing_evidence_references_are_rejected() -> None:
    """The generated response must contain evidence_ids as a list."""
    generator = OllamaAnswerGenerator()

    response_body = json.dumps(
        {
            "message": {
                "content": json.dumps(
                    {"answer": "답변"}
                )
            }
        }
    ).encode("utf-8")

    response = make_mock_response(response_body)

    with patch(
        "backend.ollama_answer_generator.urlopen",
        return_value=response,
    ):
        with pytest.raises(
            RuntimeError,
            match="invalid evidence references",
        ):
            generator.generate(
                "질문",
                make_evidence(),
            )

@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1.evil.example:11434",
        "http://localhost.evil.example:11434",
        "http://user@127.0.0.1:11434",
        "http://127.0.0.1:11434/api",
        "https://127.0.0.1:11434",
        "http://[::1",
    ],
)
def test_rejects_non_loopback_or_invalid_urls(base_url):
    with pytest.raises(
        ValueError,
        match="local loopback address",
    ):
        OllamaAnswerGenerator(base_url=base_url)