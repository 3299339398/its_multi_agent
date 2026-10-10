import logging
from typing import List

from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.config.settings import settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """可选的最终重排器，仅在配置模型后加载。"""

    def __init__(self, model_name: str | None = None, model=None) -> None:
        self.model_name = (
            model_name if model_name is not None else settings.CROSS_ENCODER_MODEL
        )
        self._model = model
        self._load_failed = False

    @property
    def enabled(self) -> bool:
        return bool(self._model is not None or self.model_name)

    def rerank(
        self,
        question: str,
        documents: List[Document],
        top_k: int,
    ) -> List[Document]:
        if not documents or not self.enabled:
            return documents[:top_k]

        model = self._get_model()
        if model is None:
            return documents[:top_k]
        try:
            scores = model.predict(
                [(question, document.page_content) for document in documents]
            )
        except Exception as error:
            logger.warning("Cross-Encoder 精排失败，回退融合排序: %s", error)
            return documents[:top_k]

        ranked = []
        for document, score in zip(documents, scores):
            document.metadata["cross_encoder_score"] = float(score)
            ranked.append((document, float(score)))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return [document for document, _ in ranked[:top_k]]

    def _get_model(self):
        if self._model is not None or self._load_failed:
            return self._model
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.model_name,
                device=settings.CROSS_ENCODER_DEVICE,
            )
        except Exception as error:
            self._load_failed = True
            logger.warning("Cross-Encoder 模型未启用，回退融合排序: %s", error)
        return self._model
