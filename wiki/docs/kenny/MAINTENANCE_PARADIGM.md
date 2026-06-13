# Kenny Fork Maintenance Paradigm

Status: standard for `Vibe-Trading-Kenny` maintenance work.

## Core Position

`Vibe-Trading-Kenny` is Kenny's personal trading research agent workbench.

The Moirix thesis, position-decision, backtest projection, and paper
execution-gate workflow is a Kenny-fork-only extension. It must not be proposed
as a general `HKUDS/Vibe-Trading` upstream feature in this shape. Upstream PRs
should stay generic and Moirix-free unless a future project decision explicitly
creates a plugin contract accepted by upstream maintainers.

The maintenance model is:

```text
Vibe stays the primary workbench.
Moirix stays an optional local PIT evidence provider.
Agent synthesis produces event theses.
Position decision agents turn theses into research-only portfolio proposals.
Research and simulation stay default.
Broker submit stays behind a separate explicit execution gate.
Real-money authority stays fail-closed.
```

## Source Documents

Read these before changing the Moirix/Vibe integration path:

- `wiki/docs/kenny/CURRENT_GOAL.md`
- `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md`
- `wiki/docs/kenny/UPSTREAM_SYNC_POLICY.md`
- `wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md`
- `/Users/kennymccormick/github/Moirix/docs/VIBE_EXTENSION_CONTRACT.md`
- `/Users/kennymccormick/github/Moirix/docs/VIBE_NEWS_EVENT_GRAPH_ADAPTER.md`

If current implementation discoveries change the plan, update the relevant doc
in the same change set.

## Standard Workflow

### 1. Define The Bounded Target

Before implementation, state:

- the concrete user outcome;
- the source of truth;
- the current stage;
- in-scope and out-of-scope surfaces;
- tests, smoke commands, and review evidence required.

Use `wiki/docs/kenny/CURRENT_GOAL.md` for the active branch-level target when
the work changes integration scope or acceptance criteria.

### 2. Keep Vibe First

Prefer routing, skills, tools, artifacts, and UI previews over Vibe core
rewrites. Do not rebuild Vibe capabilities that already exist: AgentLoop,
sessions, memory, skills, swarms, run artifacts, data loaders, backtest engines,
web UI, MCP server, and broker connector boundaries.

Keep upstream-facing work separate from Kenny-only Moirix work:

- upstream-friendly branches may contain generic run library, usage, reports,
  live-status, chart-payload, or framework fixes;
- Kenny-only branches may contain Moirix source-lake assumptions, local adapter
  paths, Moirix thesis and decision tools, and fork-specific execution gates;
- never mix the two categories in one PR or commit intended for upstream.

### 3. Keep Moirix Optional

Moirix integration must continue to run as optional local tools:

- missing adapter returns `status: "unavailable"`;
- blocked source coverage returns `status: "blocked"`;
- invalid adapter JSON returns `status: "unavailable"`;
- unknown adapter status is converted to `status: "blocked"`;
- Vibe reports the Moirix state directly rather than fabricating PIT evidence.

### 4. Use Thesis-First Event Reasoning

The canonical Moirix workflow is:

```text
moirix_status
  -> moirix_query_news
  -> moirix_portfolio_context
  -> moirix_write_event_thesis
  -> moirix_write_position_decision when a thesis becomes a proposal
  -> moirix_export_decision_projection when a proposal should be backtested
  -> moirix_execute_trade_proposal only with explicit execution approval
  -> moirix_authority_guard when needed
```

Do not reintroduce the removed numeric graph/signal path as a primary workflow:

- no `event_impact_graph.json` as canonical output;
- no edge `strength`;
- no edge `weight`;
- no numeric `confidence`;
- no `impact_score`;
- no `event_signal.csv` as the main Moirix output.

The canonical artifacts are:

```text
artifacts/moirix/news_evidence.jsonl
artifacts/moirix/event_thesis_graph.json
artifacts/moirix/event_thesis_report.md
artifacts/moirix/event_decision_context.json
artifacts/moirix/position_decision.json
artifacts/moirix/trade_proposal.json
artifacts/moirix/risk_sizing_report.json
artifacts/moirix/portfolio_adjustment_plan.md
artifacts/moirix/decision_projection.csv
artifacts/moirix/decision_projection.json
artifacts/moirix/backtest_projection_manifest.json
artifacts/moirix/execution_status.json
artifacts/moirix/authority_status.json
artifacts/moirix/vibe_run_card_patch.json
```

### 5. Keep Decision And Execution Separated

Never introduce a direct path from Moirix evidence or Agent thesis output to
orders. A valid path must pass through all of these layers:

```text
event thesis
  -> position decision
  -> trade proposal
  -> optional backtest projection for historical evaluation
  -> explicit execution approval
  -> execution gate
  -> existing Vibe trading connector / live mandate guard
```

The thesis and decision agents must not self-enable execution. The execution
gate must verify the exact proposal hash and fail closed when approval,
connector capability, profile environment, or authority is ambiguous.

Backtest projection is not execution. Projection artifacts may be used by Vibe
backtests, but they must remain research-only and carry false broker/real-money
authority fields.

The proposal remains research-only by default. A separate paper execution
approval artifact may grant `paper_trade_proposal_allowed=true` and
`broker_submit_allowed=true`, but it must keep
`ready_for_real_money_trading_authority=false` and match the exact proposal
hash.

The following must remain blocked unless a future PRD explicitly changes the
contract and adds independent review evidence:

- broker submit without explicit execution approval;
- silent order placement;
- real-money execution;
- agent self-enabling of kill switches;
- claiming trading authority from event thesis output.

Required authority fields:

```json
{
  "research_only": true,
  "paper_trade_proposal_allowed": false,
  "broker_submit_allowed": false,
  "ready_for_real_money_trading_authority": false
}
```

Paper execution may be added only as a separate, auditable workflow. Live
execution remains out of scope for the current Moirix decision layer.

### 5.1 IBKR Paper Read-Only Discipline

The logged-in IB Gateway paper account may be used only for read-only readiness
and portfolio-context artifacts unless a later PRD explicitly authorizes a
paper-order workflow.

Allowed:

- connectivity checks;
- account summary reads;
- positions reads;
- open order inspection;
- executions/history inspection;
- market-data permission checks;
- historical-data permission checks.

Forbidden:

- `placeOrder`;
- `cancelOrder`;
- `reqGlobalCancel`;
- order transmit;
- simulated submit;
- live submit.

If read-only portfolio context is unavailable, return `blocked` or
`unavailable`. Do not fabricate positions.

### 6. Label Evidence Precisely

Moirix PIT source-lake evidence, provider API evidence, ad-hoc web research,
and user-uploaded files are different evidence tiers.

Rules:

- do not call `web_search` or `read_url` PIT-valid unless Moirix proves it;
- do not route news through market-data loaders;
- do not claim universal coverage from a partial source window;
- show source gaps and coverage blockers in artifacts or final reports.

### 7. Verify The Production Path

Default validation for Moirix event thesis work:

```bash
git diff --check
node --check wiki/docs/content.js

PYTHONPATH=agent .venv/bin/pytest agent/tests/test_moirix_adapter_tools.py -q
PYTHONPATH=agent .venv/bin/pytest agent/tests/test_run_card.py -q
PYTHONPATH=agent .venv/bin/pytest agent/tests/test_mcp_regression.py agent/tests/test_mcp_server_smoke.py -q

npm run test:run -- src/pages/__tests__/Home.test.tsx src/pages/__tests__/RunDetail.test.tsx
npm run build
```

When real local Moirix is relevant, also run a smoke that proves:

```text
moirix_status -> ok or unavailable
moirix_query_news -> ok or blocked, preserving blockers
moirix_write_event_thesis -> ok from run-local evidence fixture
moirix_portfolio_context -> ok from read-only snapshot or blocked without fake positions
```

### 8. Review Before Commit

Review for:

- upstream conflict risk;
- optional-missing behavior;
- fail-closed blocked/unavailable states;
- path traversal and artifact-root safety;
- authority violations;
- absence of broker/order/live-trading surfaces;
- accurate PIT vs ad-hoc labels;
- tests that exercise the production path.

Record meaningful reviews under `wiki/docs/kenny/REVIEW_*.md` when the change
alters this integration pattern or promotes a new stage.

## Commit And Sync Discipline

Keep commits logically scoped. Do not mix upstream-friendly PR work with
Kenny-only Moirix thesis changes.

Before pushing or syncing with upstream:

```bash
git status --short --branch
git fetch upstream
git diff --check
```

After an upstream merge, rerun the relevant validation set and update
`wiki/docs/kenny/CURRENT_GOAL.md` if the stage or acceptance criteria changed.

## Stop Conditions

Stop and report clearly if:

- Moirix adapter behavior contradicts the documented PIT evidence contract;
- a tool would need broker write authority to continue;
- a path-safety check cannot prove artifacts stay inside the run directory;
- an Agent output cannot be validated without reintroducing numeric graph
  semantics;
- tests show ordinary Vibe workflows break when Moirix is missing.
