import json
import logging

from agents import RunContextWrapper, function_tool

from its_multi_agent.backend.app.schemas.agent_context import AgentRequestContext
from its_multi_agent.backend.app.services.file_artifact_service import file_artifact_service, FileArtifactError
from its_multi_agent.backend.app.services.agent_hooks import (
    agent_hooks, AgentPolicyDenied, tool_allowed, tool_confirmed,
)


logger = logging.getLogger(__name__)


class FileArtifactGenerationError(ValueError):
    """模型未能提供完整文件参数，不能通过重复执行工具恢复。"""


def file_tool_input_error(ctx, error: Exception):
    # SDK 默认把参数解析错误返回为“请重试”，长代码被截断时会不断重生成。
    # 只记录错误类型和长度，避免将文件正文或模型请求写入错误日志。
    logger.warning(
        "File tool invocation failed type=%s argument_chars=%d",
        type(error).__name__, len(getattr(ctx, "tool_arguments", "") or ""),
    )
    current = error
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, json.JSONDecodeError):
            raise FileArtifactGenerationError(
                "文件生成失败：模型返回的工具参数不是完整的 JSON。可能超过当前输出长度上限，请生成更精简的网页，或提高模型最大输出 token 后重试。"
            ) from error
        current = current.__cause__ or current.__context__
    raise FileArtifactGenerationError(
        "文件生成失败：工具参数格式不正确，请重新生成完整的文件名、内容和 MIME 类型。"
    ) from error


@function_tool(failure_error_function=file_tool_input_error)
async def create_file(ctx: RunContextWrapper[AgentRequestContext], filename: str, content: str, mime_type: str = "text/plain") -> str:
    """生成可下载文件（最多 2 MB）：txt、md、json、csv、html 或 htm。

    mime_type 必须与扩展名匹配：txt=text/plain、md=text/markdown、
    json=application/json、csv=text/csv、html/htm=text/html。
    网页优先生成自包含 HTML，将样式和脚本嵌入同一文件，供用户下载后打开。
    优先用紧凑 SVG 和 CSS 动画，遵守本轮给定的输出预算，不要生成冗长注释或重复代码。
    仅在返回 status=ok 时声称生成成功，并提供返回的下载链接。
    HTML 成功后还会返回 preview_url，请用 Markdown 链接提供“预览”和“下载”，方便用户直接观看动画。
    """
    if not tool_allowed(ctx.context, "create_file"):
        return json.dumps({"status": "error", "error_msg": "当前分支未启用文件输出"}, ensure_ascii=False)
    if not tool_confirmed(ctx.context, "create_file"):
        return json.dumps({"status": "error", "error_msg": "文件输出尚未获得用户确认"}, ensure_ascii=False)
    try:
        await agent_hooks.authorize_tool({
            "tool_name": "create_file", "filename": filename, "mime_type": mime_type,
            "user_id": ctx.context.user_id, "run_id": ctx.context.run_id,
            "context": ctx.context,
        })
        item = file_artifact_service.create(
            ctx.context.user_id, filename, content, mime_type=mime_type,
            session_id=ctx.context.session_id, run_id=ctx.context.run_id,
        )
        result = {"status": "ok", "file_id": item["id"], "filename": item["filename"],
                  "download_url": f"/api/files/{item['id']}/download"}
        if item["mime_type"] == "text/html":
            result["preview_url"] = f"#file-preview={item['id']}"
        return json.dumps(result, ensure_ascii=False)
    except (FileArtifactError, AgentPolicyDenied) as error:
        return json.dumps({"status": "error", "error_msg": str(error)}, ensure_ascii=False)
