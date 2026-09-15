# ITS Harness Engineering

Harness 是模型之外、负责边界、工具、编排、状态、验证和恢复的运行系统。`harness/`
目录只是其中的离线契约评测层，不能单独代表完整 Harness。

## 六层能力基线

| 层级 | 已实现 | 下一验收目标 |
|---|---|---|
| L1 信息边界 | 角色 Prompt、Pydantic 请求约束、用户/项目/附件隔离、模型端点白名单 | 统一策略清单、Prompt 版本与来源标签 |
| L2 工具系统 | 原子工具、MCP 生命周期、插件白名单、结果规范化、工具 Hook | 服务端确认票据、幂等键、副作用等级 |
| L3 执行编排 | 计划 Schema、依赖、步骤超时、步骤验收、部分成功 | LangGraph 条件边、并行执行、图级 checkpoint |
| L4 记忆状态 | SQLite 会话和任务、Redis 上下文、SQLite/Milvus 长期记忆 | 从步骤 checkpoint 续跑，而不是重跑整次请求 |
| L5 评估观测 | 契约场景、答案路由指标、结构化 SSE、延迟日志 | 全链路 trace、运行指标、线上失败样本回灌 |
| L6 约束恢复 | 输入/来源/长度限制、fail-closed、有限安全重试、健康检查 | 全局预算、退避/熔断、补偿事务和降级矩阵 |

## Hook 中间件

`backend/app/services/agent_hooks.py` 提供统一的 `AgentHookManager`。业务层事件包括
`before_run`、`after_run`、`on_error` 和 `on_finish`；流处理层事件包括 `tool_call`、
`tool_output` 和 `agent_transition`。`before_tool_call` Hook 可返回 `False` 或
`{"allow": false, "reason": "..."}` 阻断工具。Hook 支持同步或异步函数，可在应用启动时
注册审计、指标、限流和策略检查逻辑；观察型 Hook 异常会被隔离并记录。

任务恢复只会自动重新排队尚未开始执行的 `queued` 任务。服务重启时处于 `running` 状态的
任务会标记为失败，不会从头重放，以避免重复外部副作用；复杂任务的步骤级 checkpoint
续跑仍需后续实现。

## 发布门禁

发布必须满足：

1. 应用、知识库、前端和 `harness/` 的离线测试全部通过。
2. 每个 SSE Agent 运行必须以一个 `FINISHED` 包结束；`ERROR` 不得记录为 completed。
3. 涉及外部副作用的工具必须有确认、幂等和审计信息。
4. 证据型回答必须经过来源验证；证据不足时停止生成事实结论。
5. 新增能力必须提供成功、依赖失败、超时、取消和越权场景。

## 完成定义

只有当六层均有代码所有者、自动测试、运行指标和故障处置方式时，项目才称为“生产级
Harness”。当前阶段可表述为“已落地 Harness Engineering 核心架构”。

## 实施顺序

- P0：任务终态正确性、持久化查询、测试全绿。
- P1：服务端工具确认、幂等执行、全链路可观测性。
- P2：LangGraph checkpoint 续跑、任务级预算和熔断。
- P3：真实模型基准、人工语义评审和线上失败样本回归。
