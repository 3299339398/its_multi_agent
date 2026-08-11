import hashlib
import json
import logging
import re
from typing import List

from langchain_core.documents import Document
from langchain_openai.embeddings import OpenAIEmbeddings

from its_multi_agent.backend.knowledge.config.settings import settings

try:
    from langchain_milvus import Milvus
except ImportError:  # Compatibility with older local environments.
    from langchain_community.vectorstores import Milvus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VectorStoreRepository:
    """
    作用，对向量数据库做场景读写
    """

    def __init__(self, embedding=None, vector_database=None):
        """
        创建向量数据库实例
        创建嵌入模型的实例
        向量数据库能力，1 存储向量数据 2 搜索能力 （向量数据库检索器）
        """
        if vector_database is not None:
            self.embedding = embedding
            self.vector_database = vector_database
            self._vector_databases = {settings.MILVUS_COLLECTION: vector_database}
            self._uses_external_database = True
            return

        self.embedding = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.API_KEY,
            openai_api_base=settings.BASE_URL
        )

        connection_args = {"uri": settings.MILVUS_URI}
        if settings.MILVUS_TOKEN:
            connection_args["token"] = settings.MILVUS_TOKEN
        self._connection_args = connection_args
        self._uses_external_database = False
        self.vector_database = self._create_vector_database(settings.MILVUS_COLLECTION)
        self._vector_databases = {settings.MILVUS_COLLECTION: self.vector_database}

    def _create_vector_database(self, collection_name: str):
        return Milvus(
            connection_args=self._connection_args,
            collection_name=collection_name,
            embedding_function=self.embedding,
        )

    def _database_for_scope(self, knowledge_space: str, domain: str):
        collection_name = self.scope_collection_name(knowledge_space, domain)
        if self._uses_external_database:
            return self.vector_database
        if collection_name not in self._vector_databases:
            self._vector_databases[collection_name] = self._create_vector_database(collection_name)
        return self._vector_databases[collection_name]

    @staticmethod
    def scope_collection_name(knowledge_space: str, domain: str) -> str:
        if not settings.SCOPE_COLLECTIONS_ENABLED or (
            knowledge_space == "default" and domain == "general"
        ):
            return settings.MILVUS_COLLECTION

        scope = f"{knowledge_space}\0{domain}"
        digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:16]
        base = re.sub(r"[^A-Za-z0-9_]", "_", settings.MILVUS_COLLECTION)[:220]
        if not base or not re.match(r"^[A-Za-z_]", base):
            base = f"kb_{base}"
        return f"{base}_scope_{digest}"

    def add_documents(
        self,
        documents: List[Document],
        batch_size: int = 16,
        knowledge_space: str = "default",
        domain: str = "general",
    ) -> int:
        """
        将切分之后的文档块添加到向量数据库当中
        Args:
            document: 切分之后的文档块
            batch: 分批保存文档块的大小

        Returns:
            int:成功添加到向量数据库中文档块的数量
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        total_documents_chunks = len(documents)
        if total_documents_chunks == 0:
            return 0

        document_ids = [
            self._document_id(document, index)
            for index, document in enumerate(documents)
        ]
        for document, document_id in zip(documents, document_ids):
            document.metadata["vector_id"] = document_id

        vector_database = self._database_for_scope(knowledge_space, domain)

        # Remove remnants from an interrupted previous attempt before inserting.
        self._delete_ids(vector_database, document_ids, reason="写入前清理")
        documents_chunks_added = 0
        try:
            for i in range(0, total_documents_chunks, batch_size):
                batch = documents[i:i + batch_size]
                batch_ids = document_ids[i:i + batch_size]
                vector_database.add_documents(batch, ids=batch_ids)
                documents_chunks_added += len(batch)
                logger.info(f"成功保存: {documents_chunks_added}/{total_documents_chunks}")
            return documents_chunks_added
        except Exception:
            cleaned = self._delete_ids(vector_database, document_ids, reason="失败补偿")
            if cleaned:
                logger.exception("文档向量写入失败，已删除本次文档的全部向量")
            else:
                logger.exception("文档向量写入失败，补偿删除未完成")
            raise

    def _delete_ids(self, vector_database, document_ids: List[str], reason: str) -> bool:
        try:
            vector_database.delete(ids=document_ids)
            return True
        except Exception as error:
            # A collection may not exist before the first insertion. In that case
            # the subsequent insert creates it; insertion errors are still surfaced.
            logger.debug("Milvus %s未完成: %s", reason, error)
            return False

    def delete_document(
        self,
        document_hash: str,
        knowledge_space: str = "default",
        domain: str = "general",
    ) -> None:
        vector_database = self._database_for_scope(knowledge_space, domain)
        escaped_hash = document_hash.replace("\\", "\\\\").replace('"', '\\"')
        vector_database.delete(expr=f'document_hash == "{escaped_hash}"')

    @staticmethod
    def _document_id(document: Document, position: int) -> str:
        metadata = document.metadata
        identity = {
            "document_hash": metadata.get("document_hash", ""),
            "parent_id": metadata.get("parent_id", ""),
            "child_index": metadata.get("child_index", ""),
            "position": position,
            "content_hash": hashlib.sha256(
                document.page_content.encode("utf-8")
            ).hexdigest(),
        }
        raw = json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


    def embed_document(self, text: str) -> List[float]:
        """
        对query进行向量化
        Args:
            text:输入文本

        Returns:
            List[float]:嵌入后的浮点数列表
        """
        return self.embedding.embed_query(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        对字符串进行向量化
        Args:
            text:输入文本

        Returns:
            List[float]:嵌入后的浮点数列表
        """
        return self.embedding.embed_documents(texts)

    # Backward compatibility for callers outside this repository.
    embedd_documents = embed_documents

    def search_similarity_with_score(
        self,
        user_question: str,
        top_k: int | None = None,
        knowledge_space: str = "default",
        domain: str = "general",
    ) -> List[tuple[Document, float]]:
        """
        相似性检索文档分数
        Args:
            user_question:

        Returns:
            返回基于向量检索的相似性文档列表
        """
        limit = top_k or settings.VECTOR_CHILD_TOP_K
        scoped_database = self._database_for_scope(knowledge_space, domain)
        results = scoped_database.similarity_search_with_score(user_question, limit)
        results = [
            item for item in results
            if self.document_matches_scope(item[0], knowledge_space, domain)
        ]

        is_default_scope = knowledge_space == "default" and domain == "general"
        if (
            not is_default_scope
            and settings.LEGACY_SCOPE_FALLBACK_ENABLED
            and len(results) < limit
        ):
            legacy_results = self.vector_database.similarity_search_with_score(
                user_question,
                max(limit, settings.LEGACY_SCOPE_FALLBACK_TOP_K),
            )
            seen = {self._result_key(document) for document, _ in results}
            for document, score in legacy_results:
                key = self._result_key(document)
                if key in seen or not self.document_matches_scope(
                    document, knowledge_space, domain
                ):
                    continue
                results.append((document, score))
                seen.add(key)
                if len(results) >= limit:
                    break
        return results[:limit]

    @staticmethod
    def document_matches_scope(
        document: Document,
        knowledge_space: str,
        domain: str,
    ) -> bool:
        content = document.page_content or ""
        parent_content = str(document.metadata.get("parent_content", ""))
        searchable = f"{content}\n{parent_content}"
        space_match = re.search(r"(?:^|\n)知识空间:([^\n]+)", searchable)
        domain_match = re.search(r"(?:^|\n)知识领域:([^\n]+)", searchable)

        # Documents ingested before scoped knowledge existed belong to the
        # backward-compatible default/general collection.
        actual_space = space_match.group(1).strip() if space_match else "default"
        actual_domain = domain_match.group(1).strip() if domain_match else "general"
        return actual_space == knowledge_space and actual_domain == domain

    @staticmethod
    def _result_key(document: Document):
        return document.metadata.get("vector_id") or document.metadata.get("parent_id") or (
            document.metadata.get("title", ""),
            document.page_content[:100],
        )
