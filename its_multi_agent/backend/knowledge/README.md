# Knowledge Service

知识库服务负责文档入库和检索。它是独立的 FastAPI 服务，主应用通过
`/api/knowledge/*` 代理访问它；直接访问本服务时必须提供
`X-Service-Token`。

## 目录职责

```text
knowledge/
├── api/                         # HTTP 路由、鉴权和服务启动
├── config/                      # 环境变量和运行参数
├── services/
│   ├── crawler/                 # 远端知识文章抓取和 Markdown 转换
│   ├── ingestion/               # 文件解析、OCR、父子分块和入库编排
│   ├── ingestion_task_service.py # 异步入库任务和任务恢复
│   ├── query_service.py         # 查询改写和答案生成
│   └── retrieval_service.py     # 向量、BM25、融合和重排
├── repositories/                # Milvus、SQLite FTS5、文档注册表
├── schemas/                     # API 请求和响应模型
├── cli/                         # 爬虫命令行入口
├── batch_upload.py              # 批量提交本地 Markdown 并等待入库
└── data/                        # 爬虫源文件和运行时数据
```

## 文件入库流程

1. `api/routers.py` 校验扩展名、大小和服务令牌，把上传文件保存到临时目录。
2. `DocumentRegistry` 按知识空间、领域和内容哈希去重，并建立文档处理记录。
3. `IngestionTaskService` 把解析任务放入有界线程池，服务重启后恢复未完成任务。
4. `services/ingestion/document_extractor.py` 提取文本和元数据。
5. `ParentChildSplitter` 生成可检索的子块，并保留父块上下文。
6. `IngestionProcessor` 同时写入 Milvus 向量索引和 SQLite FTS5/BM25 索引。
7. 查询阶段由 `RetrievalService` 融合两路召回并执行重排。

当前支持 `.md`、`.txt`、`.pdf`、`.docx` 和 `.xlsx`。PDF 的低文本页面以及
Word 内嵌图片可以使用 OCR。其它格式需要先转换，或在
`DocumentExtractor` 增加对应的解析器并同步更新 API 白名单。

## 启动

以下命令在包含 `its_multi_agent/` 目录的仓库根目录执行，使用知识库的
`.venv`，并假设已安装 `requirements.txt` 中的依赖。

```powershell
.\its_multi_agent\backend\knowledge\.venv\Scripts\python.exe -m its_multi_agent.backend.knowledge.api.main
```

生产环境应通过环境变量设置 `KNOWLEDGE_SERVICE_TOKEN`、Milvus 连接参数和模型参数。

## 批量上传

```powershell
$env:KNOWLEDGE_SERVICE_TOKEN = "长度至少为 32 的服务令牌"
.\its_multi_agent\backend\knowledge\.venv\Scripts\python.exe -m its_multi_agent.backend.knowledge.batch_upload
```

令牌必须与服务端一致。默认读取 `knowledge/data/crawl`；使用 `--directory`
指定其它目录。脚本会接受异步 `202` 响应，轮询任务直到成功或失败，并对网络
错误进行有限重试；单个文件失败会汇总为失败结果，后续文件继续处理。

## 回归验证

在仓库根目录运行：

```powershell
.\its_multi_agent\backend\knowledge\.venv\Scripts\python.exe -m unittest discover -s its_multi_agent/backend/knowledge/test -q
```

测试覆盖文件解析、上传任务、文档注册、鉴权和检索逻辑。Milvus、模型服务和
OCR 的外部调用在回归测试中使用替身，真实服务的端到端联调需要对应运行环境。


## Milvus 元数据兼容与迁移

新集合启用动态字段，允许不同标题层级、页码和工作表元数据共同入库。
已有固定 schema 集合保持兼容：写入时补齐其可选字段，并使用已有字段集合；
固定集合不能保存后来新增的元数据字段。需要完整保留新元数据时，先备份原文件、
文档注册表和索引，然后配置新的 `MILVUS_COLLECTION` 名称，在独立注册表/词法索引
路径下重新入库源文件。仅更改集合名不会迁移数据；沿用 complete 注册表会跳过上传。
对新集合核对检索与引用后，再切换服务配置，并关闭不再需要的 legacy 回退。
本次没有自动删除旧集合或用户数据。

删除同时清理 scope 集合和旧总集合中相同文档哈希的数据；向量和关键词召回
还会过滤注册表中已删除、删除失败或未完成的文档。缺少注册记录的旧数据保留
兼容读取，因此迁移时应核对历史数据与注册表的一致性。
重复上传处理中内容时返回已有任务 ID；批量上传继续等待该任务的最终结果。
