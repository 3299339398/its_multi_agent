import uvicorn
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from starlette.responses import JSONResponse
from its_multi_agent.backend.app.api.routers import router
from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.infrastructure.tools.mcp.mcp_manager import mcp_connect, mcp_cleanup
from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.services.task_manager import task_manager
from its_multi_agent.backend.app.infrastructure.ai.model_factory import list_profiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI应用生命周期管理

    在应用启动时建立MCP连接，在应用关闭时清理连接。
    确保资源正确初始化和释放。
    """
    # 应用启动时执行
    logger.info("应用启动，建立MCP连接...")
    try:
        await mcp_connect()
        logger.info("MCP连接建立完成")
    except Exception as e:
        logger.error(f"MCP连接建立失败: {str(e)}")

    try:
        await task_manager.resume_pending()
    except Exception as e:
        logger.error("恢复未完成任务失败: %s", e)

    yield  # 应用运行期间（先别释放mcp链接 去处理请求...）

    # 应用关闭时执行
    logger.info("应用关闭，清理MCP连接...")
    try:
        await mcp_cleanup()
        logger.info("MCP连接清理完成")
    except Exception as e:
        logger.error(f"MCP连接清理失败: {str(e)}")


def create_fast_api() -> FastAPI:
    # 1. 创建FastApi实例,绑定了生命周期事件
    app = FastAPI(title="ITS API", lifespan=lifespan)

    # 2. 处理跨域
    app.add_middleware(
        CORSMiddleware,
        # CORSMiddleware 会自动拦截后端的响应 并贴上这些标签 Access-Control-Allow-Origin Access-Control-Allow-Methods Access-Control-Allow-Headers
        allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # 3. 注册各种路由
    app.include_router(router=router)

    @app.get("/healthz", tags=["system"])
    async def healthz():
        return {"status": "ok", "service": "app-api"}

    @app.get("/readyz", tags=["system"])
    async def readyz():
        """检查已部署服务所需依赖是否就绪。"""
        checks = {}
        try:
            checks["model"] = bool(list_profiles())
        except Exception:
            checks["model"] = False
        if settings.KNOWLEDGE_BASE_URL:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.get(
                        settings.KNOWLEDGE_BASE_URL.rstrip("/") + "/healthz"
                    )
                checks["knowledge"] = response.status_code == 200
            except httpx.HTTPError:
                checks["knowledge"] = False
        if settings.REDIS_URL:
            try:
                import redis.asyncio as redis
                client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
                try:
                    await client.ping()
                    checks["redis"] = True
                finally:
                    await client.aclose()
            except Exception:
                checks["redis"] = False
        if checks and not all(checks.values()):
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "checks": checks},
            )
        return {"status": "ready", "checks": checks}

    # 4.返回创建的FastAPI
    return app


if __name__ == '__main__':
    print("1.准备启动Web服务器")
    try:
        uvicorn.run(app=create_fast_api(), host="127.0.0.1", port=8000)

        logger.info("2.启动Web服务器成功...")

    except KeyboardInterrupt as e:
        logger.error(f"2.启动Web服务器失败: {str(e)}")
