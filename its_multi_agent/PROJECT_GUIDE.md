# ITS 多智能体系统指南

## 项目结构

ITS 由五部分组成：

- `backend/app/`：认证、会话、长期记忆、模型配置、插件和 Agent 调度 API。
- `backend/knowledge/`：文档入库、混合检索、重排和知识库问答服务。
- `front/agent_web_ui/`：用户聊天客户端，可选择服务端模型配置和工具插件。
- `front/knowlege_platform_ui/`：管理员知识库界面。
- `harness/`：独立于业务 UI 的场景评测和回归检查。

## 请求流程

1. 用户登录后获得短期 JWT，用户身份由后端令牌确定。
2. 客户端将问题、会话 ID、模型配置 ID、启用的插件和可选设备位置发送到 `/api/query`。
3. `MultiAgentService` 写入一次用户消息，召回长期记忆并构建有限长度的上下文。
4. `GroundingWorkflow` 先规划知识库、联网、附件等来源并检查证据，主 Agent 基于审查后的原文回答和分析复杂故障；需要导航时再调用服务站子 Agent。
5. 后端通过 SSE 发送 `THINKING`、`PROCESS` 和 `ANSWER` 数据。有引用时，先发送 `sagegpt/sources` 快照，并随助手消息归档；PROCESS 可带结构化工具名和 Agent 名用于评测。
6. 正常完成发送 `FINISHED/NORMAL`；失败发送中文错误答案和 `FINISHED/ERROR`。
7. 最终答案成功保存后，再异步提取长期记忆。

自动重试只覆盖尚未产生输出的临时模型故障，并且最多重试一次。用户消息、记忆提取和上下文准备不会随重试重复执行。

## Agent 与工具

- `multi_agent/orchestrator_agent.py`：创建主调度 Agent，加载 `orchestrator_v2.md`。
- `multi_agent/agent_factory.py`：按请求创建工具集合，不再维护静态 `AGENT_TOOLS`。
- `multi_agent/technical_agent.py`：保留的独立构造模块；当前聊天入口的诊断已统一到证据回答流程，不再注册重复诊断工具。
- `multi_agent/service_agent.py`：地图和服务站子 Agent。
- `plugins/registry.py`：定义客户端可见的插件及其工具集合。

当前原子工具包括知识库查询、联网搜索、位置解析、服务站查询、地图导航和受限文件输出。子 Agent 只用于确实需要多步推理的任务。

文件输出由 `create_file` 工具和 `/api/files` 接口组成。产物按用户和任务隔离保存到 `runtime/files/{user_id}/{file_id}/`，并记录会话、`run_id`、大小和过期时间。当前仅允许 UTF-8 的 `.txt`、`.md`、`.json`、`.csv`，单文件上限 2 MB，默认保留 7 天；下载、列表和删除都要求登录用户身份，其他用户无法访问。Agent 通过文件插件启用该工具，工具返回 `file_id` 和 `/api/files/{id}/download` 下载地址。

## 模型配置

客户端可选择 `model_profile_id`，也可提交个人或临时模型配置；列表接口不返回密钥。服务端模型由 `.env` 默认字段或 `MODEL_PROFILES_JSON` 提供。

所有模型客户端只接受管理员已配置的完整服务地址，并禁止跟随 HTTP 重定向。额外端点通过 `MODEL_ALLOWED_BASE_URLS_JSON` 指定，例如 `["https://provider.example/v1"]`；需要本地模型时显式添加对应地址。用户不能自行指定任意内网或其他供应商端点。

个人模型凭据使用独立 Fernet 密钥，默认保存于模型数据库旁的 `.key` 文件。数据库与密钥必须一起备份，不应提交 Git。也可以配置 `MODEL_PROFILE_ENCRYPTION_KEY` 或 `MODEL_PROFILE_ENCRYPTION_KEY_PATH`。首次启动会用当前 JWT 密钥迁移旧凭据；如果 JWT 已轮换，需用 `MODEL_PROFILE_LEGACY_JWT_SECRET` 提供旧值完成迁移。迁移失败会明确报错并保留原始密文。迁移后轮换 JWT 不再影响模型凭据。

每个 profile 描述：

- 模型名称和供应商；
- 可承担的角色：`chat`、`reasoning`、`vision`；
- 是否支持工具、视觉、推理和流式输出。

不要把 API Key 返回给前端，也不要将密钥写入日志。

## 数据存储

- 用户：SQLite `users.db`。
- 会话：SQLite `sessions.db`，保存完整消息；推理只加载摘要和最近消息。
- 长期记忆：默认 SQLite，可选 Milvus。
- 知识库：文档登记、关键词索引和向量索引共同组成检索数据。

`GET /api/user_sessions?page=1&page_size=30` 只返回分页元数据（标题、消息数、更新时间、next_page），不再内嵌全部归档。`GET /api/sessions/{session_id}/messages?page_size=20&before_id=...` 返回按时间正序的一页消息、引用快照及 `next_before_id`；未提供游标时取最近一页。两者均按登录用户隔离。

入库任务的重试和文档状态在同一事务提交，任务领取有状态条件。实际索引写入、删除和重新上传按文档加跨进程锁，任务绑定上传代次；旧任务不能写回新版本或已删除资料。所有本地进程应共享同一注册表路径，升级时需停止旧代码的 worker 后再启用新 worker。

`backend/app/data/`、`backend/app/runtime/`、日志、Chroma 数据和各类构建目录都是运行产物，不应提交到 Git。

## 错误处理约定

- 面向用户的错误使用中文，不返回异常对象、数据库信息、内部路径或供应商原始响应。
- 普通 HTTP 接口使用合适的 4xx/5xx 状态码和 `detail`。
- SSE 即使失败也必须发送 `FINISHED/ERROR` 结束包。
- 只有明确可重试、尚未输出内容且未调用工具的故障可以自动重试。
- 日志保留异常类型和服务位置；敏感响应只在受控调试环境检查。

## 本地验证

从仓库根目录运行应用后端测试：

```powershell
$taskTestRoot = Join-Path $env:TEMP ('its-tests-' + [guid]::NewGuid().ToString('N'))
$env:USER_SQLITE_PATH = Join-Path $taskTestRoot 'users.db'
$env:SESSION_SQLITE_PATH = Join-Path $taskTestRoot 'sessions.db'
$env:MODEL_PROFILE_SQLITE_PATH = Join-Path $taskTestRoot 'models.db'
$env:MEMORY_SQLITE_PATH = Join-Path $taskTestRoot 'memory.db'
$env:MEMORY_BACKEND = 'sqlite'
& 'its_multi_agent/backend/app/.venv/Scripts/python.exe' -m unittest discover -s its_multi_agent/backend/app/tests -v
& 'its_multi_agent/backend/app/.venv/Scripts/python.exe' -m unittest its_multi_agent.harness.test_harness -v
```

运行知识库测试：

```powershell
$taskKnowledgeRoot = Join-Path $env:TEMP ('its-tests-kb-' + [guid]::NewGuid().ToString('N'))
$env:DOCUMENT_REGISTRY_PATH = Join-Path $taskKnowledgeRoot 'documents.db'
$env:LEXICAL_INDEX_PATH = Join-Path $taskKnowledgeRoot 'lexical.db'
$env:INGESTION_TASK_DB_PATH = Join-Path $taskKnowledgeRoot 'tasks.db'
& 'its_multi_agent/backend/knowledge/.venv/Scripts/python.exe' -m unittest discover -s its_multi_agent/backend/knowledge/test -v
```

两个前端分别在其目录运行：

```powershell
npm run check
```

Harness 在 `its_multi_agent/harness/` 中按其 README 执行。发布前至少保证两个后端、两个前端和 Harness 全部通过。
