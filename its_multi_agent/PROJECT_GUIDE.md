# ITS 多智能体系统指南

面试与简历材料见 [Harness Engineering 综合工程化面试总指南（2026-10-07 核对）](../artifacts/interview/ITS_Harness工程化面试指南_2026-10-06.md)，版本入口见 [interview/README](../artifacts/interview/README.md)。总指南对照当前工作区（含未提交实现），覆盖真实请求链、Schema、上下文/记忆、多格式入库与混合 RAG、Coordinator/Fork、工具策略、任务/checkpoint、SSE、前端、存储部署、评测、面试追问和演示；同时标明当前缺口与验证范围。历史文件仅作为快照保留。

本页提供开发入口与运行约定；完整机制、事实依据和面试表达统一以总指南为主。本页的命令是重新验证的入口，本轮没有执行完整产品测试或真实模型联调，也没有修改业务代码。

## 项目结构

ITS 由五部分组成：

- `backend/app/`：认证、会话、长期记忆、模型配置、插件和 Agent 调度 API。
- `backend/knowledge/`：文档入库、混合检索、重排和知识库问答服务。
- `front/agent_web_ui/`：用户聊天客户端，可选择服务端模型配置和工具插件。
- `front/knowlege_platform_ui/`：管理员知识库界面。
- `harness/`：独立于业务 UI 的场景评测和回归检查。

## 请求流程

1. 用户登录后获得 JWT（源码默认有效期 480 分钟），用户身份由后端认证依赖确定。
2. 客户端将问题、会话/项目 ID、模型配置、插件选择与确认、工作模式和可选附件/设备位置发送到 `POST /api/query`。
3. `TaskManager` 创建独立后台任务并持久化请求状态，HTTP 连接负责订阅 SSE；`MultiAgentService` 处理记忆、用户消息、近期上下文和附件。
4. 普通查询由 `GroundingWorkflow` 规划知识库、联网、附件等来源并检查证据；计划模式或复杂任务触发后，由 LangGraph 规划节点生成计划，再由 `PlanExecutor` 按依赖波次执行并验收资料、技术、服务或工程步骤。Fork 并行配置启用时可并发处理就绪步骤；当前全部就绪步骤均为 coding 时仍可能同批并发，尚未强制工作区互斥。
5. 主 Agent 汇总结果；后端通过 SSE 发送 `THINKING`、`PROCESS` 和 `ANSWER`。有引用时发送 `sagegpt/sources` 并随助手消息归档；复杂任务发送 `sagegpt/plan` 阶段快照。结构化工具名、Agent 名和执行者信息供 Harness 观察。
6. 回答流程正常完成发送 `FINISHED/NORMAL`；受控异常路径发送 `FINISHED/ERROR`，任务管理器记录终态。取消当前只更新任务状态并关闭订阅，没有独立的 `FINISHED/CANCELLED` 包。响应流程正常完成不等于复杂计划的所有步骤均成功，还需查看计划中的完成、阻塞、失败和跳过状态。
7. 最终 Runner 答案成功保存后，再提交异步长期记忆提取；Grounding 直接返回澄清/不可用答复时不会经过这次提交。准备阶段也会 await 提取本轮明确用户信息，而且发生在项目权限校验之前，不能把记忆处理全部视为回答之后执行。

应用层自动重试只覆盖最终回答流尚未产生语义输出、尚未观察到工具调用的临时故障，最多重试一次；前置规划、步骤执行和上下文准备不在该重试循环内。

## 后台任务、恢复与并发边界

后台任务与 SSE 订阅解耦，客户端断连不会自动取消任务。后端提供 `GET /api/tasks/{run_id}`、`GET /api/tasks/{run_id}/events`、`POST /api/tasks/{run_id}/cancel` 和 `POST /api/tasks/{run_id}/resume`，保存任务状态、事件和计划展示快照。复杂任务有 task run ID 时，在规划后、每个执行波次结束后和最终状态处尝试保存独立的执行 checkpoint，包括计划、步骤状态、已验收结果和来源摘要；写失败只记日志，波次中断可能丢失尚未保存的进度。启动时恢复可用的排队请求，将已运行但被重启打断的请求标记为失败，避免自动重放可能有副作用的工具操作；依赖临时模型凭据的请求不能直接恢复。

步骤 checkpoint 目前是应用层持久化状态，不是 LangGraph checkpointer。符合恢复条件的失败或取消任务可通过 `POST /api/tasks/{run_id}/resume` 显式恢复；程序重新检查完成记录，跳过已保存且可接受的 completed 结果，恢复前重新校验请求身份、工作区、插件确认、模型和 checkpoint 版本。未完成步骤含服务或编码执行器时会被拒绝，避免重复外部操作。计划 partial 但 task completed 的任务当前没有此恢复入口。
聊天前端已接入任务列表、状态、事件跟随/回放、恢复按钮和后台取消；断流后有限自动重订阅，并在本次请求内按 JSON packet.id 去重。后端仍是全量事件回放，没有增量游标或跨页面持久去重；恢复重用 run_id 并保留旧终态事件，尚需 attempt 边界和恢复验收。取消 asyncio 任务也不保证已启动的阻塞工具或子进程立即停止。

当前具有 asyncio 多请求处理、同步操作线程池卸载、入库线程池、连接池和 Redis 缓存。任务订阅队列没有容量上限，SSE 事件仍逐条同步写入 SQLite，同会话并发和多实例任务协调尚未完善。`MAX_TASKS = 100` 仅用于清理已结束任务，不代表支持或限制为 100 并发；吞吐和延迟尚需压测。

## Agent 与工具

- `multi_agent/orchestrator_agent.py`：创建主调度 Agent；非 Fork 加载 `orchestrator_v2.md`，Fork 使用 `fork_runtime.py` 中的固定模板和 `fork_base.md`。
- `multi_agent/agent_factory.py`：按请求创建工具集合，不再维护静态 `AGENT_TOOLS`。
- `multi_agent/technical_agent.py`：复杂任务中的技术/资料分析执行者，使用交接的结果与已审查证据。
- `multi_agent/service_agent.py`：地图和服务站子 Agent。
- `multi_agent/planning_agent.py`：生成受约束的任务计划；`services/task_graph.py` 提供请求级规划图，`services/plan_executor.py` 负责步骤执行。
- `multi_agent/coding_agent.py`：工程修改子 Agent，只在能力已配置且请求显式选择插件时可用。
- `services/agent_hooks.py`：生命周期观察与工具策略扩展；`evaluate_tool()` 统一处理白名单、确认、风险和副作用等级，本地工具、编码工具和请求级地图 MCP 共用该判定；基础策略审计摘要写入任务数据库。观察型 Hook 异常隔离，但自定义策略 Hook 的后续拒绝/异常未补写最终审计，不能把基础许可记录当成工具成功证明；服务端签名确认、幂等键和补偿事务仍待完善。
- `plugins/registry.py`：定义客户端可见的插件及其工具集合。

当前原子工具包括知识库查询、联网搜索、位置解析、服务站查询、地图导航、受限文件输出和工程工作区操作。子 Agent 只用于确实需要多步推理的任务。

工程修改插件默认关闭。服务端配置 `CODE_WORKSPACE_ROOT` 后，用户仍须在当前请求中显式启用并确认“工程修改”，通过当前项目及所选模型的能力校验，工具才可执行。工程子 Agent 可列出、读取和搜索允许类型的文本文件，通过唯一原文匹配执行临时文件替换或创建新文件，并运行 `CODE_CHECK_COMMANDS_JSON` 中由管理员预设的检查；工具返回 diff、检查退出码与输出。路径解析限制在授权根目录内，并过滤 `.git`、虚拟环境、依赖和运行产物等目录。模型不能直接提交任意 Shell 命令，但预设检查仍会执行仓库代码；当前不是操作系统沙箱，扩展名过滤也不等于完整秘密识别，代码根目录尚未按用户独立隔离。

文件输出由 `create_file` 工具和 `/api/files` 接口组成。产物默认按用户和文件 ID 隔离保存到 `backend/app/runtime/files/{user_id}/{file_id}/`，会话和 `run_id` 是记录的关联信息，同时保存大小和过期时间。当前仅允许 UTF-8 的 `.txt`、`.md`、`.json`、`.csv`，单文件上限 2,000,000 字节，默认保留 7 天；下载、列表和删除都要求登录用户身份，其他用户无法访问。聊天前端已有文件列表、下载和删除入口；Agent 创建需要启用并确认文件插件，实际可调用性还取决于 Fork 与路由装配，工具返回 `file_id` 和 `/api/files/{id}/download` 下载地址。直接 `POST /api/files` 检查 JWT 和创建参数，不检查 Agent 插件确认。过期清理依赖访问，没有独立定时清理或用户总配额；默认文件目录还未挂 Compose 持久卷。

## 模型配置

客户端可选择 `model_profile_id`，也可提交个人或临时模型配置；列表接口不返回密钥。服务端模型由 `.env` 默认字段或 `MODEL_PROFILES_JSON` 提供。

通过 `model_factory` 创建的应用聊天客户端会校验管理员完整端点白名单，并禁止跟随 HTTP 重定向。额外端点通过 `MODEL_ALLOWED_BASE_URLS_JSON` 指定，例如 `["https://provider.example/v1"]`；需要本地模型时显式添加对应地址。用户个人/临时 profile 不能自行指定任意内网或其他供应商端点。长期记忆提取/embedding 和独立知识服务使用自己的管理员配置客户端，未统一经过这一工厂，不能泛称所有 SDK 客户端都经过相同白名单和重定向策略。

个人模型凭据使用独立 Fernet 密钥，默认保存于模型数据库旁的 `.key` 文件。数据库与密钥必须一起备份，不应提交 Git。也可以配置 `MODEL_PROFILE_ENCRYPTION_KEY` 或 `MODEL_PROFILE_ENCRYPTION_KEY_PATH`。首次启动会用当前 JWT 密钥迁移旧凭据；如果 JWT 已轮换，需用 `MODEL_PROFILE_LEGACY_JWT_SECRET` 提供旧值完成迁移。迁移失败会明确报错并保留原始密文。迁移后轮换 JWT 不再影响模型凭据。

每个 profile 描述：

- 模型名称和供应商；
- 可承担的角色：`chat`、`reasoning`、`vision`；
- 是否支持工具、视觉、推理和流式输出；
- 可选的 `context_window_tokens` 与 `max_output_tokens`。

每次最终回答前，系统估算系统指令、当前 Agent 工具定义、历史消息、记忆、附件和检索证据的 token 数，并为输出和安全余量预留空间。超出输入预算时先移除较早消息及可选记忆，再截断附件和检索片段，必要时移除旧摘要并截断任务结果；当前问题受保护。此过程只裁剪本次发给模型的副本，不改写会话归档或长期记忆。未设置单模型容量时，默认上下文窗口为 32768 token、输出上限为 4096 token，安全余量为 1024 token；小窗口会进一步约束输出。图片按 `CONTEXT_IMAGE_TOKEN_ESTIMATE` 估算。安装 `tiktoken` 后按模型编码计数，不支持的模型名回退到 `cl100k_base`；没有该依赖时使用字符估算，结果属于近似值。管理员可通过 `MODEL_CONTEXT_WINDOW_TOKENS_DEFAULT`、`MODEL_MAX_OUTPUT_TOKENS_DEFAULT`、`CONTEXT_TOKEN_SAFETY_MARGIN` 和 `CONTEXT_IMAGE_TOKEN_ESTIMATE` 修改默认值；profile 可单独覆盖窗口和输出上限。运行时 MCP schema、嵌套 Agent-as-tool 和每次工具续轮未统一预算，也没有整任务费用硬限额。

`AGENT_FORK_MODE_ENABLED=true` 时，主 Agent 与复杂任务的技术、业务和工程分支复用同一套固定 Fork 模板（模型、固定系统提示词、函数工具定义顺序和输出配置）。当前角色、步骤、证据和权限作为末尾 `fork_branch` 消息传入；工具函数仍根据请求上下文的白名单拒绝未授权能力，但存在空路由集合回退和服务分支权限较宽等收窄缺口，详见总指南第 9/11 节。不同分支的输入裁剪及 MCP 工具集合也可能改变最终请求结构。该模式为供应商前缀 Prompt Cache 提供复用条件，是否命中及命中量由模型服务商决定，当前没有实际 cached-token 测量。

不要把 API Key 返回给前端，也不要将密钥写入日志。

## 数据存储

- 用户：SQLite `users.db`。
- 会话：SQLite `sessions.db`，保存完整消息；推理只加载摘要和最近消息。
- 长期记忆：默认 SQLite，可选 Milvus。
- 知识库：文档登记、关键词索引和向量索引共同组成检索数据。

当前默认工作区主键、任务的 workspace 范围和知识空间 ACL 仍有缺口，不能把“按用户查询”统一解释为所有资源都具备完整的用户/项目授权。知识空间/领域分区和内部服务 token 也不能代替终端用户 ACL，依据见总指南第 13/18 节。

`GET /api/user_sessions?page=1&page_size=30` 只返回分页元数据（标题、消息数、更新时间、next_page），不再内嵌全部归档。`GET /api/sessions/{session_id}/messages?page_size=20&before_id=...` 返回按时间正序的一页消息、引用快照及 `next_before_id`；未提供游标时取最近一页。两者均按登录用户隔离。

入库任务的重试和文档状态在同一事务提交，任务领取有状态条件。实际索引写入、删除和重新上传按文档加跨进程锁，任务绑定上传代次，阻止旧任务写回新版本或已删除资料。Milvus 与 SQLite 无跨库事务，部分失败时只做补偿尝试；检索仍未统一按 registry active generation 过滤，不能将登记状态当成残留索引一定不可见的证明。所有本地进程应共享同一注册表路径，升级时需停止旧代码的 worker 后再启用新 worker。

`backend/app/data/`、`backend/app/runtime/`、日志、Chroma 数据和各类构建目录都是运行产物，不应提交到 Git。

## 错误处理约定

- 面向用户的错误使用中文，不返回异常对象、数据库信息、内部路径或供应商原始响应。
- 普通 HTTP 接口使用合适的 4xx/5xx 状态码和 `detail`。
- SSE 的受控异常路径应发送 `FINISHED/ERROR` 结束包；当前取消和进程突然退出不保证通过相同事件通知，客户端还需读取任务状态。
- 只有明确可重试、尚未输出内容且未调用工具的故障可以自动重试。
- 日志保留异常类型和服务位置；敏感响应只在受控调试环境检查。

## 本地验证

以下命令从仓库根目录运行，假设各自虚拟环境/依赖已安装且必要配置有效。这些是重新验证的命令，不是本轮通过记录；建议新开测试终端，避免临时环境变量继续影响正常服务。

应用后端测试：

```powershell
$taskTestRoot = Join-Path $env:TEMP ('its-tests-' + [guid]::NewGuid().ToString('N'))
$env:USER_SQLITE_PATH = Join-Path $taskTestRoot 'users.db'
$env:SESSION_SQLITE_PATH = Join-Path $taskTestRoot 'sessions.db'
$env:TASK_SQLITE_PATH = Join-Path $taskTestRoot 'tasks.db'
$env:WORKSPACE_SQLITE_PATH = Join-Path $taskTestRoot 'workspaces.db'
$env:MODEL_PROFILE_SQLITE_PATH = Join-Path $taskTestRoot 'models.db'
$env:MEMORY_SQLITE_PATH = Join-Path $taskTestRoot 'memory.db'
$env:MEMORY_BACKEND = 'sqlite'
& 'its_multi_agent/backend/app/.venv/Scripts/python.exe' -X utf8 -m unittest discover -s its_multi_agent/backend/app/tests -v
& 'its_multi_agent/backend/app/.venv/Scripts/python.exe' -X utf8 -m unittest its_multi_agent.harness.test_harness -v
```

运行知识库测试：

```powershell
$taskKnowledgeRoot = Join-Path $env:TEMP ('its-tests-kb-' + [guid]::NewGuid().ToString('N'))
$env:DOCUMENT_REGISTRY_PATH = Join-Path $taskKnowledgeRoot 'documents.db'
$env:LEXICAL_INDEX_PATH = Join-Path $taskKnowledgeRoot 'lexical.db'
$env:INGESTION_TASK_DB_PATH = Join-Path $taskKnowledgeRoot 'tasks.db'
& 'its_multi_agent/backend/knowledge/.venv/Scripts/python.exe' -X utf8 -m unittest discover -s its_multi_agent/backend/knowledge/test -v
```

两个前端从仓库根目录运行：

```powershell
npm --prefix .\its_multi_agent\front\agent_web_ui run check
npm --prefix .\its_multi_agent\front\knowlege_platform_ui run check
```

Harness 按 [Harness README](harness/README.md) 执行，真实服务场景可能调用模型与外部服务；替身测试通过不能证明真实质量、HTTP 任务恢复或容量。启动入口、演示脚本及部署前核对项统一见总指南第 17 节。发布前应完成两个后端、两个前端和 Harness 的适当检查，并按实际启用能力补做真实联调。
