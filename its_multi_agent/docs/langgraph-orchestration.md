# LangGraph 编排

核对日期：2026-09-17。

复杂任务使用请求级 LangGraph 状态图承载 planner 状态和后续执行边界；普通聊天仍使用现有 OpenAI Agents SDK。

复杂任务的执行分支可通过 `AGENT_FORK_MODE_ENABLED` 使用共享 Fork 模板。LangGraph 仍只管理计划状态；Fork 模板负责让父、技术、业务和工程 Agent 复用固定请求前缀，步骤数据和权限追加在 `fork_branch` 消息中。工具权限仍由 `AgentRequestContext.allowed_tools` 和工具内部策略控制。

构建函数默认定义 `planner -> executor -> END`，但当前聊天主路径通过 `build_task_graph(executor, execute=False)` 实际运行 `planner -> END`。Planner 节点调用受约束的 `PlanningAgent`，校验步骤 ID、依赖、工具权限和用户约束后写入图状态。

规划完成后，`PlanExecutor` 在图外按依赖层级执行资料、技术、服务或工程执行者，保留执行超时、轮数、结果长度和验收规则。启用 `AGENT_PARALLEL_FORK_ENABLED` 且存在 Fork 模板时，同一依赖层中互不依赖的资料/服务分支会组成一个并行波次；工程分支因共享工作区仍保持串行。每个波次完成后发送 SSE 计划快照，依赖步骤只能在前置结果验收通过后启动。

图状态是请求级对象，不跨用户共享；没有接入 LangGraph 持久化 checkpointer。TaskManager 单独保存后台任务状态、事件和计划快照，PlanExecutor 还会把计划、步骤状态、已验收结果和来源摘要保存到应用层 execution checkpoint。失败或取消的任务可以由用户通过任务恢复接口显式触发续跑：恢复前重新校验身份和权限，已完成步骤跳过，服务和编码等未具备幂等保证的步骤拒绝恢复。会话、任务结果和长期记忆由相应业务服务管理。

依赖已加入 `backend/app/requirements.txt` 和 `setup.py`，运行环境需要安装 `langgraph`。
