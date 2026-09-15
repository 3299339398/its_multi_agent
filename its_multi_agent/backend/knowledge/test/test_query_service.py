import json
import unittest
from unittest.mock import patch

from its_multi_agent.backend.knowledge.services.query_service import QueryService
from langchain_core.documents import Document


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeLlm:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return FakeResponse(self.content)


class QueryServiceTest(unittest.TestCase):
    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_ENABLED", True)
    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_VARIANTS", 20)
    def test_rewrite_regression_preserves_identifiers_numbers_and_constraints(self):
        original = "ZX-81 出现 E204，温度低于 30°C，等待 5 分钟怎么办"
        valid = "ZX-81 温度低于 30°C，等待 5 分钟仍出现 E204 的解决方法"
        variants = [None, 123, {"query": original},
                    original.replace("ZX-81", "ZX-82"),
                    original.replace("E204", "E205"),
                    original.replace("30", "40"),
                    original.replace("低于", "高于"),
                    original.replace("E204", ""),
                    original + " E999", valid]
        queries = QueryService(llm=FakeLlm(json.dumps(variants))).build_search_queries(
            original, force_rewrite=True)
        self.assertEqual(queries, [original, valid])

    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_ENABLED", True)
    def test_rewrite_rejects_truncation_and_zero_variant_budget(self):
        service = QueryService(llm=FakeLlm(json.dumps(["x" * 5001])))
        self.assertEqual(service.build_search_queries("help", force_rewrite=True), ["help"])
        with patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_VARIANTS", 0):
            service = QueryService(llm=FakeLlm('["new query"]'))
            self.assertEqual(service.build_search_queries("help", force_rewrite=True), ["help"])

    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_ENABLED", True)
    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_VARIANTS", 2)
    def test_build_search_queries_keeps_original_and_deduplicates_rewrites(self):
        llm = FakeLlm('["如何办理差旅报销", "差旅报销流程", "差旅报销流程"]')

        queries = QueryService(llm=llm).build_search_queries(
            "出差的钱咋报？", "finance", "policy"
        )

        self.assertEqual(queries, ["出差的钱咋报？", "如何办理差旅报销", "差旅报销流程"])
        self.assertIn("知识空间：finance", llm.prompts[0])
        self.assertIn("知识领域：policy", llm.prompts[0])

    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_ENABLED", True)
    def test_build_search_queries_falls_back_to_original_on_invalid_response(self):
        service = QueryService(llm=FakeLlm("不是 JSON"))

        self.assertEqual(service.build_search_queries("原始问题"), ["原始问题"])

    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_ENABLED", False)
    def test_build_search_queries_can_be_disabled(self):
        llm = FakeLlm(error=AssertionError("LLM should not be called"))

        self.assertEqual(QueryService(llm=llm).build_search_queries(" 原始问题 "), ["原始问题"])

    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_ADAPTIVE", True)
    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_MIN_LENGTH", 10)
    def test_adaptive_rewrite_skips_llm_for_clear_question(self):
        llm = FakeLlm(error=AssertionError("LLM should not be called"))

        queries = QueryService(llm=llm).build_search_queries(
            "员工差旅住宿费用的报销上限是多少"
        )

        self.assertEqual(queries, ["员工差旅住宿费用的报销上限是多少"])

    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_ADAPTIVE", True)
    @patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_VARIANTS", 1)
    def test_force_rewrite_expands_clear_question_after_weak_retrieval(self):
        llm = FakeLlm('["差旅住宿费用报销限额"]')

        queries = QueryService(llm=llm).build_search_queries(
            "员工差旅住宿费用的报销上限是多少",
            force_rewrite=True,
        )

        self.assertEqual(queries, ["员工差旅住宿费用的报销上限是多少", "差旅住宿费用报销限额"])

    @patch(
        "its_multi_agent.backend.knowledge.services.query_service.settings.ADAPTIVE_REWRITE_SCORE_THRESHOLD",
        0.55,
    )
    def test_retrieval_expands_only_when_first_pass_is_weak(self):
        strong = [Document(page_content="正文", metadata={"rerank_score": 0.8})]
        weak = [Document(page_content="正文", metadata={"rerank_score": 0.3})]

        self.assertFalse(QueryService.should_expand_retrieval(strong))
        self.assertTrue(QueryService.should_expand_retrieval(weak))
        self.assertTrue(QueryService.should_expand_retrieval([]))


if __name__ == "__main__":
    unittest.main()
