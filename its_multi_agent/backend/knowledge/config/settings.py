from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    API_KEY: str = os.environ.get("API_KEY", "")
    BASE_URL: str = os.environ.get("BASE_URL", "")
    MODEL: str = os.environ.get("MODEL", "")
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "")
    LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.environ.get("LLM_BASE_URL", "")
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "")

    # 知识库服务配置
    KNOWLEDGE_BASE_URL: str = os.environ.get("KNOWLEDGE_BASE_URL", "")
    KNOWLEDGE_SERVICE_TOKEN: str = ""
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    # 知识库项目路径
    _project_root = os.path.dirname(_current_dir)

    MILVUS_URI: str = os.environ.get("MILVUS_URI", "http://milvus:19530")
    MILVUS_TOKEN: str = os.environ.get("MILVUS_TOKEN", "")
    MILVUS_COLLECTION: str = os.environ.get("MILVUS_COLLECTION", "its_knowledge")
    MILVUS_MEMORY_COLLECTION: str = os.environ.get(
        "MILVUS_MEMORY_COLLECTION", "its_user_memories"
    )

    # 默认目录
    CRAWL_OUTPUT_DIR: str = os.path.join(_project_root, "data", "crawl")
    # 默认从 data/crawl 目录读取 Markdown 文件
    MD_FOLDER_PATH: str = CRAWL_OUTPUT_DIR
    TMP_MD_FOLDER_PATH: str = os.path.join(_project_root, "data", "tmp")
    INGESTION_UPLOAD_FOLDER_PATH: str = os.path.join(
        _project_root, "data", "ingestion_uploads"
    )
    DOCUMENT_REGISTRY_PATH: str = os.path.join(
        _project_root, "data", "document_registry.db"
    )
    INGESTION_TASK_DB_PATH: str = os.path.join(
        _project_root, "data", "ingestion_tasks.db"
    )
    INGESTION_WORKERS: int = 2
    LEXICAL_INDEX_PATH: str = os.path.join(_project_root, "data", "lexical_index.db")

    # 文本切分配置
    CHUNK_SIZE: int = 3000
    CHUNK_OVERLAP: int = 200
    PARENT_CHUNK_SIZE: int = 2400
    PARENT_CHUNK_OVERLAP: int = 200
    CHILD_CHUNK_SIZE: int = 600
    CHILD_CHUNK_OVERLAP: int = 100
    VECTOR_CHILD_TOP_K: int = 15
    FINAL_TOP_K: int = 5
    QUERY_REWRITE_ENABLED: bool = True
    QUERY_REWRITE_VARIANTS: int = 2
    QUERY_REWRITE_ADAPTIVE: bool = True
    QUERY_REWRITE_MIN_LENGTH: int = 18
    ADAPTIVE_REWRITE_SCORE_THRESHOLD: float = 0.55
    LEGACY_TITLE_RETRIEVAL_ENABLED: bool = False
    BM25_RETRIEVAL_ENABLED: bool = True
    BM25_TOP_K: int = 15
    BM25_MAX_QUERY_TERMS: int = 12
    RRF_K: int = 60
    SCOPE_COLLECTIONS_ENABLED: bool = True
    LEGACY_SCOPE_FALLBACK_ENABLED: bool = True
    LEGACY_SCOPE_FALLBACK_TOP_K: int = 60
    HYBRID_RERANK_ENABLED: bool = True
    RERANK_SEMANTIC_WEIGHT: float = 0.65
    RERANK_LEXICAL_WEIGHT: float = 0.1
    RERANK_QUERY_COVERAGE_WEIGHT: float = 0.05
    RERANK_RRF_WEIGHT: float = 0.2
    RERANK_SCORE_THRESHOLD: float = 0.25
    RERANK_CANDIDATE_K: int = 20
    EMBEDDING_CACHE_SIZE: int = 512
    CROSS_ENCODER_MODEL: str = ""
    CROSS_ENCODER_DEVICE: str = "cpu"

    MAX_WORKERS: int = 10

    OCR_ENABLED: bool = True
    OCR_PDF_TEXT_THRESHOLD: int = 30
    OCR_PDF_DPI: int = 200

    # 检索配置
    TOP_ROUGH: int = 50
    TOP_FINAL: int = 5

    model_config = SettingsConfigDict(
        env_file=os.path.join(_project_root, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
