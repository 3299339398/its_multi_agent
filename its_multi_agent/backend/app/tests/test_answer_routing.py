import unittest

from its_multi_agent.backend.app.services.answer_routing import (
    RoutePlan, route_by_rules, validate_plan,
)


class AnswerRoutingTest(unittest.TestCase):
    def test_internal_ownership_wins_over_recency(self):
        for question in ("公司的最新报销制度是什么？", "我们项目现在的交付周期是多少？",
                         "我司现行差旅标准", "What is our latest internal expense policy?"):
            with self.subTest(question=question):
                plan = route_by_rules(question)
                self.assertEqual(plan.route, "knowledge")
                self.assertEqual(plan.knowledge_query, question)
                self.assertFalse(plan.web_query)

    def test_public_live_questions_go_to_web(self):
        for question in ("今天北京天气如何？", "人民币今天汇率", "国家最新税收政策是什么？",
                         "微软公司今天股价", "latest Python release"):
            with self.subTest(question=question):
                self.assertEqual(route_by_rules(question).route, "web")

    def test_mixed_question_requires_semantic_split(self):
        self.assertIsNone(route_by_rules("对比公司差旅制度和国家最新税收政策"))

    def test_attachment_question_never_triggers_search(self):
        self.assertEqual(route_by_rules("根据上传的附件解释 ZX-81 参数", has_attachments=True).route,
                         "attachment")
        self.assertEqual(route_by_rules("根据附件解释 ZX-81 参数").route, "clarify")

    def test_follow_up_is_resolved_semantically_instead_of_searching_pronouns(self):
        self.assertIsNone(route_by_rules("它现在还适用吗？", previous_question="公司的差旅制度是什么？"))
        self.assertEqual(route_by_rules("它现在还适用吗？").route, "clarify")

    def test_planner_cannot_send_private_question_to_web(self):
        question = "公司的最新报销制度是什么？"
        plan = validate_plan(question, RoutePlan(route="web", web_query=question))
        self.assertEqual(plan.route, "knowledge")
        self.assertFalse(plan.web_query)

    def test_mixed_plan_rejects_private_content_in_public_query(self):
        question = "对比公司差旅制度和国家最新税收政策"
        plan = validate_plan(question, RoutePlan(
            route="mixed", knowledge_query="公司差旅制度", web_query=question,
        ))
        self.assertEqual(plan.route, "clarify")

    def test_mixed_plan_accepts_separate_public_subject(self):
        question = "对比公司差旅制度和国家最新税收政策"
        plan = validate_plan(question, RoutePlan(
            route="mixed", knowledge_query="公司差旅制度", web_query="国家最新税收政策",
        ))
        self.assertEqual(plan.route, "mixed")
        self.assertNotIn("公司", plan.web_query)

    def test_forbidden_web_and_invented_identifiers_are_rejected(self):
        plan = validate_plan("不要联网，解释 ZX-81 的 E204 故障", RoutePlan(
            route="web", web_query="ZX-81 E204 fault",
        ))
        self.assertEqual(plan.route, "clarify")
        plan = validate_plan("查询 ZX-81 故障处理", RoutePlan(
            route="knowledge", knowledge_query="ZX-82 故障处理",
        ))
        self.assertEqual(plan.route, "clarify")

    def test_prior_private_subject_cannot_be_reclassified_as_public(self):
        plan = validate_plan("它现在还适用吗？", RoutePlan(route="web", web_query="最新报销制度"),
                             previous_question="公司的差旅制度是什么？")
        self.assertEqual(plan.route, "clarify")

    def test_greeting_does_not_require_external_model_planning(self):
        self.assertEqual(route_by_rules("你好").route, "direct")

    def test_common_conversation_does_not_require_source_planning(self):
        for question in ("你是哪个模型", "你能做什么"):
            with self.subTest(question=question):
                self.assertEqual(route_by_rules(question).route, "direct")

    def test_recency_without_clear_public_subject_requires_planning(self):
        self.assertIsNone(route_by_rules("最新报销制度是什么？"))

    def test_long_questions_are_not_silently_truncated_before_search(self):
        self.assertEqual(route_by_rules("公司制度" + "要求" * 2600 + "ZX-81").route, "clarify")

    def test_mixed_attachment_request_is_not_sent_wholesale_to_web(self):
        self.assertIsNone(route_by_rules("对比附件与国家最新税收政策", has_attachments=True))
        plan = validate_plan("对比附件与国家最新税收政策", RoutePlan(
            route="web", web_query="对比附件与国家最新税收政策",
        ), has_attachments=True)
        self.assertEqual(plan.route, "clarify")

    def test_planner_cannot_reverse_temperature_or_drop_user_actions(self):
        question = "ZX-81 低于 30℃仍报警，已经重启，如何处理？"
        for query in ("ZX-81 高于 30℃仍报警，已经重启，如何处理？",
                      "ZX-81 低于 80℃仍报警，已经重启，如何处理？",
                      "ZX-81 低于 30℃仍报警，如何处理？"):
            with self.subTest(query=query):
                plan = validate_plan(question, RoutePlan(route="knowledge", knowledge_query=query))
                self.assertEqual(plan.route, "clarify")

    def test_multi_request_does_not_drop_weather_or_navigation(self):
        self.assertIsNone(route_by_rules("先查今天北京天气，再导航到天安门"))
        self.assertIsNone(route_by_rules("先查蓝屏原因，再找附近服务站"))


if __name__ == "__main__":
    unittest.main()
