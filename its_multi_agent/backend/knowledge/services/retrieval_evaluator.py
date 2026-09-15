from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence

from langchain_core.documents import Document


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    question: str
    relevant_ids: Sequence[str]
    knowledge_space: str = "default"
    domain: str = "general"


@dataclass(frozen=True)
class RetrievalMetrics:
    case_count: int
    recall_at_k: float
    hit_rate_at_k: float
    mean_reciprocal_rank: float


def evaluate_retrieval(
    retrieve: Callable[[RetrievalEvaluationCase], List[Document]],
    cases: Iterable[RetrievalEvaluationCase],
    top_k: int = 5,
) -> RetrievalMetrics:
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")

    case_list = list(cases)
    if not case_list:
        return RetrievalMetrics(0, 0.0, 0.0, 0.0)

    recall_total = 0.0
    hit_total = 0
    reciprocal_rank_total = 0.0
    for case in case_list:
        relevant = set(case.relevant_ids)
        if not relevant:
            raise ValueError(f"evaluation case has no relevant ids: {case.question}")
        retrieved_ids = [_document_id(document) for document in retrieve(case)[:top_k]]
        matched = relevant.intersection(retrieved_ids)
        recall_total += len(matched) / len(relevant)
        hit_total += int(bool(matched))
        for rank, document_id in enumerate(retrieved_ids, start=1):
            if document_id in relevant:
                reciprocal_rank_total += 1.0 / rank
                break

    count = len(case_list)
    return RetrievalMetrics(
        case_count=count,
        recall_at_k=recall_total / count,
        hit_rate_at_k=hit_total / count,
        mean_reciprocal_rank=reciprocal_rank_total / count,
    )


def _document_id(document: Document) -> str:
    return str(
        document.metadata.get("source_id")
        or document.metadata.get("parent_id")
        or document.metadata.get("document_hash")
        or document.metadata.get("source_name")
        or document.metadata.get("title")
        or ""
    )
