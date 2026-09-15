# Controlled Evidence Routing

The user approved implementing source rules, semantic intent understanding, evidence checks, and an evaluation set in the existing chat flow. Deployment is outside scope.

Before answer generation, classify clear source requirements with deterministic rules. Internal ownership overrides recency. Ambiguous, contextual, and mixed requests use a tool-free structured planner with the selected model. Code validates the plan, honors disabled plugins, and never sends an internal question wholesale to public search. Attachment questions use existing hydrated context; location requests retain the existing service tool.

Knowledge and web routes execute bounded retrieval before the answering agent. Original evidence is normalized and explicit product/error/version identifiers checked. A tool-free structured evidence reviewer checks subject, version, conditions, conflicts, and coverage. Ranking scores are never used as probabilities. Empty, mismatched, conflicting, or unverified evidence produces a deterministic clarification/limitation response. Public fallback is permitted only for a validated public query; it cannot substitute for private facts. Errors fail closed and never masquerade as no results.

Grounded generation receives only reviewed sources and source-bound instructions, with additional retrieval tools disabled for that request. Existing session, attachment, streaming, retry, and map workflows remain integrated. This improves grounding but is not proof of every generated statement's truth.

Tests cover actual workflow decisions with external model/search clients replaced by controlled doubles. A labeled, synthetic business fixture set and CLI evaluate deterministic routing and observed end-to-end predictions separately. Report route accuracy, evidence recall, citation precision, abstention decisions, and answer-term coverage (not semantic correctness). No claim of real-world accuracy without actual model runs and human-reviewed answers.
