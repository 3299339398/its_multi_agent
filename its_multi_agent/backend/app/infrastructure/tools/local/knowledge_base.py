import asyncio
import httpx
from typing import Dict
from agents import function_tool
from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.services.agent_hooks import agent_hooks, AgentPolicyDenied


async def request_knowledge(
    question: str,
    knowledge_space: str = "default",
    domain: str = "general",
    *,
    retrieve_only: bool = False,
) -> Dict:
    """
       查询通用私域知识库，用于检索制度、产品、技术、教学、法律、项目等文档。

       Args:
           question (Optional[str]): 需要查询的具体问题文本。

       Returns:
           dict: 包含查询结果的字典。包含 'question':用户输出问题 ‘answer’:答案
    """

    if not settings.KNOWLEDGE_BASE_URL:
        return {"status": "error", "error_msg": "知识库服务未配置"}
    if not settings.KNOWLEDGE_SERVICE_TOKEN or len(settings.KNOWLEDGE_SERVICE_TOKEN) < 32:
        return {"status": "error", "error_msg": "知识库服务认证未配置"}

    async with httpx.AsyncClient() as client:
        try:
            # 1. 发送请求（异步上下文管理器对象）
            response = await client.post(
                url=f"{settings.KNOWLEDGE_BASE_URL.rstrip('/')}/query",
                json={
                    "question": question,
                    "knowledge_space": knowledge_space,
                    "domain": domain,
                    "retrieve_only": retrieve_only,
                },
                headers={"X-Service-Token": settings.KNOWLEDGE_SERVICE_TOKEN},
                timeout=settings.KNOWLEDGE_REQUEST_TIMEOUT,
            )

            # 2. 处理异常情况(4xx-600x)直接抛出异常
            response.raise_for_status()

            # 3. 处理正常情况
            return response.json()

        except httpx.HTTPError as e:
            logger.error(f"发送请求获取知识库服务下的知识库数据失败:{str(e)}")
            return {"status": "error", "error_msg": "知识库服务暂时不可用，请稍后重试。"}
        except Exception as e:
            logger.error(f"未知错误:{str(e)}")
            return {"status": "error", "error_msg": "知识库服务返回异常，请稍后重试。"}


@function_tool
async def query_knowledge(
    question: str,
    knowledge_space: str = "default",
    domain: str = "general",
) -> Dict:
    """Return original evidence excerpts and source IDs for a grounded answer."""
    try:
        await agent_hooks.authorize_tool({
            "tool_name": "query_knowledge", "question": question,
            "knowledge_space": knowledge_space, "domain": domain,
        })
        return await request_knowledge(question, knowledge_space, domain, retrieve_only=True)
    except AgentPolicyDenied as error:
        return {"status": "error", "error_msg": str(error)}


async def main():
    result = await query_knowledge(question="电脑不能开机怎么解决?")
    print(result)


# 测试接口调用
if __name__ == '__main__':
    asyncio.run(main())
