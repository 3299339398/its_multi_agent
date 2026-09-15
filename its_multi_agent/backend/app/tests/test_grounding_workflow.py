import unittest
from unittest.mock import AsyncMock, patch

from its_multi_agent.backend.app.services.answer_routing import RoutePlan
from its_multi_agent.backend.app.services.grounding_workflow import (
    EvidenceReview, GroundingWorkflow, normalize_sources,
)


def knowledge(excerpt="ZX-81 E204: unplug power before replacing the drive.", source_id="manual-1"):
    return {"sources": [{"source_id": source_id, "excerpt": excerpt, "source_name": "Manual", "page": 2}]}


class GroundingWorkflowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.workflow = GroundingWorkflow(model=object())
        self.workflow.plan = AsyncMock()
        self.workflow.review = AsyncMock(return_value=EvidenceReview(
            status="sufficient", supporting_source_ids=["manual-1"], missing_information="",
        ))
        self.kb = AsyncMock(return_value=knowledge())
        self.web = AsyncMock(return_value={"status": "ok", "results": [
            {"url": "https://example.org/policy", "title": "Public policy", "snippet": "Public travel rules"},
        ]})
        self.patch_kb = patch("its_multi_agent.backend.app.services.grounding_workflow.request_knowledge", self.kb)
        self.patch_web = patch("its_multi_agent.backend.app.services.grounding_workflow.request_web_search", self.web)
        self.patch_kb.start()
        self.patch_web.start()
        self.addCleanup(self.patch_kb.stop)
        self.addCleanup(self.patch_web.stop)

    async def test_internal_question_prefetches_evidence_and_removes_search_tools(self):
        result = await self.workflow.prepare("公司 ZX-81 手册的 E204 如何处理？")
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.sources[0]["source_id"], "manual-1")
        self.assertEqual(result.allowed_tools, [])
        self.assertTrue(self.kb.await_args.kwargs["retrieve_only"])
        self.web.assert_not_awaited()
        self.workflow.plan.assert_not_awaited()

    async def test_empty_private_evidence_abstains_without_public_fallback(self):
        self.kb.return_value = {"sources": []}
        result = await self.workflow.prepare("公司最新报销制度是什么？")
        self.assertEqual(result.status, "insufficient")
        self.assertTrue(result.reply)
        self.web.assert_not_awaited()

    async def test_high_ranking_score_does_not_make_wrong_model_answerable(self):
        self.kb.return_value = knowledge("ZX-82 E204: reset everything.")
        self.kb.return_value["sources"][0]["score"] = 0.999
        result = await self.workflow.prepare("公司 ZX-81 手册的 E204 如何处理？")
        self.assertEqual(result.status, "insufficient")
        self.assertFalse(result.sources)
        self.workflow.review.assert_not_awaited()

    async def test_conflicting_or_partial_evidence_cannot_reach_answer_generation(self):
        for status in ("conflicting", "insufficient"):
            self.workflow.review.return_value = EvidenceReview(
                status=status, supporting_source_ids=["manual-1"], missing_information="缺少适用版本",
            )
            result = await self.workflow.prepare("公司 ZX-81 手册的 E204 如何处理？")
            self.assertEqual(result.status, status)
            self.assertTrue(result.reply)
            self.assertFalse(result.sources)

    async def test_reviewer_cannot_invent_source_ids(self):
        self.workflow.review.return_value = EvidenceReview(
            status="sufficient", supporting_source_ids=["invented"], missing_information="",
        )
        result = await self.workflow.prepare("公司最新报销制度是什么？")
        self.assertEqual(result.status, "unverified")
        self.assertTrue(result.reply)

    async def test_selected_sources_must_still_cover_requested_identifiers(self):
        self.kb.return_value = {"sources": [
            {"source_id": "manual-1", "excerpt": "ZX-82 E204 reset"},
            {"source_id": "manual-2", "excerpt": "ZX-81 E204 unplug"},
        ]}
        result = await self.workflow.prepare("公司 ZX-81 手册的 E204 如何处理？")
        self.assertEqual(result.status, "unverified")

    async def test_mixed_attachment_uses_file_evidence_and_public_query_only(self):
        self.workflow.plan.return_value = RoutePlan(
            route="mixed", knowledge_query="附件中的差旅标准", web_query="国家最新税收政策",
        )
        self.workflow.review.side_effect = lambda question, sources: EvidenceReview(
            status="sufficient", supporting_source_ids=[source["source_id"] for source in sources], missing_information="",
        )
        result = await self.workflow.prepare("对比附件与国家最新税收政策", has_attachments=True,
            available_tools=["search_web"], attachment_sources=[{
                "source_id": "attachment-1", "origin": "attachment", "source_name": "差旅制度.txt",
                "excerpt": "差旅标准：住宿每晚 500 元。", "excerpt_truncated": False,
            }])
        self.assertEqual(result.status, "ready")
        self.assertEqual({source["origin"] for source in result.sources}, {"attachment", "web"})
        self.kb.assert_not_awaited()
        self.assertEqual(self.web.await_args.args[0], "国家最新税收政策")

    async def test_disabled_plugin_does_not_fall_back_to_another_source(self):
        result = await self.workflow.prepare("公司最新报销制度是什么？", available_tools=["search_web"])
        self.assertEqual(result.status, "unavailable")
        self.kb.assert_not_awaited()
        self.web.assert_not_awaited()

    async def test_public_knowledge_can_fall_back_once_to_approved_web_query(self):
        self.workflow.plan.return_value = RoutePlan(
            route="knowledge", knowledge_query="公开的 Python 列表操作资料", web_query="Python list official documentation",
        )
        self.kb.return_value = {"sources": []}
        self.workflow.review.side_effect = lambda question, sources: EvidenceReview(
            status="sufficient", supporting_source_ids=[sources[0]["source_id"]], missing_information="",
        )
        result = await self.workflow.prepare("先查知识库中的 Python 列表资料，没有就查官方文档")
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.sources[0]["origin"], "web")
        self.assertEqual(self.web.await_count, 1)

    async def test_mixed_query_never_sends_private_query_to_search(self):
        self.workflow.plan.return_value = RoutePlan(
            route="mixed", knowledge_query="公司差旅制度", web_query="国家最新税收政策",
        )
        self.workflow.review.side_effect = lambda question, sources: EvidenceReview(
            status="sufficient", supporting_source_ids=[item["source_id"] for item in sources], missing_information="",
        )
        result = await self.workflow.prepare("对比公司差旅制度和国家最新税收政策")
        self.assertEqual(result.status, "ready")
        self.assertEqual({source["origin"] for source in result.sources}, {"knowledge", "web"})
        self.assertEqual(self.web.await_args.args[0], "国家最新税收政策")

    async def test_mixed_review_must_support_both_origins(self):
        self.workflow.plan.return_value = RoutePlan(
            route="mixed", knowledge_query="公司差旅制度", web_query="国家最新税收政策",
        )
        result = await self.workflow.prepare("对比公司差旅制度和国家最新税收政策")
        self.assertEqual(result.status, "unverified")

    async def test_network_error_is_not_reported_as_no_documents(self):
        self.kb.return_value = {"status": "error", "error_msg": "secret backend traceback"}
        result = await self.workflow.prepare("公司最新报销制度是什么？")
        self.assertEqual(result.status, "unavailable")
        self.assertNotIn("secret", result.reply)
        self.web.assert_not_awaited()

    async def test_planner_failure_fails_closed(self):
        self.workflow.plan.side_effect = RuntimeError("provider secret")
        result = await self.workflow.prepare("最新报销制度是什么？", history=[{"role": "user", "content": "政策 A"}])
        self.assertEqual(result.status, "unavailable")
        self.assertNotIn("secret", result.reply)
        self.kb.assert_not_awaited()
        self.web.assert_not_awaited()

    async def test_evidence_reviewer_receives_resolved_subject_for_follow_up(self):
        self.workflow.plan.return_value = RoutePlan(route="knowledge", knowledge_query="公司 ZX-81 手册的 E204 如何处理？")
        result = await self.workflow.prepare("它的 E204 如何处理？", history=[
            {"role": "user", "content": "公司 ZX-81 手册在哪里？"},
        ])
        self.assertEqual(result.status, "ready")
        self.assertIn("ZX-81", self.workflow.review.await_args.args[0])

    async def test_combined_query_preserves_navigation_after_review(self):
        self.workflow.plan.return_value = RoutePlan(route="knowledge", knowledge_query="公司维修手册的蓝屏处理")
        result = await self.workflow.prepare("先查公司维修手册的蓝屏处理，再找附近服务站")
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.allowed_tools, ["query_service_station_and_navigate"])

    async def test_explicit_knowledge_space_and_domain_are_preserved(self):
        self.workflow.plan.return_value = RoutePlan(
            route="knowledge", knowledge_query="公司 ZX-81 手册的 E204 如何处理？",
            knowledge_space="handbook", domain="hardware",
        )
        result = await self.workflow.prepare("在知识空间 handbook、领域 hardware 查询公司 ZX-81 手册的 E204 处理方法")
        self.assertEqual(result.status, "ready")
        self.assertEqual(self.kb.await_args.kwargs.get("knowledge_space"), "handbook")
        self.assertEqual(self.kb.await_args.kwargs.get("domain"), "hardware")

    async def test_planner_receives_durable_memory_beyond_recent_window(self):
        from its_multi_agent.backend.app.services.conversation_memory import SUMMARY_PREFIX
        workflow = GroundingWorkflow(object())
        workflow._structured = AsyncMock(return_value=RoutePlan(route="knowledge", knowledge_query="ZX-81 E204 handling"))
        await workflow.plan("它如何处理？", [{"role": "system", "content": SUMMARY_PREFIX + "用户目标：修复 ZX-81，不能清空硬盘。"}], False)
        self.assertIn("不能清空硬盘", workflow._structured.await_args.args[1].get("conversation_memory", ""))

    async def test_follow_up_may_resolve_identifiers_from_durable_memory(self):
        from its_multi_agent.backend.app.services.conversation_memory import SUMMARY_PREFIX
        self.workflow.plan.return_value = RoutePlan(route="knowledge", knowledge_query="ZX-81 E204 handling")
        result = await self.workflow.prepare("它的 E204 如何处理？", history=[
            {"role": "system", "content": SUMMARY_PREFIX + "用户设备：ZX-81"},
            {"role": "user", "content": "继续"},
        ])
        self.assertEqual(result.status, "ready")

    async def test_attachment_has_no_external_search_and_greeting_stays_fast(self):
        result = await self.workflow.prepare("解释附件参数", has_attachments=True)
        self.assertEqual(result.route, "attachment")
        self.assertEqual(result.allowed_tools, [])
        self.assertFalse(result.reply)
        result = await self.workflow.prepare("你好")
        self.assertEqual(result.route, "direct")
        self.workflow.plan.assert_not_awaited()
        self.web.assert_not_awaited()
        self.kb.assert_not_awaited()


class SourceNormalizationTest(unittest.TestCase):
    def test_web_sources_require_an_inspectable_http_url_and_excerpt(self):
        result = normalize_sources({"results": {"pages": [
            {"url": "https://example.org/rules", "title": "Rules", "snippet": "version 2026"},
            {"url": "javascript:bad", "content": "not a source"},
            {"url": "https://example.org/empty", "snippet": ""},
        ]}}, "web")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["url"], "https://example.org/rules")
        self.assertEqual(result[0]["excerpt"], "version 2026")


class StructuredWorkflowTest(unittest.IsolatedAsyncioTestCase):
    async def test_openai_compatible_models_use_json_object_mode(self):
        from types import SimpleNamespace
        from agents import OpenAIChatCompletionsModel

        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"route":"direct"}'),
        )]))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        model = OpenAIChatCompletionsModel(model="deepseek-chat", openai_client=client)

        result = await GroundingWorkflow(model).plan("你是哪个模型", [], False)

        self.assertEqual(result.route, "direct")
        self.assertEqual(create.await_args.kwargs["response_format"], {"type": "json_object"})

    async def test_real_sdk_parses_planner_and_review_without_exposing_tools(self):
        import json
        from agents import Model
        from agents.items import ModelResponse
        from agents.usage import Usage
        from openai.types.responses import ResponseOutputMessage, ResponseOutputText

        class StructuredModel(Model):
            def __init__(self):
                self.outputs = [
                    {"route": "knowledge", "knowledge_query": "ZX-81 E204 handling", "web_query": "", "clarification": ""},
                    {"status": "sufficient", "supporting_source_ids": ["manual-1"], "missing_information": ""},
                ]
                self.requests = []

            async def get_response(self, **kwargs):
                self.requests.append(kwargs)
                return ModelResponse(output=[ResponseOutputMessage(
                    id="message", role="assistant", status="completed", content=[ResponseOutputText(
                        type="output_text", text=json.dumps(self.outputs.pop(0)), annotations=[], logprobs=[],
                    )], type="message",
                )], usage=Usage(), response_id="response")

            async def stream_response(self, **kwargs):
                raise AssertionError("Planning must not stream a user-visible answer")
                yield

        model = StructuredModel()
        with patch("its_multi_agent.backend.app.services.grounding_workflow.request_knowledge",
                   AsyncMock(return_value=knowledge())):
            result = await GroundingWorkflow(model).prepare("ZX-81 E204 handling")
        self.assertEqual(result.status, "ready")
        self.assertEqual(len(model.requests), 2)
        self.assertTrue(all(request["tools"] == [] for request in model.requests))


if __name__ == "__main__":
    unittest.main()
