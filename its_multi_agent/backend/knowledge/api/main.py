"""
创建FASTAPI实例，并且管理所有的路由
"""
import uvicorn
import uvicorn
from fastapi import FastAPI
from its_multi_agent.backend.knowledge.api.routers import router
from its_multi_agent.backend import knowledge
import logging
logging.basicConfig(level=logging.INFO)
logger=logging.getLogger(__name__)


def create_fast_app()->FastAPI:

    # 创建FastApi实例
    app=FastAPI(title="Knowledge API")

    #  注册各种路由
    app.include_router(router=router)

    @app.get("/healthz", tags=["system"])
    async def healthz():
        return {"status": "ok", "service": "knowledge-api"}

    return app




if __name__=="__main__":
    print("启动服务器")
    try:
        uvicorn.run(app=create_fast_app(),host="127.0.0.1",port=8001)
        logger.info("启动web服务器成功")
    except KeyboardInterrupt as e:
        logger.error(f"启动服务器失败：{e}")
