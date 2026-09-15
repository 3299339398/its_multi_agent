# 导航多轮上下文

聊天接口在路由前，从当前用户、当前会话最近的消息恢复待完成的纯导航任务。原始消息仍按原文归档，不额外写入模型生成的任务文本；恢复结果只用于本次路由、主 Agent 输入和导航子 Agent 委派。

例如“从我这里到淄博推荐一下路线”后，助手询问出发地和出行方式，用户依次回答“都可以”“郑州”，任务恢复为郑州到淄博，方式不限。未提供起点时仅询问起点，不再重复询问已知终点。明确更改目的地或新路线会更新任务，取消或不相关话题会结束此规则的继承。导航插件关闭时仍返回未启用，不绕过插件权限。

导航子 Agent 的起点、终点和出行偏好由请求上下文传递，避免主 Agent 委派遗漏或反转。未指定出行方式时，工具的 driving 默认值不代表用户偏好。城市间建议与需要具体地址的精确导航应区分。

范围：这是最近 12 条消息内常见中文导航补充的确定性恢复，不是无限期保存的任务数据库，也不是覆盖所有自然语言的地点识别器。其他表述继续走原有模型路由；路由现在也读取最多 12 条历史消息，并明确要求按上轮提问理解简短回答。现有会话摘要和长期记忆保持原有机制。

验证命令（仓库根目录）：

```powershell
.\its_multi_agent\backend\app\.venv\Scripts\python.exe -X utf8 -m unittest its_multi_agent.backend.app.tests.test_navigation_context
.\its_multi_agent\backend\app\.venv\Scripts\python.exe -X utf8 -m its_multi_agent.harness.smoke_navigation_memory
```

第二条为显式执行的真实模型测试：经 HTTP/SSE 调用当前模型，但模拟导航子 Agent 结果并隔离用户历史写入，不证明地图服务可用。
