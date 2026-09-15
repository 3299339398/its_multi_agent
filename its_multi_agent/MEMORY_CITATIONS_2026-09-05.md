# Long Conversation Memory and Citation Snapshots

Implemented on 2026-09-05. Scope: answer context and inspectable evidence.

## Behavior

- Older user messages feed incremental extractive memory, with original quotes and message IDs. Goals, constraints, corrections, facts, attempts and open questions have bounded storage. Assistant guesses are excluded.
- Rendering preserves the first goal/constraint and prioritizes recent updates within each category's budget. Explicit corrections remain visible for the model to interpret. This is rule-based extraction, not complete semantic conflict resolution.
- The default chat context uses the latest 12 visible messages plus a memory rendering bounded to 6000 characters. Archived messages remain available. This is not exact token budgeting or unlimited recall.
- Route planning receives the memory, enabling contextual follow-ups to refer to older device identifiers and requirements.
- Reviewed evidence snapshots are streamed before the answer and saved with that assistant message. Known inline citations and the source list open the snapshot viewer.
- The viewer includes excerpt, origin, source name and supplied page, sheet or version metadata. Truncated excerpts are labelled. Only validated HTTP(S) source URLs can be opened. Version is shown only when provided by the source.
- Unknown citations and code references remain ordinary text. Changing sessions unmounts the viewer, and delayed source events cannot attach to another session's answer.
- SQLite migration adds fields without replacing existing archives. Older summaries rebuild from archived messages when needed.

## Verification

- App backend: 117 tests passed, using isolated test databases.
- Knowledge backend: 44 tests passed.
- Chat frontend: 40 tests passed; production check build passed.
- Browser fixtures: 1440 x 1000 and 390 x 844 passed citation opening, excerpt/version display, modal bounds, Escape close, focus restoration, Markdown code formatting and horizontal overflow checks. Both had zero page errors; screenshots inspected.
- Local app API restarted; `/healthz` returned `status: ok`.
- Local chat preview: http://127.0.0.1:5173/

## Limits

- These are deterministic regression and browser fixture results, not measured live-model answer accuracy. Live Milvus retrieval and paid model evaluation were not run.
- Answers created before evidence snapshots were stored cannot retroactively recover their original evidence. The viewer shows saved excerpts, not an entire document reader.
- The bounded extractive memory can omit details. Earlier attachments outside the recent context are not automatically loaded again.
- No deployment or Docker work was performed in this change.
