import asyncio
import httpx
from typing import Dict
from agents import RunContextWrapper, function_tool
from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.services.agent_hooks import agent_hooks, AgentPolicyDenied
from its_multi_agent.backend.app.services.agent_hooks import tool_allowed
from its_multi_agent.backend.app.schemas.agent_context import AgentRequestContext
from its_multi_agent.backend.app.schemas.tool import KnowledgeToolRequest


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
    ctx: RunContextWrapper[AgentRequestContext],
    question: str,
    knowledge_space: str = "default",
    domain: str = "general",
) -> Dict:
    """返回生成有据回答所需的原始证据片段和来源 ID。"""
    if not tool_allowed(ctx.context, "query_knowledge"):
        return {"status": "error", "error_msg": "当前分支未启用知识库查询"}
    try:
        request = KnowledgeToolRequest(
            question=question, knowledge_space=knowledge_space, domain=domain,
        )
    except Exception:
        return {"status": "error", "error_msg": "知识库查询参数无效"}
    try:
        await agent_hooks.authorize_tool({
            "tool_name": "query_knowledge", "question": request.question,
            "knowledge_space": request.knowledge_space, "domain": request.domain,
            "context": ctx.context,
        })
        return await request_knowledge(request.question, request.knowledge_space, request.domain, retrieve_only=True)
    except AgentPolicyDenied as error:
        return {"status": "error", "error_msg": str(error)}


async def main():
    # 直接运行本文件时调用底层客户端，函数工具本身需要 Agent 运行时上下文。
    result = await request_knowledge("电脑不能开机怎么解决?", retrieve_only=True)
    print(result)


# 测试接口调用
if __name__ == '__main__':
    asyncio.run(main())
