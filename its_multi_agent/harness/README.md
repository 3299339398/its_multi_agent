# ITS Agent Harness

This is a deterministic contract evaluation layer around the production chat service. It does not replace `backend/app` or measure semantic answer accuracy.

Scenarios describe inputs and expected behavior. The grader requires a nonblank answer and at least one nonblank expectation. It checks observed tools, forbidden tools, expected tool order (ordered subsequence, including repeats), agent transitions, emitted source origins, and case-insensitive required substrings. Required substrings are lexical checks; passing does not establish that the answer is correct or supported by its citations.

Run the first smoke tests from the repository root:

```text
python -m unittest its_multi_agent.harness.test_harness.HarnessTest
```

Run the full `its_multi_agent.harness.test_harness` and `its_multi_agent.backend.app.tests.test_stream_metadata` modules with the app virtual environment for mocked production-service integration coverage. Set `USER_SQLITE_PATH`, `SESSION_SQLITE_PATH`, `MEMORY_SQLITE_PATH`, and `MODEL_PROFILE_SQLITE_PATH` to temporary files and `MEMORY_BACKEND=sqlite` before importing the service. Those tests mock providers, persistence, attachments, and grounding decisions; they do not call a paid model or prove live retrieval quality.

`execute_with_service` calls `MultiAgentService.process_task`, exercising the same session, attachment, grounding, and SSE path as chat. `execute_with_agents` remains a compatibility alias for that service path. Live runs require the normal model, knowledge, and MCP configuration and may incur provider costs.

The adapter assigns fresh `harness-...` user and session IDs per call. Explicit IDs must use the same prefix; reuse them only for intentional history scenarios. Fixtures with attachments or user model profiles must be provisioned for that explicit harness user. Integration persistence should use disposable databases. `user_context` supports `user_id`, `session_id`, `origin` (the chat GeoLocation object), `flag` (default false), `model_profile_id`, `enabled_plugins`, `attachment_ids`, and `temporary_model`; unknown fields fail instead of being silently ignored.

The adapter preserves answer deltas, source snapshots, repeated raw tool names, agent updates, and finish errors. Missing finish packets and non-normal finishes fail. Structured tool/agent metadata covers events emitted by the final orchestrator stream. Grounding planner, reviewer, and retrieval calls happen before that stream and are not tool events in this trace. Consequently forbidden-tool/order checks apply only to the observed stream, and emitted `sources.origin` does not prove retrieval completeness. Use the grounding unit tests and prediction evaluation for their separate contracts.

The bundled knowledge scenarios require seeded internal travel and repair policies. They check emitted knowledge evidence and navigation invocation, with a synthetic location. They should fail when required evidence is absent. They do not prescribe obsolete diagnosis tools or expect `query_knowledge` inside the final answer stream.

Prediction evaluation (`python -m its_multi_agent.backend.app.services.answer_evaluation --predictions predictions.json`) requires complete case coverage and nonblank answers. It exits 1 for unmet thresholds, 2 for invalid input, and 0 when its measured contracts pass. The default minimum is 1.0 for route accuracy, action accuracy, evidence recall, citation source precision, and answer term coverage. Override with `--min-route-accuracy`, `--min-action-accuracy`, `--min-evidence-recall`, `--min-citation-source-precision`, or `--min-answer-term-coverage` (finite values from 0 to 1). Metrics with no applicable expectations are unmeasured; their report value is null. Missing predictions always fail even with relaxed thresholds. Citation IDs and answer terms remain proxies requiring human semantic review.
