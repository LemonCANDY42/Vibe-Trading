# Review: Moirix Extension V0

## Verdict

Approved for local personal-fork use.

The PRD's recommended direction is suitable for this fork: keep Vibe-Trading as
the primary research workbench, keep Moirix as an optional local extension, and
protect upstream sync by isolating custom code in narrow `moirix_*` files,
skills, swarm presets, and fork-owned docs.

This is the right shape for the current stage because it avoids rebuilding Vibe
loaders, agent loop, session/memory, backtest engines, or broker surfaces while
still exposing Moirix's differentiated value: PIT evidence status,
event-impact graph artifacts, and fail-closed authority boundaries.

## Blocking Findings

None remaining.

One issue was found during review and fixed before commit:

- The initial authority guard checked real-money authority fields only inside
  `payload["authority"]`. The PRD's `status` schema allows
  `ready_for_real_money_trading_authority` at the top level, so the Vibe wrapper
  now blocks top-level and nested authority violations. Regression coverage was
  added in `agent/tests/test_moirix_adapter_tools.py`.

## Non-Blocking Findings

- `event_signal.csv` export is intentionally deferred until Moirix exposes a
  stable `export-event-signal` adapter command.
- A dedicated `moirix_authority_guard` Vibe tool is intentionally deferred until
  Moirix exposes a stable `authority-check` adapter command.
- Frontend Moirix panels and IBKR paper-readiness checks should remain separate
  branches/stages.

## Files Reviewed

Implementation:

- `agent/src/tools/_moirix_adapter.py`
- `agent/src/tools/moirix_status_tool.py`
- `agent/src/tools/moirix_news_tool.py`
- `agent/src/tools/moirix_event_graph_tool.py`
- `agent/src/skills/moirix-event-graph/SKILL.md`
- `agent/src/swarm/presets/moirix_event_impact_desk.yaml`
- `agent/src/agent/context.py`

Tests:

- `agent/tests/test_moirix_adapter_tools.py`
- `agent/tests/test_swarm_presets_packaging.py`

Docs:

- `README.md`
- `wiki/docs/content.js`
- `wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md`
- `wiki/docs/kenny/CURRENT_GOAL.md`
- `wiki/docs/kenny/UPSTREAM_SYNC_POLICY.md`
- `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md`

## Commands Run

```bash
cmp -s /Users/kennymccormick/Downloads/PRD_PERSONAL_VIBE_MOIRIX_FORK.md \
  wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md

git diff --check
node --check wiki/docs/content.js

uv run --extra dev python -m pytest agent/tests/test_moirix_adapter_tools.py -q

uv run --extra dev python -m pytest \
  agent/tests/test_swarm_presets_packaging.py \
  agent/tests/test_swarm_preset_inspect.py \
  agent/tests/test_skills.py -q
```

Real local adapter smoke:

```text
status ok local_moirix_conda
query blocked ['source_lake_observed_window_does_not_cover_request']
graph ok /private/tmp/vibe-moirix-review-smoke-run/artifacts/moirix/event_impact_graph.json
```

## Observed Results

- PRD copy matches the downloaded source.
- `git diff --check` passed.
- `node --check wiki/docs/content.js` passed.
- Moirix adapter tool tests: 9 passed.
- skill/swarm/package tests: 29 passed.
- Real local Moirix adapter discovery succeeded through the sibling Moirix
  checkout and the local conda environment.
- Query-news preserved Moirix's blocked source-lake window result.
- Event graph build succeeded from run-local fixture evidence.

## Merge Recommendation

Keep this as one local fork commit for V0 foundation work. Do not upstream this
exact shape yet: upstreamable form should first replace Kenny-specific local
repo/conda discovery with a generic optional plugin configuration.

Next recommended work:

1. Push this branch after commit.
2. Run one end-to-end Vibe prompt using `moirix-event-graph`.
3. Add `export-event-signal` only after the Moirix adapter command is stable.
4. Keep IBKR and frontend work in separate branches.
