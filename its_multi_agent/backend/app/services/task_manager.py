"""聊天后台任务的生命周期管理。

HTTP/SSE 连接仅负责订阅结果，实际 Agent 运行由 asyncio 任务管理，
因此客户端切换会话或重新连接不会取消已经开始的工作。
"""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.services.agent_service import MultiAgentService
from its_multi_agent.backend.app.repositories.sqlite_task_repository import task_repository, execution_lease, TaskLeaseLost
from its_multi_agent.backend.app.schemas.request import ChatMessageRequest
from its_multi_agent.backend.app.services.plan_executor import PlanExecutor
from its_multi_agent.backend.app.infrastructure.ai.model_factory import resolve_profile
from its_multi_agent.backend.app.repositories.model_profile_repository import user_model_profiles
from its_multi_agent.backend.app.projects import get_project
from its_multi_agent.backend.app.utils.response_util import ResponseFactory
from its_multi_agent.backend.app.schemas.response import StopReason
from its_multi_agent.backend.app.plugins import plugin_registry


@dataclass
class TaskRecord:
    run_id: str
    user_id: str
    session_id: str
    created_at: float = field(default_factory=time.time)
    status: str = "queued"
    packets: list[str] = field(default_factory=list)
    error: str | None = None
    task: asyncio.Task | None = None
    saw_finish: bool = False
    finish_reason: str | None = None
    checkpoint: dict[str, Any] | None = None


class TaskManager:
    MAX_TASKS = 100
    MAX_PACKETS = 500

    def __init__(self, repository=task_repository):
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()
        self._repository = repository
        self._lease_seconds = 90

    async def start(self, request, user_id: str) -> str:
        record = TaskRecord(str(uuid.uuid4()), user_id, request.context.session_id or "default_session")
        async with self._lock:
            self._tasks[record.run_id] = record
            self._prune_locked()
        self._repository.create(record.run_id, user_id, record.session_id, request, record.created_at)
        record.task = asyncio.create_task(self._run(record, request), name=f"agent-run-{record.run_id}")
        return record.run_id

    async def resume(self, run_id: str, user_id: str) -> dict[str, Any]:
        """显式从步骤 checkpoint 恢复任务；服务启动不会调用此方法。"""
        row = self._repository.get(run_id, user_id)
        if row is None:
            raise KeyError("任务不存在")
        active = self._tasks.get(run_id)
        if active is not None and (active.task is None or not active.task.done()) \
                and active.status not in {"completed", "failed", "cancelled"}:
            raise ValueError("任务仍在执行，不能重复恢复")
        if row.get("status") not in {"failed", "cancelled"}:
            raise ValueError("只有失败或取消的任务可以恢复")

        checkpoint = self._repository.execution_checkpoint(run_id, user_id)
        if checkpoint is None:
            raise ValueError("任务没有可恢复的步骤 checkpoint")
        try:
            payload = json.loads(row["request_json"])
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("任务请求数据已损坏，不能恢复") from error
        if payload.get("_resume_blocked") or payload.get("temporary_model"):
            raise ValueError("任务依赖临时模型凭据，不能恢复")
        try:
            request = ChatMessageRequest.model_validate(payload)
        except Exception as error:
            raise ValueError("任务请求格式已不兼容") from error
        self._validate_resume_request(request, user_id)
        reason = PlanExecutor.checkpoint_resume_blocking_reason(checkpoint)
        if reason:
            raise ValueError(reason)

        record = self._record_from_row(row)
        record.status = "queued"
        record.error = None
        record.saw_finish = False
        record.finish_reason = None
        async with self._lock:
            active = self._tasks.get(run_id)
            if active is not None and (active.task is None or not active.task.done()) \
                    and active.status not in {"completed", "failed", "cancelled"}:
                raise ValueError("任务仍在执行，不能重复恢复")
            if not self._repository.queue_resume(run_id, user_id):
                raise ValueError("任务已被其他实例恢复或尚未释放执行租约")
            self._tasks[run_id] = record
        record.task = asyncio.create_task(
            self._run(record, request, resume_checkpoint=checkpoint),
            name=f"agent-resume-{run_id}",
        )
        return self._summary(record)

    @staticmethod
    def _validate_resume_request(request: ChatMessageRequest, user_id: str) -> None:
        """恢复前重新检查项目、插件和模型配置，避免沿用过期权限。"""
        get_project(request.project_id, user_id=user_id)
        if request.model_profile_id and request.model_profile_id.startswith("user-"):
            profile = user_model_profiles.get(user_id, request.model_profile_id)
            if profile is None or not {"chat", "reasoning"}.intersection(profile["roles"]):
                raise ValueError("原模型配置不存在或不支持对话")
        else:
            try:
                resolve_profile(request.model_profile_id, role="chat")
            except Exception as error:
                raise ValueError("原模型配置当前不可用") from error

        project = get_project(request.project_id, user_id=user_id)
        manifests = {plugin.id: plugin for plugin in plugin_registry.list_plugins()}
        selected = set(request.enabled_plugins or ())
        if request.enabled_plugins is not None:
            unknown = selected.difference(project.plugins)
            if unknown:
                raise ValueError("原请求的插件权限已失效: " + ", ".join(sorted(unknown)))
            removed = selected.difference(manifests)
            if removed:
                raise ValueError("原请求的插件已从服务端移除: " + ", ".join(sorted(removed)))
        else:
            selected = {
                plugin_id for plugin_id in project.plugins
                if manifests.get(plugin_id) is not None
                and manifests[plugin_id].enabled_by_default
                and not manifests[plugin_id].requires_confirmation
            }
        missing = {
            plugin_id for plugin_id in selected
            if manifests.get(plugin_id) is not None
            and manifests[plugin_id].requires_confirmation
            and plugin_id not in set(request.confirmed_plugins)
        }
        if missing:
            raise ValueError("原请求的高风险插件确认已失效: " + ", ".join(sorted(missing)))

    async def resume_pending(self) -> None:
        """恢复上次进程遗留的排队任务，并将中断的运行中任务标记为失败。"""
        for row in self._repository.pending():
            try:
                if row["status"] == "running":
                    # 进程崩溃时，外部工具可能已经执行了部分操作。
                    # 不自动重放整个请求，标记失败后由用户明确发起重试；
                    # 涉及副作用的重试仍需保证幂等性。
                    self._repository.fail_expired(row["run_id"], "执行租约已过期，未自动重放")
                    continue
                payload = json.loads(row["request_json"])
                if payload.get("_resume_blocked"):
                    self._repository.fail_expired(row["run_id"], "任务包含不可恢复的临时模型凭据")
                    continue
                request = ChatMessageRequest.model_validate(payload)
                record = self._record_from_row(row)
                record.status = "queued"
                record.packets = self._repository.events(record.run_id)
                self._tasks[record.run_id] = record
                record.task = asyncio.create_task(self._run(record, request), name=f"agent-run-{record.run_id}")
            except Exception as exc:
                self._repository.fail_expired(row["run_id"], str(exc))
                logger.exception("恢复任务 %s 失败", row["run_id"])

    async def _run(self, record: TaskRecord, request, resume_checkpoint: dict | None = None) -> None:
        owner = uuid.uuid4().hex  # unique fencing identity for each execution attempt
        if record.status == "cancelled" or not self._repository.claim(record.run_id, owner, self._lease_seconds):
            record.status = "failed"  # local cache only; shared state belongs to the winner
            return  # Losing a claim must never overwrite the winning worker's state.
        token = execution_lease.set((record.run_id, owner))
        worker = asyncio.current_task()
        heartbeat = asyncio.create_task(self._renew_lease(record.run_id, owner, worker))
        try:
            record.status = "running"
            self._repository.update(record.run_id, "running")
            async for packet in MultiAgentService.process_task(
                request, user_id=record.user_id, flag=True, run_id=record.run_id,
                resume_checkpoint=resume_checkpoint,
            ):
                await self._publish(record, packet)
            if not record.saw_finish:
                record.status, record.error = "failed", "Agent 响应流缺少 FINISHED 结束包"
            elif record.finish_reason == "NORMAL":
                record.status, record.error = "completed", None
            else:
                record.status = "failed"
                record.error = record.error or "Agent 响应以错误状态结束"
            self._repository.update(record.run_id, record.status, record.error)
        except asyncio.CancelledError:
            record.status = "cancelled"
            try:
                self._repository.update(record.run_id, "cancelled", "任务已取消")
            except TaskLeaseLost:
                pass
            raise
        except TaskLeaseLost:
            record.status = "failed"
            logger.warning("停止失去租约的任务 %s", record.run_id)
        except Exception as exc:
            record.status, record.error = "failed", str(exc)
            try:
                self._repository.update(record.run_id, "failed", str(exc))
            except TaskLeaseLost:
                pass
            logger.exception("后台任务 %s 执行失败", record.run_id)
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except (asyncio.CancelledError, Exception):
                pass
            try:
                self._repository.release_lease(record.run_id, owner)
            except Exception:
                logger.exception("任务租约释放失败 %s", record.run_id)
            finally:
                execution_lease.reset(token)

    async def _renew_lease(self, run_id: str, owner: str, worker) -> None:
        while True:
            await asyncio.sleep(max(0.1, self._lease_seconds / 3))
            try:
                renewed = self._repository.renew_lease(run_id, owner, self._lease_seconds)
            except Exception:
                logger.exception("任务 %s 租约续期异常", run_id)
                renewed = False
            if not renewed:
                worker.cancel()
                return

    async def _publish(self, record: TaskRecord, packet: str | None) -> None:
        if packet is not None:
            self._repository.append_event(record.run_id, packet)
            record.packets.append(packet)
            try:
                payload = json.loads(packet.removeprefix("data: ").strip())
                content = payload.get("content") or {}
                if content.get("contentType") == "sagegpt/plan":
                    record.checkpoint = content
                    self._repository.save_checkpoint(record.run_id, content)
                if payload.get("status") == "FINISHED":
                    metadata = payload.get("metadata") or {}
                    record.saw_finish = True
                    record.finish_reason = metadata.get("finishReason")
                    if record.finish_reason != "NORMAL":
                        record.error = metadata.get("errorMessage") or record.error
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
            if len(record.packets) > self.MAX_PACKETS:
                del record.packets[:-self.MAX_PACKETS]

    async def subscribe(self, run_id: str, user_id: str):
        # SQLite is the replay and live source for every worker. No unbounded
        # per-subscriber queue, and no dependence on a process-local task cache.
        cursor = 0
        saw_finish = False
        while True:
            row = self._repository.get(run_id, user_id)
            if row is None:
                return
            if row["status"] == "running" and (row.get("lease_expires_at") or 0) <= time.time():
                self._repository.fail_expired(run_id, "执行租约已过期，未自动重放")
                continue
            events = self._repository.event_rows(run_id, cursor, limit=100)
            for event in events:
                cursor = event["id"]
                try:
                    payload = json.loads(event["packet"].removeprefix("data: ").strip())
                    saw_finish = saw_finish or payload.get("status") == "FINISHED"
                except (TypeError, ValueError):
                    pass
                yield event["packet"]
            if len(events) == 100:
                continue
            if row["status"] in {"completed", "failed", "cancelled"}:
                # Status was read before events, so every terminal packet is included.
                if not saw_finish and row["status"] != "completed":
                    packet = ResponseFactory.build_finish(finish_reason=StopReason.ERROR, error_message=row.get("error") or "任务已停止")
                    yield "data: " + packet.model_dump_json() + "\n\n"
                return
            await asyncio.sleep(0.1)

    def get(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        row = self._repository.get(run_id, user_id)
        if row is None:
            return None
        if row["status"] == "running" and (row.get("lease_expires_at") or 0) <= time.time():
            self._repository.fail_expired(run_id, "执行租约已过期，未自动重放")
            row = self._repository.get(run_id, user_id)
        record = self._record_from_row(row, packets=self._repository.events(run_id))
        for packet in reversed(record.packets):
            try:
                payload = json.loads(packet.removeprefix("data: ").strip())
                if payload.get("status") == "FINISHED":
                    record.finish_reason = (payload.get("metadata") or {}).get("finishReason")
                    break
            except (TypeError, ValueError):
                continue
        return self._summary(record)

    def list_for_session(self, session_id: str, user_id: str) -> list[dict[str, Any]]:
        return [self.get(row["run_id"], user_id)
                for row in self._repository.list_for_session(session_id, user_id)]

    async def cancel(self, run_id: str, user_id: str) -> bool:
        if not self._repository.request_cancel(run_id, user_id):
            return False
        record = self._tasks.get(run_id)
        if record and record.task and not record.task.done():
            record.task.cancel()
        return True

    @staticmethod
    def _summary(record: TaskRecord) -> dict[str, Any]:
        return {"run_id": record.run_id, "session_id": record.session_id, "status": record.status,
                "created_at": record.created_at, "packet_count": len(record.packets), "error": record.error,
                "finish_reason": record.finish_reason, "checkpoint": record.checkpoint}

    @staticmethod
    def _record_from_row(row: dict, *, packets: list[str] | None = None) -> TaskRecord:
        checkpoint = None
        if row.get("checkpoint_json"):
            try:
                checkpoint = json.loads(row["checkpoint_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                checkpoint = None
        return TaskRecord(
            row["run_id"], row["user_id"], row["session_id"], row["created_at"], row["status"],
            packets=packets or [], error=row.get("error"), checkpoint=checkpoint,
        )

    def _prune_locked(self) -> None:
        if len(self._tasks) <= self.MAX_TASKS:
            return
        finished = sorted((r for r in self._tasks.values() if r.status in {"completed", "failed", "cancelled"}),
                          key=lambda r: r.created_at)
        for record in finished[: max(0, len(self._tasks) - self.MAX_TASKS)]:
            self._tasks.pop(record.run_id, None)


task_manager = TaskManager()
