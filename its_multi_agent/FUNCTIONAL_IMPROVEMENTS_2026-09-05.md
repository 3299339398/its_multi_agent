# Functional and Answer-Quality Improvements

Date: 2026-09-05. Scope: chat functionality and evidence quality. No Docker or deployment configuration changes in this batch.

## Changes

- Model creation uses server-generated IDs, reports duplicate names, and persists actual tool/vision capabilities. Default models are resolved lazily. Requests honor the selected model and its capabilities.
- Streaming retries are allowed only before answer/reasoning output or tool side effects. Stream cleanup cancels unfinished SDK runs. Answer whitespace is preserved end to end.
- Requests and delayed callbacks are scoped to the originating session and authentication generation. Switching sessions and logging out invalidate old results. Logout clears temporary credentials and model configuration.
- Attachment references survive archival and subsequent questions. Model context reloads bounded evidence (8 recent files, 30,000 characters per document, 60,000 total), with explicit truncation/unavailable markers. Current files are validated before archival; missing historical files do not break later requests. Word tables and workbook sheet labels are included.
- Chat knowledge tools request original evidence without an intermediate generated answer. Sources expose stable IDs, excerpts, provenance, and ranking-score semantics. Prompts require evidence-based citations and acknowledgment of missing/conflicting evidence.
- Deduplication preserves distinct complete chunks and provenance. Query rewrite guards reject changes to protected identifiers, quantities, comparison and negation tokens. This is a conservative lexical guard, not a semantic-equivalence proof.
- Mobile chat uses a collapsible drawer; custom model configuration remains available with an empty model list. Archived attachments display filename chips.

## Verification

| Area | Result |
| --- | --- |
| App backend | 62 tests passed |
| Knowledge backend | 44 tests passed |
| Chat frontend | 30 tests passed; build passed |
| Knowledge frontend | 5 tests passed; lint and build passed |
| Harness | 3 tests passed |
| Browser smoke | 1440x1000 and 390x844; no page errors or horizontal page overflow; exact code whitespace |

Total: 144 automated tests. Backend tests used isolated temporary databases. Browser checks used API fixtures, not paid model requests.

Synthetic regression fixtures (`backend/knowledge/test/fixtures/retrieval_regressions.json`) show:

- Distinct chunks sharing a prefix: retained count 1 -> 2, expected 2.
- Identical text from different documents/pages: retained count 1 -> 3, expected 3.
- Exact duplicates: retained count remains 1, expected 1.
- Ten labeled rewrite variants: invalid variants accepted 9 -> 0; the valid variant remains accepted.

These counts demonstrate specific regression fixes, not production accuracy percentages. Reproduce with the knowledge virtual environment: `python -m its_multi_agent.backend.knowledge.test.test_regression_fixtures`.

## Remaining Evaluation

Local chat preview: http://127.0.0.1:5173/. The updated standalone knowledge service could not connect to Milvus at 127.0.0.1:19530, so live retrieval integration remains unverified. Existing Docker services and deployment settings were left in place; the preview's existing knowledge endpoint may still run older code. Local document parsing dependencies and pymilvus were installed for verification; the knowledge virtual environment uses setuptools 80.10.2 for legacy pkg_resources compatibility.

No live LLM answer benchmark, load test, or production accuracy claim is included. Citation instructions do not guarantee model compliance. A real evaluation set should contain expected answers and source locations, including near-identical model numbers, numerical limits, conflicting documents, attachment follow-ups, and unanswerable questions. Measure retrieval recall, citation correctness, answer correctness, and appropriate abstention separately before further tuning retrieval depth, reranking, or prompts.

The earlier overall review remains a baseline, not a claim that every finding has been resolved. Task-state recovery, key rotation, and broader security/deployment concerns were outside this batch.
