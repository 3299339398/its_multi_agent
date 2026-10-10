import hashlib
import json
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from its_multi_agent.backend.knowledge.config.settings import settings


SEPARATORS = ["\n##", "\n**", "\n\n", "\n", " ", ""]


class ParentChildSplitter:
    """生成用于检索的子块，并保留对应父块的完整上下文。"""

    def __init__(self):
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.PARENT_CHUNK_SIZE,
            chunk_overlap=settings.PARENT_CHUNK_OVERLAP,
            separators=SEPARATORS,
        )
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHILD_CHUNK_SIZE,
            chunk_overlap=settings.CHILD_CHUNK_OVERLAP,
            separators=SEPARATORS,
        )

    def split(
        self,
        documents: List[Document],
        source_name: str,
        document_hash: str = "",
        context_prefix: str = "",
    ) -> List[Document]:
        children = []
        source_context = context_prefix.strip() or f"文档来源:{source_name}"
        for source_index, document in enumerate(documents):
            section_path = str(
                document.metadata.get("section_path")
                or document.metadata.get("heading_path")
                or document.metadata.get("title")
                or ""
            ).strip()
            indexed_context = (
                f"{source_context}\n章节路径:{section_path}"
                if section_path and f"章节路径:{section_path}" not in source_context
                else source_context
            )
            parents = self._split_if_needed(
                document, self.parent_splitter, settings.PARENT_CHUNK_SIZE
            )
            for parent_index, parent in enumerate(parents):
                parent_text = parent.page_content.strip()
                if not parent_text:
                    continue
                parent_content = f"{indexed_context}\n{parent_text}"
                parent_id = self._parent_id(
                    document_hash=document_hash,
                    source_name=source_name,
                    source_index=source_index,
                    parent_index=parent_index,
                    metadata=parent.metadata,
                )
                child_documents = self._split_if_needed(
                    parent, self.child_splitter, settings.CHILD_CHUNK_SIZE
                )
                for child_index, child in enumerate(child_documents):
                    child_text = child.page_content.strip()
                    if not child_text:
                        continue
                    metadata = dict(child.metadata)
                    metadata.update(
                        {
                            "chunk_type": "child",
                            "parent_id": parent_id,
                            "parent_index": parent_index,
                            "child_index": child_index,
                            "parent_content": parent_content,
                        }
                    )
                    children.append(
                        Document(
                            page_content=f"{indexed_context}\n{child_text}",
                            metadata=metadata,
                        )
                    )
        return children

    @staticmethod
    def _split_if_needed(
        document: Document, splitter, threshold: int
    ) -> List[Document]:
        if len(document.page_content) <= threshold:
            return [
                Document(
                    page_content=document.page_content, metadata=dict(document.metadata)
                )
            ]
        return splitter.split_documents([document])

    @staticmethod
    def _parent_id(
        document_hash: str,
        source_name: str,
        source_index: int,
        parent_index: int,
        metadata: dict,
    ) -> str:
        identity = {
            "document": document_hash or source_name,
            "source_index": source_index,
            "parent_index": parent_index,
            "page": metadata.get("page"),
            "sheet": metadata.get("sheet"),
        }
        value = json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(value).hexdigest()
