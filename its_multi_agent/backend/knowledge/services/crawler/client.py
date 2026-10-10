import requests

from its_multi_agent.backend.knowledge.config.settings import settings


class KnowledgeApiClient:
    """主要提供一个方法 获取网络知识"""

    @staticmethod
    def fetch_knowledge_content(knowledge_no: str, timeout: float = 10) -> dict:
        """根据知识库编号获取远端知识库内容。"""
        try:
            if not settings.KNOWLEDGE_BASE_URL:
                raise RuntimeError("未配置 KNOWLEDGE_BASE_URL")
            url = (
                f"{settings.KNOWLEDGE_BASE_URL.rstrip('/')}/"
                "knowledgeapi/api/knowledge/knowledgeDetails"
            )
            response = requests.get(
                url,
                params={"knowledgeNo": str(knowledge_no)},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise RuntimeError(f"请求远端知识库失败: {error}") from error
        except ValueError as error:
            raise RuntimeError("远端知识库返回了无效 JSON") from error

        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise RuntimeError("远端知识库响应缺少有效的 data 对象")
        return payload["data"]
