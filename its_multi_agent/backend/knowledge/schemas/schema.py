from typing import List, Optional
import hashlib
import json
import math

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """
    文件上传的相应数据模式
    """
    status: str
    message: str
    file_name: str
    task_id: Optional[str] = None
    document_hash: Optional[str] = None
    chunks_added: int = 0  # 上传文档切分之后的文档块数量
    knowledge_space: str = "default"
    domain: str = "general"



class QueryResponse(BaseModel):
    """
    查询响应数据模型
    """
    question: str
    answer: str
    knowledge_space: str = "default"
    domain: str = "general"
    search_queries: List[str] = Field(default_factory=list)
    sources: List["KnowledgeSource"] = Field(default_factory=list)


class KnowledgeSource(BaseModel):
    title: str
    source_name: str = ""
    page: Optional[int] = None
    sheet: Optional[str] = None
    version: str = ""
    score: Optional[float] = None
    score_kind: str = "ranking_score"
    source_id: str = ""
    document_hash: str = ""
    parent_id: str = ""
    excerpt: str = ""
    excerpt_truncated: bool = False

    @classmethod
    def from_document(cls, document):
        metadata = document.metadata
        def text(key, default=""):
            value = metadata.get(key)
            return value if isinstance(value, str) else default

        page = metadata.get("page")
        if isinstance(page, bool) or not isinstance(page, int):
            page = None
        score = metadata.get("rerank_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            score = None
        identity = [text("knowledge_space"), text("domain"), text("document_hash"),
                    text("parent_id"), text("source_name"), text("path"),
                    text("title"), page, text("sheet"), text("version"), document.page_content]
        source_id = "src_" + hashlib.sha256(
            json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        return cls(title=text("title", "未知来源"), source_name=text("source_name"),
                   page=page, sheet=text("sheet") or None, version=text("version"), score=score,
                   source_id=source_id, document_hash=text("document_hash"),
                   parent_id=text("parent_id"), excerpt=document.page_content[:12000],
                   excerpt_truncated=len(document.page_content) > 12000)


class QueryRequest(BaseModel):
    """查询的请求数据模型"""
    question: str = Field(min_length=1, max_length=5000)
    retrieve_only: bool = False
    knowledge_space: str = Field(
        default="default", min_length=1, max_length=64,
        pattern=r"^[\w.-]+$",
    )
    domain: str = Field(
        default="general", min_length=1, max_length=64,
        pattern=r"^[\w.-]+$",
    )


class KnowledgeDocument(BaseModel):
    document_hash: str
    content_hash: str = ""
    file_name: str
    status: str
    chunks_added: int = 0
    knowledge_space: str = "default"
    domain: str = "general"
    file_size: int = 0
    uploaded_by: str = "system"
    error_message: str = ""
    created_at: int
    updated_at: int
    deleted_at: Optional[int] = None
    deleted_by: str = ""


class KnowledgeDocumentList(BaseModel):
    items: List[KnowledgeDocument]
    total: int
    page: int
    page_size: int


class KnowledgeStatistics(BaseModel):
    total_documents: int
    complete_documents: int
    processing_documents: int
    failed_documents: int
    total_chunks: int
    knowledge_spaces: int
    domains: int


class IngestionTask(BaseModel):
    task_id: str
    document_hash: str
    file_name: str
    knowledge_space: str
    domain: str
    uploaded_by: str
    status: str
    progress: int
    message: str
    error_message: str = ""
    chunks_added: int = 0
    attempts: int = 0
    created_at: int
    updated_at: int


class IngestionTaskList(BaseModel):
    items: List[IngestionTask]
    total: int
    page: int
    page_size: int

