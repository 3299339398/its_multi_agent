# Conversation Memory and Citation Viewer

The user approved improving long conversations and inspectable citations. No deployment changes or unrelated feature expansion.

## Design

Replace repeated full-history truncation with incremental, extractive memory tied to original user message IDs. Persist a processing watermark and bounded structured categories for goals, constraints, facts, attempted actions, open questions, and corrections. Preserve user wording; assistant guesses must not become user facts. Explicit corrections are shown with precedence over older statements. This avoids an extra summarization model call and is not presented as universal semantic understanding.

Use bounded recent-history queries on the chat path, with a bounded memory rendering. Supply memory to both planning and final answer context, while retaining the original archive. Rebuild old truncated summaries lazily using original messages.

Persist reviewed evidence snapshots alongside assistant messages and send them as a typed SSE event before answer text. Render known citation IDs as accessible controls, with a source viewer showing the exact excerpt, provenance, page/sheet/version when available, truncation state, and safe external URL. Historical answers retain their evidence snapshot even when source content changes. Unknown citations remain plain text.

## Tasks

- [x] Write failing long-conversation and archive-source tests; implement incremental memory and additive schema migration.
- [x] Integrate bounded context, planner memory, source SSE and answer archival; verify request isolation.
- [x] Write frontend tests; implement citation rendering and a responsive, keyboard-accessible source viewer.
- [x] Run backend/frontend checks and desktop/mobile browser checks; refresh preview and document verified limits.
