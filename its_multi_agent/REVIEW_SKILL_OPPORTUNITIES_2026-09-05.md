# 项目复查与 Skill 候选

范围：当前工作区的问答入口、路由与证据、会话、知识库任务、模型配置、前端和评测。未审查部署方案，未修改业务代码，未安装 skill。以下是重点路径审查，不是逐行安全审计。

## 当前发现

### P1：入库重试与删除仍可能互相覆盖

`backend/knowledge/services/ingestion_task_service.py:76` 的重试只更新任务表，没有同步登记表。删除接口 `backend/knowledge/api/routers.py:224` 只拦截登记状态为 processing 的文档；worker 完成后，`backend/knowledge/repositories/document_registry.py:73` 无条件把文档改成 complete。因此失败任务重试后被删除，仍可能被 worker 重新写入索引并标成 complete。任务领取也没有状态条件，重复提交可能重复执行。

本轮证据：重新核对上述状态读写路径；此前审查的临时数据库复现仍对应当前实现，本轮未重跑并发实验。建议先用条件更新领取任务，并通过任务代次、删除标记和索引补偿维护一致性。这个约束必须由代码保障。

### P1：个人模型地址缺少服务端访问边界

`backend/app/schemas/model_profile.py:15` 和 `backend/app/schemas/request.py:41` 只校验 base_url 长度；`backend/app/infrastructure/ai/model_factory.py:64` 将地址直接交给服务器客户端。登录用户可以指定回环或内网目标。

本轮离线复现：ModelProfileCreate 接受 http://127.0.0.1:8001/v1。没有向内部服务发送请求，实际可达范围依赖网络和目标接口。建议管理员登记允许的端点；本地模型端点可显式允许。Skill 提醒不能替代该校验。

### P2：评测不能可靠阻止质量回退

`harness/grader.py:6` 在没有期望条件时允许空答案通过；关键词出现不代表结论正确。`backend/app/services/answer_evaluation.py:94` 只检查 failures，但预测模式报告 route_failures。离线复现：28 个用例均无预测，route_accuracy 为 0，现有退出码表达式仍为 0。

`harness/real_executor.py:26` 直接执行 orchestrator，未经过生产入口的会话准备、附件处理和 GroundingWorkflow。建议修复通过标准、缺失预测和退出码，再接入真实业务入口的离线回放。

### P2：历史列表无分页，引用快照放大响应体

`backend/app/api/routers.py:135` 调用完整会话归档；`backend/app/repositories/sqlite_session_repository.py:208` 遍历会话并加载全部消息，包括来源快照。前端每次请求结束再次 fetchUserSessions。推理侧最近窗口已经有界，但列表的数据库读量、传输量和浏览器内存仍随所有历史增长。

建议列表只返回分页的会话 ID、标题、更新时间和消息数量；进入会话再分页加载消息和引用。该判断来自静态调用链，未做大型归档性能基准。

### P2：技术诊断子智能体与主流程契约不一致

`backend/app/plugins/registry.py` 仍公开 diagnose_technical_issue；`backend/app/multi_agent/agent_factory.py` 仍构建该工具。然而 GroundingOutcome 默认 allowed_tools 为空，当前 GroundingWorkflow 只在导航任务开放 query_service_station_and_navigate，`agent_service.py:127` 将该列表传入最终 Agent。因此当前主问答入口不会调用技术诊断子智能体，而旧 harness 可以调用它。

需确认这是证据流程统一后的有意简化，还是遗漏了复杂诊断路径。若保留诊断功能，应让子流程使用经过审查的证据和当前约束；不应简单恢复全部工具，绕过已有边界。若不保留，应同步插件、指南和评测。

### P2：JWT 与已保存模型凭据共用密钥生命周期

`backend/app/repositories/model_profile_repository.py:24` 从 AUTH_JWT_SECRET 派生 Fernet 密钥。轮换登录签名密钥后，旧个人模型凭据无法由新密钥解密。建议单独的存储加密密钥及版本迁移。静态确认，本轮未操作真实密钥。

## 可维护性与已改善部分

- 已接入用户原话记忆、来源快照、附件续聊和流式请求隔离；不再将此前对应问题全部列为未修复。
- 聊天排版已改善，但 App.vue、style.css、modern.css 同时维护覆盖规则。上轮按钮最小宽度冲突说明样式所有权应逐步统一；不建议继续堆更多覆盖层。
- PROJECT_GUIDE.md 的请求流程、模型配置说明已落后于代码，需要同步临时模型、前置证据规划和 sources SSE。

## Skill 应如何使用

当前已检查的项目源码没有 SKILL.md 发现、按需加载或执行机制；plugins 是工具注册，prompts 是 Agent 指令，两者都不等于完整 skill 运行框架。添加 Markdown 不会自动赋予应用新能力。

### 开发维护 Skill

| 候选名称 | 触发任务 | 应沉淀的项目专属内容 | 验证产物 |
| --- | --- | --- | --- |
| its-regression-review | 修改路由、SSE、记忆、检索或模型适配后 | 真实入口、隔离数据库、各模块测试命令、失败用例归档、区分回归通过与真实准确率 | 有执行证据的变更评测报告 |
| its-retrieval-tuning | 排查查不到、引用错、型号混淆 | 固定资料与问题集，比较召回、去重、重排、引用适用性，每次调整保留基线 | 分层指标与失败样本 |
| its-chat-ui-review | 修改聊天或知识库布局 | 样式所有权、已有组件与图标、手机侧栏、长标题、长表格、SSE 状态、截图检查 | 桌面与手机的可复现检查结果 |

这些 skill 供开发助手使用；可直接复用现有脚本，避免另建一套测试体系。优先做 its-regression-review，但先修好评分器，否则 skill 只会重复运行不可靠的门槛。

### 产品业务 Skill

| 候选名称 | 触发条件 | 流程输出与边界 |
| --- | --- | --- |
| 设备故障排查 | 设备型号、症状或错误码明确，且需要多步骤诊断 | 收集系统版本、已尝试操作、保数据约束；引用适用资料；输出检查步骤、预期观察、下一分支、停止或转人工条件 |
| 内部制度与公开规则对照 | 同时询问公司规定和公开规则，或资料版本冲突 | 分开查询、标注日期与适用范围、区分冲突与证据缺失；不把内部原文作为公网查询词 |
| 售后服务站办理 | 用户明确请求维修地点或导航 | 确认位置与品牌、查询匹配站点、列出来源；营业与服务能力仅在资料支持时陈述，不自动预约或提交用户资料 |

业务 skill 是可复用的操作方法和检查项，不是另一个必须新增的 Agent。可先选一个领域，在现有规划与回答流程按需加载受维护的指令和参考资料；只有出现明确的独立工具或状态需求时再设计执行器。

鉴权、知识空间权限、工具白名单、重试、状态一致性和证据 ID 校验继续留在确定性代码。文档、网页和用户上传内容不能自行注册成可执行 skill。

## 本轮验证

- App 后端 117 项测试通过，使用临时隔离数据库。
- Knowledge 后端 44 项测试通过，使用临时隔离数据库。
- Harness 基础自测 3 项通过；另行复现上述评分漏洞。
- 聊天前端 40 项测试和构建通过。
- 知识库前端 5 项测试、lint 和构建通过。
- 合计 209 项通过。未调用付费模型、未运行真实 Milvus 检索基准，本轮没有重跑浏览器截图检查。

优先级：入库状态一致性和评测假通过修复；会话分页；首个开发回归 skill；再以设备故障排查作为业务 skill 试点。
