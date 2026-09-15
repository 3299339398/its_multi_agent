import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List

import jieba
from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.config.settings import settings


class LexicalIndexRepository:
    """Persistent Chinese BM25 index backed by SQLite FTS5."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = Path(db_path or settings.LEXICAL_INDEX_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def replace_document(
        self,
        document_hash: str,
        documents: List[Document],
        knowledge_space: str,
        domain: str,
    ) -> int:
        parents = {}
        for document in documents:
            parent_id = str(document.metadata.get("parent_id", ""))
            parent_content = str(document.metadata.get("parent_content", ""))
            if not parent_id or not parent_content or parent_id in parents:
                continue
            metadata = dict(document.metadata)
            metadata.pop("parent_content", None)
            parents[parent_id] = (parent_content, metadata)

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM lexical_chunks WHERE document_hash = ?",
                (document_hash,),
            )
            connection.executemany(
                """
                INSERT INTO lexical_chunks(
                    parent_id, document_hash, knowledge_space, domain,
                    tokens, content, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        parent_id,
                        document_hash,
                        knowledge_space,
                        domain,
                        self._tokenize(content),
                        content,
                        json.dumps(metadata, ensure_ascii=False, default=str),
                    )
                    for parent_id, (content, metadata) in parents.items()
                ],
            )
        return len(parents)

    def search(
        self,
        query: str,
        knowledge_space: str = "default",
        domain: str = "general",
        top_k: int | None = None,
    ) -> List[Document]:
        terms = self._query_terms(query)
        if not terms:
            return []
        match_expression = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT parent_id, content, metadata_json, bm25(lexical_chunks) AS bm25_score
                FROM lexical_chunks
                WHERE lexical_chunks MATCH ?
                  AND knowledge_space = ?
                  AND domain = ?
                ORDER BY bm25_score
                LIMIT ?
                """,
                (
                    match_expression,
                    knowledge_space,
                    domain,
                    top_k or settings.BM25_TOP_K,
                ),
            ).fetchall()

        documents = []
        for rank, row in enumerate(rows, start=1):
            metadata = json.loads(row["metadata_json"] or "{}")
            metadata.update({
                "parent_id": row["parent_id"],
                "retrieval_channel": "bm25",
                "bm25_rank": rank,
                "bm25_score": float(row["bm25_score"]),
            })
            documents.append(Document(page_content=row["content"], metadata=metadata))
        return documents

    def delete_document(self, document_hash: str) -> int:
        with self._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM lexical_chunks WHERE document_hash = ?",
                (document_hash,),
            ).fetchone()[0]
            connection.execute(
                "DELETE FROM lexical_chunks WHERE document_hash = ?",
                (document_hash,),
            )
        return int(count)

    @staticmethod
    def _tokenize(text: str) -> str:
        return " ".join(LexicalIndexRepository._terms(text))

    @staticmethod
    def _query_terms(text: str) -> List[str]:
        terms = []
        for term in LexicalIndexRepository._terms(text):
            if term not in terms:
                terms.append(term)
        return terms[: settings.BM25_MAX_QUERY_TERMS]

    @staticmethod
    def _terms(text: str) -> List[str]:
        normalized = text.lower()
        terms = [
            token.strip()
            for token in jieba.lcut(normalized)
            if token.strip() and re.search(r"[\w\u4e00-\u9fff]", token)
        ]
        terms.extend(
            match.lower()
            for match in re.findall(r"[A-Za-z]+[-_.]?\d+[A-Za-z0-9_.-]*|\d{3,}", text)
        )
        return terms

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS lexical_chunks USING fts5(
                    parent_id UNINDEXED,
                    document_hash UNINDEXED,
                    knowledge_space UNINDEXED,
                    domain UNINDEXED,
                    tokens,
                    content UNINDEXED,
                    metadata_json UNINDEXED,
                    tokenize = 'unicode61'
                )
                """
            )
