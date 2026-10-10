"""编码 Agent 使用的受限工程工具。"""
import asyncio
import json

from agents import RunContextWrapper, function_tool

from its_multi_agent.backend.app.schemas.agent_context import AgentRequestContext
from its_multi_agent.backend.app.services.agent_hooks import (
    AgentPolicyDenied, agent_hooks, tool_allowed, tool_confirmed,
)
from its_multi_agent.backend.app.services.code_workspace_service import CodeWorkspaceError, CodeWorkspaceService


async def _invoke(ctx, tool_name, operation, **arguments):
    payload = {
        "tool_name": tool_name, "user_id": ctx.context.user_id,
        "run_id": ctx.context.run_id, "context": ctx.context, **arguments,
    }
    try:
        if not tool_allowed(ctx.context, tool_name):
            return json.dumps({"status": "error", "error_msg": "当前分支未启用工程工具"}, ensure_ascii=False)
        if not tool_confirmed(ctx.context, tool_name):
            return json.dumps({"status": "error", "error_msg": "工程工具尚未获得用户确认"}, ensure_ascii=False)
        await agent_hooks.authorize_tool(payload)
        await agent_hooks.emit("tool_call", payload)
        service = CodeWorkspaceService(ctx.context.code_workspace_root, actor=ctx.context.user_id)
        result = await asyncio.to_thread(operation(service))
        await agent_hooks.emit("tool_output", {
            **payload, "status": result.get("status"), "changed": result.get("changed", False),
        })
        return json.dumps(result, ensure_ascii=False)
    except (CodeWorkspaceError, AgentPolicyDenied) as error:
        await agent_hooks.emit("tool_output", {
            **payload, "status": "error", "error_type": type(error).__name__,
        })
        return json.dumps({"status": "error", "error_msg": str(error)}, ensure_ascii=False)
    except (OSError, UnicodeError) as error:
        await agent_hooks.emit("tool_output", {
            **payload, "status": "error", "error_type": type(error).__name__,
        })
        return json.dumps({"status": "error", "error_msg": "工程文件操作暂时不可用"}, ensure_ascii=False)


@function_tool
async def list_code_files(ctx: RunContextWrapper[AgentRequestContext], path: str = ".") -> str:
    """列出授权工程目录中的源码和配置文件。"""
    return await _invoke(ctx, "list_code_files", lambda service: lambda: service.list_files(path), path=path)


@function_tool
async def read_code_file(ctx: RunContextWrapper[AgentRequestContext], path: str,
                         start_line: int = 1, end_line: int = 400) -> str:
    """按行读取授权工程中的 UTF-8 文本文件。"""
    return await _invoke(ctx, "read_code_file", lambda service: lambda: service.read_file(path, start_line, end_line), path=path)


@function_tool
async def search_code(ctx: RunContextWrapper[AgentRequestContext], query: str, path: str = ".") -> str:
    """在授权工程的文本文件中搜索固定文本。"""
    return await _invoke(ctx, "search_code", lambda service: lambda: service.search(query, path), path=path)


@function_tool
async def replace_code(ctx: RunContextWrapper[AgentRequestContext], path: str,
                       old_text: str, new_text: str, expected_sha256: str = "",
                       operation_id: str = "") -> str:
    """读取后带文件 SHA-256 版本执行一次精确替换；重复 operation_id 返回原结果。"""
    if not expected_sha256:
        return json.dumps({
            "status": "error",
            "error_msg": "修改前必须先读取文件并提供 expected_sha256",
        }, ensure_ascii=False)
    return await _invoke(
        ctx, "replace_code",
        lambda service: lambda: service.replace(
            path, old_text, new_text, expected_sha256=expected_sha256, operation_id=operation_id,
        ),
        path=path, expected_sha256=expected_sha256, operation_id=operation_id,
    )


@function_tool
async def create_code_file(ctx: RunContextWrapper[AgentRequestContext], path: str, content: str) -> str:
    """在授权工程内创建一个尚不存在的源码或配置文件。"""
    return await _invoke(ctx, "create_code_file", lambda service: lambda: service.create(path, content), path=path)


@function_tool
async def run_code_check(ctx: RunContextWrapper[AgentRequestContext], name: str) -> str:
    """运行服务端管理员预设的代码检查命令，不接受任意命令文本。"""
    return await _invoke(ctx, "run_code_check", lambda service: lambda: service.run_check(name), check_name=name)


CODE_TOOLS = (list_code_files, read_code_file, search_code, replace_code, create_code_file, run_code_check)
CODE_TOOL_NAMES = frozenset(tool.name for tool in CODE_TOOLS)
