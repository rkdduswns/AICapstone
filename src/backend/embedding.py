
"""ContextTrace 검색용 의미 임베딩 생성 기능."""

import math
from threading import RLock

from backend.privacy import PrivacyPolicy

MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSION = 384

# 모델의 최대 입력 토큰 길이.
DEFAULT_MAX_SEQUENCE_LENGTH = 512

# 특수 토큰 및 접두어 길이를 고려한 여유분.
TOKEN_SAFETY_MARGIN = 8


class EmbeddingService:
    """multilingual E5 모델을 사용해 정규화된 임베딩을 생성한다."""

    def __init__(
        self,
        model_name: str = MODEL_NAME,
    ) -> None:
        self.model_name = model_name
        self._model = None
        self._model_lock = RLock()

    def _load_model(self):
        """최초 요청 시에만 임베딩 모델을 로드한다."""
        # 의미 검색과 RAG가 동시에 들어와도 큰 모델을 두 번 로드하지 않는다.
        with self._model_lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name, device="cpu")

        return self._model

    def _get_tokenizer(self):
        """SentenceTransformer 모델의 토크나이저를 반환한다."""
        model = self._load_model()

        tokenizer = getattr(model, "tokenizer", None)

        if tokenizer is None:
            raise RuntimeError(
                "The embedding model does not expose a tokenizer."
            )

        return tokenizer

    @property
    def max_sequence_length(self) -> int:
        """현재 모델이 지원하는 최대 입력 토큰 수를 반환한다."""
        model = self._load_model()

        max_length = getattr(
            model,
            "max_seq_length",
            DEFAULT_MAX_SEQUENCE_LENGTH,
        )

        if (
            isinstance(max_length, bool)
            or not isinstance(max_length, int)
            or max_length < 1
        ):
            return DEFAULT_MAX_SEQUENCE_LENGTH

        return max_length

    def _tokenize(
        self,
        text: str,
        add_special_tokens: bool = False,
    ):
        """텍스트를 토큰 ID로 변환한다."""
        tokenizer = self._get_tokenizer()

        return tokenizer(
            text,
            add_special_tokens=add_special_tokens,
        )

    def count_tokens(
        self,
        text: str,
        prefix: str = "passage",
    ) -> int:
        """E5 접두어를 포함한 입력 토큰 수를 계산한다."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        if not text.strip():
            raise ValueError("text must not be empty")

        encoded = self._tokenize(
            f"{prefix}: {text}",
            add_special_tokens=True,
        )

        return len(encoded["input_ids"])

    def split_passage(
        self,
        text: str,
        privacy_policy: PrivacyPolicy | None = None,
    ) -> list[str]:
        """긴 문서를 모델 입력 토큰 제한에 맞춰 분할한다.

        토크나이저의 offset_mapping을 이용해 원문 문자 위치를
        기준으로 자르므로 토큰을 decode하면서 발생할 수 있는
        공백이나 문장 형태의 변형을 최소화한다.
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        if not text.strip():
            return []

        policy = privacy_policy or PrivacyPolicy()

        if policy.contains_sensitive_data(text):
            raise ValueError(
                "text contains sensitive information"
            )

        tokenizer = self._get_tokenizer()

        max_tokens = (
            self.max_sequence_length - TOKEN_SAFETY_MARGIN
        )

        if max_tokens < 1:
            raise ValueError(
                "Model sequence length is too small."
            )

        # passage 접두어가 차지하는 토큰 수를 제외한다.
        prefix_tokens = tokenizer(
            "passage: ",
            add_special_tokens=True,
        )["input_ids"]

        token_budget = max_tokens - len(prefix_tokens)

        if token_budget < 1:
            raise ValueError(
                "Insufficient token budget for passage text."
            )

        encoded = tokenizer(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True,
        )

        offsets = encoded.get("offset_mapping")

        if offsets is None:
            raise RuntimeError(
                "Tokenizer must support offset_mapping."
            )

        parts: list[str] = []
        start = 0
        token_count = 0

        for token_start, token_end in offsets:
            # 특수 처리 토큰 등 실제 문자 범위가 없는 항목은 건너뛴다.
            if token_start == token_end:
                continue

            if token_count >= token_budget:
                part = text[start:token_start].strip()

                if part:
                    parts.append(part)

                start = token_start
                token_count = 0

            token_count += 1

        final_part = text[start:].strip()

        if final_part:
            parts.append(final_part)

        return parts

    def _validate_texts(
        self,
        texts: list[str],
        privacy_policy: PrivacyPolicy | None = None,
    ) -> None:
        """임베딩 입력값과 개인정보를 검사한다."""
        if not isinstance(texts, list):
            raise TypeError("texts must be a list")

        policy = privacy_policy or PrivacyPolicy()

        for text in texts:
            if not isinstance(text, str):
                raise TypeError(
                    "each text must be a string"
                )

            if not text.strip():
                raise ValueError(
                    "text must not be empty"
                )

            if policy.contains_sensitive_data(text):
                raise ValueError(
                    "text contains sensitive information"
                )

    def _encode(
        self,
        texts: list[str],
        prefix: str,
        privacy_policy: PrivacyPolicy | None = None,
    ) -> list[list[float]]:
        """텍스트를 임베딩 벡터로 변환한다."""
        self._validate_texts(
            texts,
            privacy_policy=privacy_policy,
        )

        if not texts:
            return []

        model = self._load_model()

        # 실제 모델에서는 토큰 초과 입력을 미리 차단한다.
        # 테스트용 FakeModel처럼 tokenizer가 없는 모델은
        # 토큰 길이 검사를 생략한다.
        if getattr(model, "tokenizer", None) is not None:
            for text in texts:
                token_count = self.count_tokens(
                    text,
                    prefix=prefix,
                )

                if token_count > self.max_sequence_length:
                    raise ValueError(
                        "Text exceeds the model token limit. "
                        "Split the passage before embedding."
                    )

        vectors = model.encode(
            [f"{prefix}: {text}" for text in texts],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

        if vectors.shape != (
            len(texts),
            EMBEDDING_DIMENSION,
        ):
            raise ValueError(
                "unexpected embedding dimensions"
            )

        results: list[list[float]] = []

        for vector in vectors:
            values = [
                float(value)
                for value in vector
            ]

            if not all(
                math.isfinite(value)
                for value in values
            ):
                raise ValueError(
                    "embedding contains non-finite values"
                )

            results.append(values)

        return results

    def embed_passages(
        self,
        texts: list[str],
        privacy_policy: PrivacyPolicy | None = None,
    ) -> list[list[float]]:
        """웹 페이지 및 문서의 검색 청크를 임베딩한다."""
        return self._encode(
            texts,
            "passage",
            privacy_policy,
        )

    def embed_query(
        self,
        text: str,
        privacy_policy: PrivacyPolicy | None = None,
    ) -> list[float]:
        """사용자 검색 질의를 임베딩한다."""
        return self._encode(
            [text],
            "query",
            privacy_policy,
        )[0]
