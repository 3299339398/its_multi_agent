"""Application entry point for the standalone knowledge service."""

import logging

import uvicorn
from fastapi import FastAPI

from its_multi_agent.backend.knowledge.api.routers import router


logger = logging.getLogger(__name__)


def create_fast_app() -> FastAPI:
    app = FastAPI(title="Knowledge API")
    app.include_router(router)

    @app.get("/healthz", tags=["system"])
    async def healthz():
        return {"status": "ok", "service": "knowledge-api"}

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting knowledge API")
    uvicorn.run(app=create_fast_app(), host="127.0.0.1", port=8001)
