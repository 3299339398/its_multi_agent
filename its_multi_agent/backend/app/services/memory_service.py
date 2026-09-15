import asyncio
import json
import re
import time
from typing import Any, Dict, List

from openai import AsyncOpenAI

from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.repositories.milvus_memory_repository import (
    memory_repository as milvus_memory_repository,
)
from its_multi_agent.backend.app.repositories.sqlite_memory_repository import (
    sqlite_memory_repository,
)


memory_repository = (
    milvus_memory_repository
    if settings.MEMORY_BACKEND == "milvus"
    else sqlite_memory_repository
)


class MemoryService:
    """用户长期记忆服务：提取、向量化、存储和召回。"""

    def __init__(self) -> None:
        self._embedding_client = self._create_client()
        self._extraction_client = self._create_client()

    @property
    def available(self) -> bool:
        return memory_repository.available

    async def retrieve(self, user_id: str, query: str, workspace_id: str = "default") -> str:
        if not memory_repository.available:
            return ""
        try:
            if getattr(memory_repository, "supports_vectors", True):
                if not self._embedding_client:
                    return ""
                embedding = await self._embed(query)
                rows = await asyncio.to_thread(memory_repository.search, self._scope(user_id, workspace_id), embedding, 5)
            else:
                rows = await asyncio.to_thread(memory_repository.search_text, self._scope(user_id, workspace_id), query, 5)
            if not rows:
                return ""
            return "\n".join(
                f"- [{row.get('memory_type', 'fact')}] {row.get('content', '')}"
                for row in rows if row.get("content")
            )
        except Exception as error:
            logger.debug("长期记忆召回失败: %s", error)
            return ""

    async def extract_and_store(self, user_id: str, session_id: str, user_query: str, answer: str, workspace_id: str = "default") -> None:
        if not memory_repository.available:
            return
        try:
            if getattr(memory_repository, "supports_vectors", True):
                if not self._extraction_client:
                    return
                memories = await self._extract(user_query, answer)
            else:
                memories = self.extract_local_memories(user_query)
            if not memories:
                return
            now = int(time.time())
            expires_at = now + settings.MEMORY_TTL_DAYS * 86400
            rows = []
            for memory in memories:
                content = str(memory.get("content", "")).strip()[:2000]
                if not content:
                    continue
                rows.append({
                    "user_id": self._scope(user_id, workspace_id),
                    "content": content,
                    "memory_type": str(memory.get("memory_type", "fact"))[:64],
                    "importance": min(max(float(memory.get("importance", 0.5)), 0.0), 1.0),
                    "source_session_id": session_id or "default_session",
                    "created_at": now,
                    "expires_at": expires_at,
                })
                if getattr(memory_repository, "supports_vectors", True):
                    rows[-1]["embedding"] = await self._embed(content)
            for row in rows:
                await asyncio.to_thread(memory_repository.upsert_or_insert, row)
        except Exception as error:
            logger.debug("长期记忆写入失败: %s", error)

    def list_memories(self, user_id: str, workspace_id: str = "default") -> List[Dict[str, Any]]:
        try:
            return memory_repository.list(self._scope(user_id, workspace_id))
        except Exception as error:
            logger.debug("长期记忆列表读取失败: %s", error)
            return []

    def delete_memory(self, user_id: str, memory_id: int, workspace_id: str = "default") -> bool:
        try:
            return memory_repository.delete(self._scope(user_id, workspace_id), memory_id)
        except Exception as error:
            logger.debug("长期记忆删除失败: %s", error)
            return False

    async def _extract(self, user_query: str, answer: str) -> List[Dict[str, Any]]:
        prompt = f"""
从下面这轮对话中提取值得跨会话长期记住的用户事实。
只提取明确、稳定、对未来服务有帮助的信息，不要保存寒暄、一次性问题或模型猜测。
只返回 JSON 数组，每项格式为 {{"content":"...","memory_type":"profile|device|preference|troubleshooting_state","importance":0到1}}。
如果没有值得保存的内容，返回 []。

用户问题：{user_query}
助手回答：{answer[:4000]}
"""
        response = await self._extraction_client.chat.completions.create(
            model=settings.MEMORY_EXTRACTION_MODEL or settings.SUB_MODEL_NAME or settings.MAIN_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content or "[]"
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []

    async def _embed(self, text: str) -> List[float]:
        response = await self._embedding_client.embeddings.create(
            model=settings.MEMORY_EMBEDDING_MODEL,
            input=[text],
        )
        return response.data[0].embedding

    @staticmethod
    def extract_local_memories(user_query: str) -> List[Dict[str, Any]]:
        """Extract only explicit, stable user facts without calling an LLM."""
        text = re.sub(r"\s+", " ", user_query).strip()
        if not text:
            return []
        clauses = [
            item.strip(" ，,。！？!?；;")
            for item in re.split(r"[。！？!?；;\n]+", text)
        ]
        rules = (
            (r"(?:请)?记住(?:一下|：|:)?(.{2,120})", "fact", 0.95),
            (r"(?:我叫|我的名字是)([\w\u4e00-\u9fff·]{1,30})", "profile", 0.9),
            (r"(我(?:喜欢|偏好|习惯|不喜欢|更喜欢).{1,100})", "preference", 0.8),
            (r"(我(?:正在)?(?:使用|用的是).{1,100})", "device", 0.75),
            (r"(我的(?:电脑|手机|设备|系统|车型)是.{1,100})", "device", 0.8),
            (r"(我(?:住在|常住在|来自).{1,80})", "profile", 0.75),
        )
        extracted: List[Dict[str, Any]] = []
        seen = set()
        for clause in clauses:
            for pattern, memory_type, importance in rules:
                match = re.search(pattern, clause)
                if not match:
                    continue
                content = match.group(1).strip(" ，,。")
                if pattern.startswith("(?:请)?记住"):
                    content = f"用户要求记住：{content}"
                normalized = re.sub(r"\W+", "", content)
                if len(normalized) < 2 or normalized in seen:
                    continue
                seen.add(normalized)
                extracted.append({
                    "content": content[:2000],
                    "memory_type": memory_type,
                    "importance": importance,
                })
                break
        return extracted

    @staticmethod
    def _create_client():
        if settings.SF_API_KEY and settings.SF_BASE_URL:
            return AsyncOpenAI(api_key=settings.SF_API_KEY, base_url=settings.SF_BASE_URL)
        if settings.AL_BAILIAN_API_KEY and settings.AL_BAILIAN_BASE_URL:
            return AsyncOpenAI(api_key=settings.AL_BAILIAN_API_KEY, base_url=settings.AL_BAILIAN_BASE_URL)
        return None

    @staticmethod
    def _scope(user_id: str, workspace_id: str) -> str:
        return user_id if not workspace_id or workspace_id == "default" else f"{user_id}::ws::{workspace_id}"


memory_service = MemoryService()
