import json
from pathlib import Path
import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.services.query_service import QueryService
from its_multi_agent.backend.knowledge.services.retrieval_service import RetrievalService
from its_multi_agent.backend.knowledge.test.test_query_service import FakeLlm


def regression_report():
    fixtures = json.loads((Path(__file__).parent / "fixtures" / "retrieval_regressions.json").read_text(encoding="utf-8"))
    service = RetrievalService.__new__(RetrievalService)
    dedup = []
    for case in fixtures["dedup"]:
        documents = [Document(page_content="Shared introduction. " * case["common_prefix_repeats"] + item["content"],
                              metadata=item["metadata"]) for item in case["documents"]]
        legacy_count = len({(doc.metadata.get("title", ""), doc.page_content[:100]) for doc in documents})
        dedup.append({"label": case["label"], "expected": case["expected_count"],
                      "before": legacy_count, "after": len(service._deduplicate(documents))})
    rewrites = fixtures["rewrites"]
    values = [item["value"] for item in rewrites["variants"]]
    legacy_accepted = list(dict.fromkeys(str(value).strip()[:5000] for value in values if str(value).strip()))
    with patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_ENABLED", True), \
         patch("its_multi_agent.backend.knowledge.services.query_service.settings.QUERY_REWRITE_VARIANTS", 20):
        accepted = QueryService(llm=FakeLlm(json.dumps(values))).build_search_queries(
            rewrites["original"], force_rewrite=True)[1:]
    return {"note": fixtures["description"], "dedup": dedup,
            "rewrites": {"labeled_variants": len(values),
                         "invalid_accepted_before": sum(not item["valid"] and str(item["value"]).strip() in legacy_accepted for item in rewrites["variants"]),
                         "invalid_accepted_after": sum(not item["valid"] and item["value"] in accepted for item in rewrites["variants"]),
                         "valid_accepted_after": sum(item["valid"] and item["value"] in accepted for item in rewrites["variants"])}}


class RegressionFixturesTest(unittest.TestCase):
    def test_labeled_regressions(self):
        report = regression_report()
        for case in report["dedup"]:
            with self.subTest(label=case["label"]):
                self.assertEqual(case["after"], case["expected"])
        self.assertEqual(report["rewrites"]["invalid_accepted_after"], 0)
        self.assertEqual(report["rewrites"]["valid_accepted_after"], 1)


if __name__ == "__main__":
    print(json.dumps(regression_report(), indent=2))
