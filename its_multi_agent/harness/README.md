# ITS Agent Harness

This is a deterministic contract evaluation layer around the production chat service. It does not replace `backend/app` or measure semantic answer accuracy.

Scenarios describe inputs and expected behavior. The grader requires a nonblank answer and at least one nonblank expectation. It checks observed tools, forbidden tools, expected tool order (ordered subsequence, including repeats), agent transitions, emitted source origins, and case-insensitive required substrings. Required substrings are lexical checks; passing does not establish that the answer is correct or supported by its citations.

工程任务可以使用 `expected_plan_executors: ["coding"]` 检查计划是否包含编码执行步骤。编码能力必须由请求显式启用，并由服务端配置授权工作区和预设检查命令；评测时应使用临时工程副本，避免修改真实项目。

Run the first smoke tests from the repository root:

```text
python -m unittest its_multi_agent.harness.test_harness.HarnessTest
```

Run the full `its_multi_agent.harness.test_harness` and `its_multi_agent.backend.app.tests.test_stream_metadata` modules with the app virtual environment for mocked production-service integration coverage. Set `USER_SQLITE_PATH`, `SESSION_SQLITE_PATH`, `MEMORY_SQLITE_PATH`, and `MODEL_PROFILE_SQLITE_PATH` to temporary files and `MEMORY_BACKEND=sqlite` before importing the service. Those tests mock providers, persistence, attachments, and grounding decisions; they do not call a paid model or prove live retrieval quality.

`execute_with_service` calls `MultiAgentService.process_task`, exercising the same session, attachment, grounding, and SSE path as chat. `execute_with_agents` remains a compatibility alias for that service path. Live runs require the normal model, knowledge, and MCP configuration and may incur provider costs.

`run_suite` and `harness.metrics.summarize_runs` produce comparable snapshots for scenario pass rate, route accuracy, source-origin coverage, non-empty answers, median/p95 total latency, first-event latency, and duplicate side-effect rate. These are service-level contract metrics; they do not claim semantic answer correctness unless scenarios provide an independently reviewed expectation.

The adapter assigns fresh `harness-...` user and session IDs per call. Explicit IDs must use the same prefix; reuse them only for intentional history scenarios. Fixtures with attachments or user model profiles must be provisioned for that explicit harness user. Integration persistence should use disposable databases. `user_context` supports `user_id`, `session_id`, `origin` (the chat GeoLocation object), `flag` (default false), `model_profile_id`, `enabled_plugins`, `confirmed_plugins`, `project_id`, `work_mode`, `attachment_ids`, and `temporary_model`; unknown fields fail instead of being silently ignored. Scenario files reject duplicate IDs, unknown fields, invalid expectation lists, and expected/forbidden tool conflicts.

The adapter preserves answer deltas, source snapshots, grounding trace events, repeated raw tool names, agent updates, and finish errors. Missing finish packets and non-normal finishes fail. Structured tool/agent metadata covers events emitted by the final orchestrator stream. Grounding planner, reviewer, and retrieval calls are exposed as `sagegpt/grounding-trace` packets with phase, status, route, origin, and source IDs; they remain separate from tool events. `expected_grounding_origins` checks that an origin was observed during grounding, while `expected_source_origins` checks the final evidence snapshot. Consequently forbidden-tool/order checks apply only to the observed stream. Use the grounding unit tests and prediction evaluation for semantic retrieval quality.

The bundled knowledge scenarios require seeded internal travel and repair policies. They check emitted knowledge evidence and navigation invocation, with a synthetic location. They should fail when required evidence is absent. They do not prescribe obsolete diagnosis tools or expect `query_knowledge` inside the final answer stream.

Prediction evaluation (`python -m its_multi_agent.backend.app.services.answer_evaluation --predictions predictions.json`) requires complete case coverage and nonblank answers. It exits 1 for unmet thresholds, 2 for invalid input, and 0 when its measured contracts pass. The default minimum is 1.0 for route accuracy, action accuracy, evidence recall, citation source precision, and answer term coverage. Override with `--min-route-accuracy`, `--min-action-accuracy`, `--min-evidence-recall`, `--min-citation-source-precision`, or `--min-answer-term-coverage` (finite values from 0 to 1). Metrics with no applicable expectations are unmeasured; their report value is null. Missing predictions always fail even with relaxed thresholds. Citation IDs and answer terms remain proxies requiring human semantic review.


### 指标观测边界（2026-10-10）

`source_origin_coverage` 仅检查来源类别是否出现，不能代表引用支持率。
没有路由、首事件耗时或副作用审计样本时，相应指标返回 `null`。
当前 SSE 适配器的 PROCESS 工具名称无法证明副作用已提交，因此不推断
重复副作用；`side_effect_observed_count` 为 0 时，重复副作用率是 `null`。
需要测量该指标时，应由操作审计适配器提供经过确认的操作身份与提交结果。
`expected_route` 和 `max_latency_ms` 可写入场景 JSON，由加载器和评分器校验。
