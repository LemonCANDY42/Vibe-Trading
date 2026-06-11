# Current Goal: Vibe-Moirix Personal Fork V0

## Source Of Truth

- PRD: `wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md`
- Moirix adapter boundary: `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md`
- Local Moirix contract docs:
  - `/Users/kennymccormick/github/Moirix/docs/VIBE_EXTENSION_CONTRACT.md`
  - `/Users/kennymccormick/github/Moirix/docs/VIBE_NEWS_EVENT_GRAPH_ADAPTER.md`

The repository root `docs/` directory is ignored by this fork. Fork-owned
Kenny docs therefore live under `wiki/docs/kenny/`.

## Objective

Absorb the personal Vibe-Moirix PRD into the fork-owned docs area, keep the
current implementation aligned with a bounded V0 integration, and verify that
the optional Moirix tool path remains discoverable, fail-closed, and
upstream-friendly.

## Current V0 Scope

In scope now:

- Keep Vibe-Trading as the primary local research workbench.
- Keep Moirix as an optional local extension, not a replacement app.
- Add optional Vibe tools for:
  - `moirix_status`
  - `moirix_query_news`
  - `moirix_build_event_graph`
- Add one Moirix research skill:
  - `moirix-event-graph`
- Add one Moirix swarm preset:
  - `moirix_event_impact_desk`
- Write Moirix outputs only under the current run's `artifacts/moirix/`.
- Preserve `ok`, `blocked`, and `unavailable` adapter states exactly.
- Return fail-closed responses when Moirix is missing, blocked, returns invalid
  JSON, returns unknown status, or reports artifact paths outside the run
  artifact directory.
- Keep all real-money and broker-submit authority false.

Out of scope for this V0 branch:

- IBKR paper submission.
- Real-money execution.
- Frontend Moirix panels.
- A generic upstream plugin architecture.
- `event_signal.csv` export until the Moirix adapter exposes a stable
  `export-event-signal` command.
- A dedicated `moirix_authority_guard` Vibe tool until the Moirix adapter
  exposes a stable `authority-check` command.

## Runtime Sequence

```text
Vibe prompt or swarm worker
  -> load_skill("moirix-event-graph")
  -> moirix_status
  -> moirix_query_news(target, market, as_of, lookback_days)
  -> artifacts/moirix/*
  -> moirix_build_event_graph(target, as_of, input_path?)
  -> report Moirix coverage and authority boundaries
```

If Moirix returns `blocked` or `unavailable`, Vibe may still use `web_search`,
`read_url`, or existing event-driven CSV workflows, but those outputs must be
labelled as ad-hoc web research rather than PIT source-lake evidence.

## Quantitative Acceptance

The current goal is complete when all of the following are true:

- `wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md` exists and matches the
  downloaded PRD source.
- `wiki/docs/kenny/CURRENT_GOAL.md` defines current scope, exclusions, runtime
  sequence, and measurable acceptance.
- `wiki/docs/kenny/UPSTREAM_SYNC_POLICY.md` defines the fork sync policy and
  custom-code isolation rules.
- `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md` names the PRD source and marks
  implemented vs deferred Moirix extension pieces.
- `wiki/docs/content.js` exposes a docs-site entry for the Kenny fork docs.
- `git diff --check` passes.
- The targeted Moirix tool tests pass:

  ```bash
  uv run --extra dev python -m pytest agent/tests/test_moirix_adapter_tools.py -q
  ```

- The relevant packaging/skill/swarm tests pass:

  ```bash
  uv run --extra dev python -m pytest \
    agent/tests/test_swarm_presets_packaging.py \
    agent/tests/test_swarm_preset_inspect.py \
    agent/tests/test_skills.py -q
  ```

## Stop Conditions

Stop and ask before continuing if:

- completing the PRD would require broker credentials, live broker submission,
  or real-money authority;
- the Moirix adapter contract has changed and no longer matches the local Vibe
  wrapper;
- upstream sync introduces conflicts in Vibe core files that would require a
  broader architecture decision;
- the user wants `event_signal.csv`, `authority-check`, frontend panels, or
  IBKR work treated as part of the current branch instead of the next stage.

## Verification Evidence

Verified locally on 2026-06-12:

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

Observed results:

- PRD copy matches the downloaded source.
- `git diff --check` passed.
- `node --check wiki/docs/content.js` passed.
- `agent/tests/test_moirix_adapter_tools.py`: 9 passed.
- skill/swarm/package tests: 29 passed.

Review smoke against the real local Moirix checkout:

```text
status ok local_moirix_conda
query blocked ['source_lake_observed_window_does_not_cover_request']
graph ok /private/tmp/vibe-moirix-review-smoke-run/artifacts/moirix/event_impact_graph.json
```
