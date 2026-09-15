# Controlled Evidence Routing Implementation Plan

**Goal:** Enforce source selection and evidence checks before chat answers, with reproducible evaluation.

**Architecture:** A pure routing policy validates structured plans. A request-scoped evidence workflow performs bounded retrieval and model review. The chat service consumes its outcome before streaming the final answer.

**Tech Stack:** Existing Python, Pydantic, OpenAI Agents SDK, unittest. No added runtime dependency.

**Spec:** ../specs/2026-09-05-answer-routing-design.md

## Constraints

- Preserve the existing dirty worktree and deployment configuration; no commits requested.
- Honor plugin settings and private/public source boundaries.
- No paid external model calls for automated verification.

## Tasks

- [x] Add failing tests and implement routing policy, including contextual and mixed-source validation.
- [x] Add failing workflow tests and implement retrieval, identifier checks, evidence review, and bounded fallback.
- [x] Integrate chat preparation and terminal responses; test persistence and tool restrictions.
- [x] Add labeled business scenarios and evaluation CLI; distinguish offline checks from live answer accuracy.
- [x] Run relevant regression suites, inspect integration, update documentation and refresh local preview.

Verification: app 105 tests, knowledge 44 tests, 28 offline rule scenarios passed. The local chat API health endpoint and frontend returned successfully after refresh. No live paid-model accuracy benchmark was run; the existing Milvus connectivity limitation remains outside this deployment-free batch.
