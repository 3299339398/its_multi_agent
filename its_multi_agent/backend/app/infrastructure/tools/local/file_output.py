import json

from agents import RunContextWrapper, function_tool

from its_multi_agent.backend.app.schemas.agent_context import AgentRequestContext
from its_multi_agent.backend.app.services.file_artifact_service import file_artifact_service, FileArtifactError
from its_multi_agent.backend.app.services.agent_hooks import agent_hooks, AgentPolicyDenied


@function_tool
async def create_file(ctx: RunContextWrapper[AgentRequestContext], filename: str, content: str, mime_type: str = "text/plain") -> str:
    """Create a bounded text artifact for the current user and return its download metadata."""
    try:
        await agent_hooks.authorize_tool({
            "tool_name": "create_file", "filename": filename, "mime_type": mime_type,
            "user_id": ctx.context.user_id, "run_id": ctx.context.run_id,
        })
        item = file_artifact_service.create(
            ctx.context.user_id, filename, content, mime_type=mime_type,
            session_id=ctx.context.session_id, run_id=ctx.context.run_id,
        )
        return json.dumps({"status": "ok", "file_id": item["id"], "filename": item["filename"],
                           "download_url": f"/api/files/{item['id']}/download"}, ensure_ascii=False)
    except (FileArtifactError, AgentPolicyDenied) as error:
        return json.dumps({"status": "error", "error_msg": str(error)}, ensure_ascii=False)
