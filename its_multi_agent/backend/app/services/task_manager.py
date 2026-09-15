"""Background task lifecycle for chat runs.

The HTTP/SSE connection is only a subscription.  The actual agent run is
owned by an asyncio task, so a client switching sessions or reconnecting does
not cancel work already started.
"""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.services.agent_service import MultiAgentService
from its_multi_agent.backend.app.repositories.sqlite_task_repository import task_repository
from its_multi_agent.backend.app.schemas.request import ChatMessageRequest


@dataclass
class TaskRecord:
    run_id: str
    user_id: str
    session_id: str
    created_at: float = field(default_factory=time.time)
    status: str = "queued"
    packets: list[str] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
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

    async def start(self, request, user_id: str) -> str:
        record = TaskRecord(str(uuid.uuid4()), user_id, request.context.session_id or "default_session")
        async with self._lock:
            self._tasks[record.run_id] = record
            self._prune_locked()
        self._repository.create(record.run_id, user_id, record.session_id, request, record.created_at)
        record.task = asyncio.create_task(self._run(record, request), name=f"agent-run-{record.run_id}")
        return record.run_id

    async def resume_pending(self) -> None:
        """Resume queued/running tasks left by a previous process."""
        for row in self._repository.pending():
            try:
                if row["status"] == "running":
                    # A process crash may have left external tool calls half
                    # complete. Replaying the whole request is unsafe; leave
                    # it failed for an explicit, idempotent user retry.
                    self._repository.update(row["run_id"], "failed", "服务重启中断任务，未自动重放")
                    continue
                payload = json.loads(row["request_json"])
                if payload.get("_resume_blocked"):
                    self._repository.update(row["run_id"], "failed", "任务包含不可恢复的临时模型凭据")
                    continue
                request = ChatMessageRequest.model_validate(payload)
                record = self._record_from_row(row)
                record.status = "queued"
                record.packets = self._repository.events(record.run_id)
                self._tasks[record.run_id] = record
                record.task = asyncio.create_task(self._run(record, request), name=f"agent-run-{record.run_id}")
            except Exception as exc:
                self._repository.update(row["run_id"], "failed", str(exc))
                logger.exception("恢复任务 %s 失败", row["run_id"])

    async def _run(self, record: TaskRecord, request) -> None:
        record.status = "running"
        self._repository.update(record.run_id, "running")
        try:
            async for packet in MultiAgentService.process_task(
                request, user_id=record.user_id, flag=True, run_id=record.run_id
            ):
                await self._publish(record, packet)
            if not record.saw_finish:
                record.status = "failed"
                record.error = "Agent 响应流缺少 FINISHED 结束包"
            elif record.finish_reason == "NORMAL":
                record.status = "completed"
                record.error = None
            else:
                record.status = "failed"
                record.error = record.error or "Agent 响应以错误状态结束"
            self._repository.update(record.run_id, record.status, record.error)
        except asyncio.CancelledError:
            record.status = "cancelled"
            self._repository.update(record.run_id, "cancelled")
            raise
        except Exception as exc:  # process_task normally emits error packets itself
            record.status = "failed"
            record.error = str(exc)
            self._repository.update(record.run_id, "failed", record.error)
            logger.exception("后台任务 %s 执行失败", record.run_id)
        finally:
            await self._publish(record, None)

    async def _publish(self, record: TaskRecord, packet: str | None) -> None:
        if packet is not None:
            record.packets.append(packet)
            self._repository.append_event(record.run_id, packet)
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
        for queue in tuple(record.subscribers):
            queue.put_nowait(packet)

    async def subscribe(self, run_id: str, user_id: str):
        record = self._tasks.get(run_id)
        if record is None or record.user_id != user_id:
            row = self._repository.get(run_id, user_id)
            if row is None:
                return
            record = self._record_from_row(row, packets=self._repository.events(run_id))
            self._tasks[run_id] = record
        queue: asyncio.Queue = asyncio.Queue()
        record.subscribers.add(queue)
        try:
            for packet in record.packets:
                yield packet
            if record.status in {"completed", "failed", "cancelled"}:
                return
            while True:
                packet = await queue.get()
                if packet is None:
                    return
                yield packet
        finally:
            record.subscribers.discard(queue)

    def get(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        record = self._tasks.get(run_id)
        if record is not None and record.user_id != user_id:
            return None
        if record is None:
            row = self._repository.get(run_id, user_id)
            if row is None:
                return None
            record = self._record_from_row(row)
            record.packets = self._repository.events(run_id)
            self._tasks[run_id] = record
        return self._summary(record)

    def list_for_session(self, session_id: str, user_id: str) -> list[dict[str, Any]]:
        records = [r for r in self._tasks.values() if r.user_id == user_id and r.session_id == session_id]
        persisted = self._repository.list_for_session(session_id, user_id)
        known = {r.run_id for r in records}
        records.extend(self._record_from_row(row, packets=self._repository.events(row["run_id"]))
                       for row in persisted if row["run_id"] not in known)
        return [self._summary(r) for r in sorted(records, key=lambda item: item.created_at, reverse=True)]

    async def cancel(self, run_id: str, user_id: str) -> bool:
        record = self._tasks.get(run_id)
        if record is None or record.user_id != user_id:
            return False
        if record.task and not record.task.done():
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
