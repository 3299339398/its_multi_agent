import os.path
import hashlib
from pathlib import Path
from uuid import uuid4
import logging
import time
import aiofiles

logger = logging.getLogger(__name__)
from fastapi import (
    APIRouter,
    Depends,
    Header,
    UploadFile,
    File,
    Form,
    HTTPException,
    Query,
)
from starlette.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from its_multi_agent.backend.knowledge.services.ingestion.ingestion_processor import (
    IngestionProcessor,
)
from its_multi_agent.backend.knowledge.schemas.schema import (
    KnowledgeDocumentList,
    KnowledgeStatistics,
    QueryRequest,
    QueryResponse,
    UploadResponse,
)
from its_multi_agent.backend.knowledge.services.ingestion_task_service import (
    create_ingestion_task_service,
)
from its_multi_agent.backend.knowledge.services.retrieval_service import (
    RetrievalService,
)
from its_multi_agent.backend.knowledge.services.query_service import QueryService
from its_multi_agent.backend.knowledge.config.settings import settings
from its_multi_agent.backend.knowledge.repositories.document_registry import (
    DocumentBusyError,
    document_registry,
)
from its_multi_agent.backend.knowledge.api.dependencies import verify_service_token


# 1.创建APIRouter
router = APIRouter()
# 2. 创建应用的实例
ingestion_processor = IngestionProcessor()
retrieval_service = RetrievalService()
query_service = QueryService()
ingestion_task_service = create_ingestion_task_service(ingestion_processor)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx", ".xlsx"}


# IO(对文件读写) 执行SQL 网络请求 典型耗时任务
@router.post("/upload", response_model=UploadResponse, summary="提交知识库异步入库任务")
async def upload_file(
    file: UploadFile = File(...),
    knowledge_space: str = Form(
        "default",
        min_length=1,
        max_length=64,
        pattern=r"^[\w.-]+$",
    ),
    domain: str = Form(
        "general",
        min_length=1,
        max_length=64,
        pattern=r"^[\w.-]+$",
    ),
    uploaded_by: str = Form("system", min_length=1, max_length=128),
    _authorized: None = Depends(verify_service_token),
):
    tmp_md_path = None
    registry_hash = None
    claimed = False

    try:
        safe_filename = Path(file.filename or "").name
        if (
            not safe_filename
            or Path(safe_filename).suffix.lower() not in SUPPORTED_EXTENSIONS
        ):
            raise HTTPException(
                status_code=400, detail="仅支持 .md、.txt、.pdf、.docx、.xlsx 文件"
            )

        # 0.临时目录
        temp_md_dir = settings.TMP_MD_FOLDER_PATH
        tmp_md_path = os.path.join(temp_md_dir, f"{uuid4().hex}_{safe_filename}")
        os.makedirs(temp_md_dir, exist_ok=True)

        # 1. 文件写入磁盘
        total_bytes = 0
        hasher = hashlib.sha256()
        async with aiofiles.open(tmp_md_path, "wb") as out_file:
            while content := await file.read(1024 * 1024):
                total_bytes += len(content)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413, detail="文件大小不能超过 10 MB"
                    )
                hasher.update(content)
                await out_file.write(content)

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="不能上传空文件")

        content_hash = hasher.hexdigest()
        registry_hash = hashlib.sha256(
            f"{knowledge_space}\0{domain}\0{content_hash}".encode("utf-8")
        ).hexdigest()
        claimed = await run_in_threadpool(
            document_registry.claim,
            registry_hash,
            safe_filename,
            content_hash=content_hash,
            knowledge_space=knowledge_space,
            domain=domain,
            file_size=total_bytes,
            uploaded_by=uploaded_by,
        )
        if not claimed:
            if (
                await run_in_threadpool(document_registry.get_status, registry_hash)
                == "complete"
            ):
                return UploadResponse(
                    status="duplicate",
                    message="文档内容已存在，已跳过重复入库",
                    file_name=safe_filename,
                    document_hash=registry_hash,
                    chunks_added=0,
                    knowledge_space=knowledge_space,
                    domain=domain,
                )
            existing = await run_in_threadpool(ingestion_task_service.active_task_for_document, registry_hash)
            if existing:
                return JSONResponse(status_code=202, content=UploadResponse(
                    status="queued", message="复用正在处理的入库任务", file_name=safe_filename,
                    task_id=existing["task_id"], document_hash=registry_hash, chunks_added=0,
                    knowledge_space=knowledge_space, domain=domain,
                ).model_dump())
            # The first request may have claimed the document but not yet created its task.
            raise HTTPException(status_code=409, detail="文档正在排队，请稍后重试", headers={"Retry-After": "1"})

        upload_path = settings.INGESTION_UPLOAD_FOLDER_PATH
        os.makedirs(upload_path, exist_ok=True)
        stored_path = os.path.join(upload_path, f"{registry_hash}_{safe_filename}")
        os.replace(tmp_md_path, stored_path)
        tmp_md_path = None
        task = await run_in_threadpool(
            ingestion_task_service.create_task,
            document_hash=registry_hash,
            file_path=stored_path,
            file_name=safe_filename,
            knowledge_space=knowledge_space,
            domain=domain,
            uploaded_by=uploaded_by,
        )
        return JSONResponse(
            status_code=202,
            content=UploadResponse(
                status="queued",
                message="文档已提交后台入库任务",
                file_name=safe_filename,
                task_id=task["task_id"],
                document_hash=registry_hash,
                chunks_added=0,
                knowledge_space=knowledge_space,
                domain=domain,
            ).model_dump(),
        )

    except HTTPException:
        if claimed and registry_hash:
            await run_in_threadpool(document_registry.fail, registry_hash)
        raise
    except Exception as e:
        if claimed and registry_hash:
            await run_in_threadpool(document_registry.fail, registry_hash, str(e))
        logger.exception("文档上传到知识库失败")
        raise HTTPException(status_code=500, detail="文档处理失败，请稍后重试") from e

    finally:
        # 4. 清理上传文件
        if tmp_md_path and os.path.exists(tmp_md_path):
            os.remove(tmp_md_path)
            logger.info(f"临时文件:{tmp_md_path}已删除...")


@router.get("/tasks/{task_id}", summary="查询异步入库任务")
async def get_ingestion_task(
    task_id: str, _authorized: None = Depends(verify_service_token)
):
    task = await run_in_threadpool(ingestion_task_service.get_task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/tasks", summary="分页查询异步入库任务")
async def list_ingestion_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _authorized: None = Depends(verify_service_token),
):
    return await run_in_threadpool(
        ingestion_task_service.list_tasks, page=page, page_size=page_size
    )


@router.post("/tasks/{task_id}/retry", summary="重试异步入库任务")
async def retry_ingestion_task(
    task_id: str, _authorized: None = Depends(verify_service_token)
):
    task = await run_in_threadpool(ingestion_task_service.retry_task, task_id)
    if not task:
        raise HTTPException(
            status_code=409, detail="任务不可重试，可能已完成或源文件已清理"
        )
    return task


@router.get(
    "/documents",
    response_model=KnowledgeDocumentList,
    summary="分页查询知识库文档",
)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=128),
    status: str = Query(
        "", pattern=r"^(|processing|complete|failed|deletion_failed|deleted)$"
    ),
    knowledge_space: str = Query("", max_length=64, pattern=r"^(|[\w.-]+)$"),
    domain: str = Query("", max_length=64, pattern=r"^(|[\w.-]+)$"),
    include_deleted: bool = False,
    _authorized: None = Depends(verify_service_token),
):
    return await run_in_threadpool(
        document_registry.list_documents,
        page=page,
        page_size=page_size,
        search=search.strip(),
        status=status,
        knowledge_space=knowledge_space,
        domain=domain,
        include_deleted=include_deleted,
    )


@router.get(
    "/documents/statistics",
    response_model=KnowledgeStatistics,
    summary="知识库文档统计",
)
async def document_statistics(
    _authorized: None = Depends(verify_service_token),
):
    return await run_in_threadpool(document_registry.statistics)


@router.delete("/documents/{document_hash}", summary="删除知识库文档")
async def delete_document(
    document_hash: str,
    actor: str = Header("system", alias="X-Actor-Id", max_length=128),
    _authorized: None = Depends(verify_service_token),
):
    if len(document_hash) != 64 or any(
        char not in "0123456789abcdef" for char in document_hash.lower()
    ):
        raise HTTPException(status_code=400, detail="无效的文档 ID")
    try:
        return await run_in_threadpool(
            ingestion_task_service.delete_document,
            document_hash,
            actor,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail="文档不存在") from error
    except DocumentBusyError as error:
        raise HTTPException(
            status_code=409, detail="文档正在处理中，暂时不能删除"
        ) from error
    except Exception as error:
        logger.exception("删除知识库文档失败: %s", document_hash)
        raise HTTPException(
            status_code=500, detail="文档删除失败，请稍后重试"
        ) from error


@router.post("/query", response_model=QueryResponse, summary="查询知识库")
async def query(
    request: QueryRequest,
    _authorized: None = Depends(verify_service_token),
):
    """
    查询知识库
    Args:
        request: 用户的输入请求

    Returns:
        QueryResponse： 模型的结果以及原始问题

    """
    try:
        started_at = time.perf_counter()
        rewrite_ms = 0.0
        retrieval_ms = 0.0
        # 1. 判断用户问题
        user_question = request.question
        if not user_question:
            raise HTTPException(status_code=500, detail="查询问题不存在")

        if settings.QUERY_REWRITE_ADAPTIVE:
            # 快速路径先使用原始问题检索，仅在首轮排序较弱时调用大模型改写。
            search_queries = [user_question.strip()]
        else:
            stage_started_at = time.perf_counter()
            search_queries = await run_in_threadpool(
                query_service.build_search_queries,
                user_question,
                request.knowledge_space,
                request.domain,
            )
            rewrite_ms += (time.perf_counter() - stage_started_at) * 1000
        stage_started_at = time.perf_counter()
        retrieval_context = await run_in_threadpool(
            retrieval_service.retrieval,
            user_question,
            search_queries,
            request.knowledge_space,
            request.domain,
        )
        retrieval_ms += (time.perf_counter() - stage_started_at) * 1000

        if settings.QUERY_REWRITE_ADAPTIVE and query_service.should_expand_retrieval(
            retrieval_context
        ):
            stage_started_at = time.perf_counter()
            expanded_queries = await run_in_threadpool(
                query_service.build_search_queries,
                user_question,
                request.knowledge_space,
                request.domain,
                True,
            )
            rewrite_ms += (time.perf_counter() - stage_started_at) * 1000
            if expanded_queries != search_queries:
                search_queries = expanded_queries
                stage_started_at = time.perf_counter()
                retrieval_context = await run_in_threadpool(
                    retrieval_service.retrieval,
                    user_question,
                    search_queries,
                    request.knowledge_space,
                    request.domain,
                )
                retrieval_ms += (time.perf_counter() - stage_started_at) * 1000

        # 3. 调用查询器的查询方法
        stage_started_at = time.perf_counter()
        answer = (
            ""
            if request.retrieve_only
            else await run_in_threadpool(
                query_service.generate_answer, user_question, retrieval_context
            )
        )
        generation_ms = (time.perf_counter() - stage_started_at) * 1000
        logger.info(
            "知识库查询完成 question_len=%d queries=%d sources=%d "
            "rewrite_ms=%.0f retrieval_ms=%.0f generation_ms=%.0f elapsed_ms=%.0f",
            len(user_question),
            len(search_queries),
            len(retrieval_context),
            rewrite_ms,
            retrieval_ms,
            generation_ms,
            (time.perf_counter() - started_at) * 1000,
        )

        # 4. 封装到响应数据模型
        return QueryResponse(
            question=user_question,
            answer=answer,
            knowledge_space=request.knowledge_space,
            domain=request.domain,
            search_queries=search_queries,
            sources=query_service.build_sources(retrieval_context),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"调用查询知识库服务失败:原因:{str(e)}")
        raise HTTPException(status_code=500, detail="服务内部出现异常")
