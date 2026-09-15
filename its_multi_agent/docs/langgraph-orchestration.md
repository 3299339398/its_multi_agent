# LangGraph 编排

复杂任务使用请求级 LangGraph 状态图承载 planner 状态和后续执行边界；普通聊天仍使用现有 OpenAI Agents SDK。

图的节点为 `planner -> executor -> END`。Planner 节点调用现有受约束的 `PlanningAgent`，校验步骤 ID、依赖、工具权限和用户约束后写入图状态。执行阶段由 `PlanExecutor` 按依赖顺序运行技术或服务子 Agent，保留每步超时、轮数、结果长度和验收规则，并继续发送原有 SSE 进度事件。

图状态是请求级对象，不跨用户共享，也不直接持久化模型内部状态。会话、任务结果和长期记忆仍由现有服务统一管理。

依赖已加入 `backend/app/requirements.txt` 和 `setup.py`，运行环境需要安装 `langgraph`。
