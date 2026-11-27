"""Windows 배포본에서 공식 E5 ONNX와 토크나이저를 로컬 CPU로 실행한다."""

from pathlib import Path


class PackagedE5:
    """기존 EmbeddingService의 접두어·민감정보 검사·토큰 분할을 그대로 사용한다."""

    max_seq_length = 512

    def __init__(self, directory: Path):
        """가중치는 EXE 옆 모델 폴더에서 읽으며 사용자 질의나 원문은 전송하지 않는다."""
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self._tokenizer.no_truncation()
        self._tokenizer.no_padding()
        self.session = ort.InferenceSession(str(directory / "model.onnx"), providers=["CPUExecutionProvider"])

    def tokenizer(self, text, add_special_tokens=True, return_offsets_mapping=False):
        """원문 분할용 오프셋과 접두어를 포함한 정확한 토큰 수를 반환한다."""
        encoding = self._tokenizer.encode(text, add_special_tokens=add_special_tokens)
        result = {"input_ids": encoding.ids}
        if return_offsets_mapping:
            result["offset_mapping"] = encoding.offsets
        return result

    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True):
        """공식 E5 평균 풀링과 L2 정규화를 적용한다. 한 문장씩 처리해 패딩을 피한다."""
        import numpy as np

        vectors = []
        inputs = {x.name for x in self.session.get_inputs()}
        for text in texts:
            encoding = self._tokenizer.encode(text)
            ids = np.asarray([encoding.ids], dtype=np.int64)
            if ids.shape[1] > self.max_seq_length:
                raise ValueError("E5 token limit exceeded")
            feed = {"input_ids": ids, "attention_mask": np.ones_like(ids)}
            if "token_type_ids" in inputs:
                feed["token_type_ids"] = np.asarray([encoding.type_ids], dtype=np.int64)
            hidden = self.session.run(["last_hidden_state"], feed)[0]
            vector = hidden[0].mean(axis=0)
            vectors.append(vector / np.linalg.norm(vector))
        return np.stack(vectors)
