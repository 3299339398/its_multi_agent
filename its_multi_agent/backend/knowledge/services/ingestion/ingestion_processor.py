import hashlib
import logging
import os
from typing import List

from langchain_community.vectorstores.utils import filter_complex_metadata
from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.repositories.lexical_index_repository import (
    LexicalIndexRepository,
)
from its_multi_agent.backend.knowledge.repositories.vector_store_repository import (
    VectorStoreRepository,
)
from its_multi_agent.backend.knowledge.services.ingestion.document_extractor import (
    DocumentExtractor,
)
from its_multi_agent.backend.knowledge.services.ingestion.parent_child_splitter import (
    ParentChildSplitter,
)
from its_multi_agent.backend.knowledge.utils.markdown_utils import MarkDownUtils

logger = logging.getLogger(__name__)


class IngestionProcessor:
    """提取并切分文档，将结果写入语义索引和词法索引。"""

    def __init__(self):
        self.vector_store = VectorStoreRepository()
        self.lexical_index = LexicalIndexRepository()
        self.parent_child_splitter = ParentChildSplitter()
        self.document_spliter = self.parent_child_splitter.child_splitter

    def ingest_file(
        self,
        file_path: str,
        document_hash: str = "",
        source_name: str = "",
        knowledge_space: str = "default",
        domain: str = "general",
    ) -> int:
        chunks, index_hash = self._prepare_chunks(
            file_path,
            document_hash,
            source_name,
            knowledge_space,
            domain,
        )
        if not chunks:
            raise RuntimeError("文档未提取到可入库的内容")

        chunks_added = self.vector_store.add_documents(
            chunks,
            knowledge_space=knowledge_space,
            domain=domain,
        )
        try:
            self.lexical_index.replace_document(
                index_hash,
                chunks,
                knowledge_space,
                domain,
            )
        except Exception:
            try:
                self.vector_store.delete_document(index_hash, knowledge_space, domain)
            except Exception:
                logger.exception(
                    "关键词索引写入失败，向量补偿删除也失败: %s", index_hash
                )
            raise
        return chunks_added

    def index_lexical_file(
        self,
        file_path: str,
        document_hash: str = "",
        source_name: str = "",
        knowledge_space: str = "default",
        domain: str = "general",
    ) -> int:
        """补建 BM25 数据，不重复写入向量。"""
        chunks, index_hash = self._prepare_chunks(
            file_path,
            document_hash,
            source_name,
            knowledge_space,
            domain,
        )
        return self.lexical_index.replace_document(
            index_hash,
            chunks,
            knowledge_space,
            domain,
        )

    def _prepare_chunks(
        self,
        file_path: str,
        document_hash: str,
        source_name: str,
        knowledge_space: str,
        domain: str,
    ) -> tuple[List[Document], str]:
        try:
            documents = DocumentExtractor.load(file_path)
        except Exception as error:
            logger.error("文件 %s 加载失败: %s", file_path, error)
            raise RuntimeError(f"文件加载失败: {error}") from error

        source_file_name = source_name or os.path.basename(file_path)
        index_hash = (
            document_hash
            or hashlib.sha256(
                f"{knowledge_space}\0{domain}\0{source_file_name}".encode("utf-8")
            ).hexdigest()
        )
        for document in documents:
            document.metadata["title"] = MarkDownUtils.extract_title(source_file_name)
            document.metadata["source_name"] = source_file_name
            document.metadata["document_hash"] = index_hash

        chunks = self.parent_child_splitter.split(
            documents,
            source_name=source_file_name,
            document_hash=index_hash,
            context_prefix=(
                f"知识空间:{knowledge_space}\n"
                f"知识领域:{domain}\n"
                f"文档来源:{source_file_name}"
            ),
        )
        return (
            [
                document
                for document in filter_complex_metadata(chunks)
                if document.page_content.strip()
            ],
            index_hash,
        )
