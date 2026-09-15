import time
from typing import Any, Dict, List, Optional

from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.infrastructure.logging.logger import logger

try:
    from pymilvus import DataType, MilvusClient
except ImportError:
    DataType = None
    MilvusClient = None


class MilvusMemoryRepository:
    """长期用户记忆的 Milvus 仓储，collection 与知识库完全隔离。"""

    def __init__(self) -> None:
        self._client = None
        self._last_attempt = 0.0
        self._connect()

    @property
    def available(self) -> bool:
        if self._client is None and time.time() - self._last_attempt > 10:
            self._connect()
        return self._client is not None

    def insert(self, memories: List[Dict[str, Any]]) -> None:
        if not self._client or not memories:
            return
        self._client.insert(collection_name=settings.MILVUS_MEMORY_COLLECTION, data=memories)

    def upsert_or_insert(
        self,
        memory: Dict[str, Any],
        threshold: Optional[float] = None,
    ) -> str:
        """同一用户的近似记忆更新原记录，否则新增记录。"""
        if not self._client:
            return ""
        cosine_threshold = (
            settings.MEMORY_DEDUP_COSINE_THRESHOLD
            if threshold is None
            else threshold
        )
        similar = self.search(memory["user_id"], memory["embedding"], limit=1)
        if (
            similar
            and similar[0].get("distance", -1) >= cosine_threshold
            and similar[0].get("memory_id")
        ):
            memory["id"] = int(similar[0]["memory_id"])
            self._client.upsert(collection_name=settings.MILVUS_MEMORY_COLLECTION, data=[memory])
            return str(memory["id"])
        result = self._client.insert(collection_name=settings.MILVUS_MEMORY_COLLECTION, data=[memory])
        ids = result.get("ids", []) if isinstance(result, dict) else []
        return str(ids[0]) if ids else ""

    def search(self, user_id: str, embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        if not self._client:
            return []
        safe_user_id = user_id.replace('"', '\\"')
        results = self._client.search(
            collection_name=settings.MILVUS_MEMORY_COLLECTION,
            data=[embedding],
            filter=f'user_id == "{safe_user_id}" and expires_at > {int(time.time())}',
            limit=limit,
            output_fields=["content", "memory_type", "importance", "source_session_id", "expires_at"],
        )
        return [
            item["entity"] | {"memory_id": item.get("id"), "distance": item.get("distance")}
            for item in results[0]
        ]

    def list(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not self._client:
            return []
        safe_user_id = user_id.replace('"', '\\"')
        return self._client.query(
            collection_name=settings.MILVUS_MEMORY_COLLECTION,
            filter=f'user_id == "{safe_user_id}" and expires_at > {int(time.time())}',
            output_fields=["id", "content", "memory_type", "importance", "source_session_id", "created_at", "expires_at"],
            limit=limit,
        )

    def delete(self, user_id: str, memory_id: int) -> bool:
        if not self._client:
            return False
        safe_user_id = user_id.replace('"', '\\"')
        result = self._client.delete(
            collection_name=settings.MILVUS_MEMORY_COLLECTION,
            filter=f'user_id == "{safe_user_id}" and id == {int(memory_id)}',
        )
        if isinstance(result, dict):
            return int(result.get("delete_count", 0)) > 0
        return False

    def _ensure_collection(self) -> None:
        collection = settings.MILVUS_MEMORY_COLLECTION
        if self._client.has_collection(collection_name=collection):
            return

        schema = self._client.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("user_id", DataType.VARCHAR, max_length=64)
        schema.add_field("content", DataType.VARCHAR, max_length=2000)
        schema.add_field("memory_type", DataType.VARCHAR, max_length=64)
        schema.add_field("importance", DataType.FLOAT)
        schema.add_field("source_session_id", DataType.VARCHAR, max_length=128)
        schema.add_field("created_at", DataType.INT64)
        schema.add_field("expires_at", DataType.INT64)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=settings.MEMORY_EMBEDDING_DIM)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self._client.create_collection(
            collection_name=collection,
            schema=schema,
            index_params=index_params,
        )

    def _connect(self) -> None:
        self._last_attempt = time.time()
        if MilvusClient is None or not settings.MILVUS_URI:
            return
        try:
            kwargs = {"uri": settings.MILVUS_URI}
            if settings.MILVUS_TOKEN:
                kwargs["token"] = settings.MILVUS_TOKEN
            self._client = MilvusClient(**kwargs)
            self._ensure_collection()
        except Exception as error:
            logger.debug("Milvus 长期记忆暂不可用，稍后重试: %s", error)
            self._client = None


memory_repository = MilvusMemoryRepository()
