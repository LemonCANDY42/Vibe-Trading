# Kenny Fork Maintenance Paradigm

Status: standard for `Vibe-Trading-Kenny` maintenance work.

This document turns the PRD's recommended working style into the default
maintenance workflow for this personal fork. It applies to non-trivial feature,
integration, architecture, docs, review, and upstream-sync work.

## Core Position

`Vibe-Trading-Kenny` is Kenny's personal trading research agent workbench.

The maintenance model is:

```text
Vibe-Trading core stays primary and upstream-compatible.
Moirix stays an optional local extension.
Research and simulation stay default.
Broker submit and real-money authority stay fail-closed.
```

This is suitable because it preserves the existing Vibe surface area: CLI/TUI,
web UI, MCP server, agent loop, skills, swarms, sessions, memory, data loaders,
backtest engines, and broker connector boundaries. Moirix contributes only the
parts that are differentiated: PIT evidence status, event-impact graph
artifacts, coverage/leakage checks, and authority boundaries.

## Source Documents

Read these before changing the Moirix/Vibe integration path:

- `wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md`
- `wiki/docs/kenny/CURRENT_GOAL.md`
- `wiki/docs/kenny/UPSTREAM_SYNC_POLICY.md`
- `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md`
- `/Users/kennymccormick/github/Moirix/docs/VIBE_EXTENSION_CONTRACT.md`
- `/Users/kennymccormick/github/Moirix/docs/VIBE_NEWS_EVENT_GRAPH_ADAPTER.md`

If current implementation discoveries change the plan, update the relevant doc
in the same change set.

## Standard Workflow

### 1. Define The Bounded Target

Before implementation, state:

- the concrete user outcome;
- the source of truth;
- the current stage, such as V0, V1, or deferred;
- what is in scope;
- what is explicitly out of scope;
- the exact tests, smoke commands, or review evidence required.

Use `wiki/docs/kenny/CURRENT_GOAL.md` for the active branch-level target when
the work changes integration scope or acceptance criteria.

### 2. Keep Vibe First

Do not rebuild Vibe capabilities that already exist:

- CLI/TUI;
- FastAPI/web surfaces;
- MCP server;
- agent loop;
- session and memory systems;
- skills and swarms;
- data loaders;
- backtest engines;
- Alpha Zoo;
- broker connector surfaces.

Prefer routing, skills, tools, artifacts, and docs over core rewrites.

### 3. Keep Moirix Optional

Moirix integration should be callable through optional local tools and stable
adapter contracts. Vibe must continue to run when Moirix is missing.

Required behavior:

- missing adapter returns `status: "unavailable"`;
- blocked source coverage returns `status: "blocked"`;
- invalid adapter JSON returns `status: "unavailable"`;
- unknown adapter status is converted to `status: "blocked"`;
- Vibe reports the Moirix state directly rather than fabricating PIT evidence.

### 4. Isolate Custom Code

Prefer new files under:

```text
wiki/docs/kenny/
wiki/docs/moirix/
agent/src/tools/_moirix_adapter.py
agent/src/tools/moirix_*.py
agent/src/skills/moirix-*/
agent/src/swarm/presets/moirix_*.yaml
agent/tests/test_moirix_*.py
```

Edits to upstream-heavy files must stay small and explainable. Expected touch
points are registry, routing, counts, and docs index files.

### 5. Keep Research-Only Authority

Never introduce a direct path from Moirix graph scores to orders.

The following must remain blocked unless a future PRD explicitly changes the
contract and adds independent review evidence:

- broker submit;
- silent order placement;
- real-money execution;
- agent self-enabling of kill switches;
- claiming trading authority from event graph confidence.

Check both top-level and nested authority fields from adapter payloads. Any
true real-money or broker-submit authority field must fail closed.

### 5.1 IBKR Paper Read-Only Discipline

The logged-in IB Gateway paper account may be used only for read-only readiness
checks unless a later PRD explicitly authorizes a paper-order workflow.
Use `ibkr_paper_readiness` as the standard readiness artifact path; do not
compose ad-hoc order or cancel API calls for this purpose.

Gateway state does not grant project authority. If IB Gateway has "Read-Only
API" disabled, treat the environment as capable of broker writes and enforce
read-only behavior in the Vibe/Moirix code path.

Allowed in the current PRD:

- connectivity checks;
- account summary reads;
- positions reads;
- open orders inspection;
- executions/history inspection;
- market-data permission checks;
- historical-data permission checks.

Forbidden in the current PRD:

- `placeOrder`;
- `cancelOrder`;
- `reqGlobalCancel`;
- order transmit;
- simulated submit;
- live submit;
- any helper that lets event graph confidence become a broker write.

Avoid API client-id behavior that binds, modifies, cancels, or otherwise
changes manually entered orders. If a read-only check cannot be implemented
without such behavior, return `blocked` and document the blocker.

### 6. Label Evidence Precisely

Moirix PIT source-lake evidence, provider API evidence, ad-hoc web research,
and user-uploaded files are different evidence tiers.

Rules:

- do not call `web_search` or `read_url` PIT-valid unless Moirix explicitly
  proves it;
- do not route news through `backtest/loaders`;
- do not claim universal coverage from a partial source window;
- show source gaps and coverage blockers in the run artifact or final report.

### 7. Verify The Production Path

Match tests to the changed surface.

For current Moirix V0 maintenance, the default validation set is:

```bash
git diff --check
node --check wiki/docs/content.js

uv run --extra dev python -m pytest agent/tests/test_moirix_adapter_tools.py -q

uv run --extra dev python -m pytest \
  agent/tests/test_swarm_presets_packaging.py \
  agent/tests/test_swarm_preset_inspect.py \
  agent/tests/test_skills.py -q
```

When the real local Moirix checkout is relevant, also run a smoke that proves:

```text
moirix_status -> ok or unavailable
moirix_query_news -> ok or blocked, preserving blockers
moirix_build_event_graph -> ok from run-local evidence fixture
```

### 8. Review Before Commit

Use review as a gate, not a postscript.

Review for:

- upstream conflict risk;
- optional-missing behavior;
- fail-closed blocked/unavailable states;
- path traversal and artifact-root safety;
- top-level and nested authority violations;
- absence of broker/order/live-trading surfaces;
- accurate PIT vs ad-hoc evidence labels;
- tests that exercise the production path.

Record meaningful reviews under `wiki/docs/kenny/REVIEW_*.md` when the change
alters this integration pattern or promotes a new stage.

## Stage Rules

### Current V0 Pattern

Allowed:

- optional local adapter wrapper;
- `moirix_status`;
- `moirix_query_news`;
- `moirix_build_event_graph`;
- `moirix-event-graph` skill;
- `moirix_event_impact_desk` swarm;
- run artifacts under `artifacts/moirix/`;
- fail-closed status preservation.

Deferred:

- `moirix_export_event_signal` until adapter `export-vibe-artifacts` can expose
  or copy `event_signal.csv` under the frozen contract;
- `moirix_authority_guard` until adapter `authority-check` is stable;
- frontend Moirix panels;
- IBKR paper read-only readiness;
- paper submit;
- real-money authority.

### Promotion Criteria

Only promote a deferred stage when all are true:

- the upstream or Moirix contract is stable enough to wrap;
- the implementation is isolated from Vibe core where possible;
- docs define the new runtime sequence and fail states;
- targeted tests cover success, blocked, unavailable, and unsafe inputs;
- an independent review finds no remaining blocking findings.

## Commit And Sync Discipline

Keep commits logically scoped:

- one commit for a coherent V0 foundation is acceptable;
- split docs/runtime/frontend/broker stages when their risks differ;
- do not mix IBKR, frontend, and event-signal export into unrelated changes.

Before pushing or syncing with upstream:

```bash
git status --short --branch
git fetch upstream
git diff --check
```

After an upstream merge, rerun the relevant validation set and update
`wiki/docs/kenny/CURRENT_GOAL.md` if the stage or acceptance criteria changed.

## Stop Conditions

Stop and ask before proceeding when:

- the change requires broker credentials, order submission, or real-money
  authority;
- the Moirix adapter contract no longer matches the Vibe wrapper;
- upstream merge conflicts would require broad Vibe core rewrites;
- the requested work crosses from research artifacts into execution authority;
- a fallback would hide missing PIT coverage or source-lake blockers.
