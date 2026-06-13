# Moirix Event Thesis Extension Plan

This fork keeps Moirix as an optional local PIT evidence provider and makes Vibe
the Agent-driven thesis workbench. The canonical Moirix workflow is no longer a
numeric event-impact graph or event_signal backtest path. It is:

```text
moirix_status
  -> moirix_query_news
  -> moirix_portfolio_context
  -> moirix_write_event_thesis
  -> moirix_write_position_decision when a thesis should become a portfolio proposal
  -> moirix_export_decision_projection when a proposal should be backtested
  -> moirix_execute_trade_proposal only when an explicit execution approval exists
  -> moirix_authority_guard when a proposal needs review
```

## Repository Scope

This plan is a Kenny-fork extension plan, not an upstream Vibe-Trading feature
proposal. It is allowed to depend on Kenny's local Moirix checkout, local PIT
source-lake assumptions, fork-owned Moirix tools, fork-owned Moirix swarm
presets, and fork-owned Moirix UI panels.

Do not upstream this workflow as-is. If a future upstream contribution is
desired, split out only generic infrastructure with no Moirix dependency, such
as run artifact previews, usage reporting, report navigation, live status
display, chart payload optimization, or a generic plugin interface.

## Current Decision

The previous `event_impact_graph.json` / `event_signal.csv` direction was
removed from the Vibe-side tool surface. The issue was not implementation
quality; the artifact model was wrong for this fork's purpose. Edge `strength`,
numeric `confidence`, and `impact_score` made event relationships look like a
direct scoring system, while the desired product is an auditable Agent thesis:
what happened, how credible it is, which older events it updates or contradicts,
how it affects the target and sector, what the current portfolio context is, and
what would invalidate the view.

Historical local run files from the removed numeric workflow are not part of the
canonical Moirix UI/API preview and should not be used as success evidence for
new work.

## Ownership Boundary

Vibe owns:

- Agent synthesis and thesis artifacts;
- run artifact writes under `artifacts/moirix/`;
- skill and swarm workflow routing;
- Home and Run Detail UI for evidence, thesis, decision context, and authority;
- fail-closed presentation when evidence or portfolio context is unavailable.

Moirix owns:

- PIT source-lake evidence retrieval;
- source coverage and blocker claims;
- no-fake-evidence behavior for blocked/unavailable queries.

Vibe must not write Moirix source-lake, graph-truth, portfolio, ledger, broker,
or audit state. Vibe must not route news through market-data loaders. Vibe may
write its own run-local research proposal artifacts and, only through a separate
execution gate, may forward an explicitly approved paper-trading proposal to an
existing Vibe trading connector.

For IBKR, the connector split is explicit: `ibkr-paper-local` remains the
read-only readiness/profile for account and market-data checks, while
`ibkr-paper-trade` is the paper-only order profile. IBKR live profiles remain
read-only. Moirix tools may request the execution gate, but they do not own the
IBKR connector or bypass Vibe's approval checks.

## Canonical Artifacts

```text
artifacts/moirix/
  status.json
  request.json
  coverage_status.json
  news_evidence.jsonl
  event_thesis_graph.json
  event_thesis_report.md
  event_decision_context.json
  position_decision.json
  trade_proposal.json
  risk_sizing_report.json
  portfolio_adjustment_plan.md
  decision_projection.csv
  decision_projection.json
  backtest_projection_manifest.json
  execution_status.json
  authority_status.json
  vibe_run_card_patch.json
```

`event_thesis_graph.json` uses schema
`vibe.moirix_event_thesis.v1`. It must use semantic relations only:

- `supports`
- `contradicts`
- `supersedes`
- `updates`
- `duplicates`
- `weakens`
- `confirms`
- `causal_chain`

It must not use `strength`, `weight`, numeric `confidence`, or `impact_score`.

Authority must remain fail-closed:

```json
{
  "research_only": true,
  "paper_trade_proposal_allowed": false,
  "broker_submit_allowed": false,
  "ready_for_real_money_trading_authority": false
}
```

`position_decision.json` uses schema `vibe.moirix_position_decision.v1`. It is
the first artifact allowed to express add/trim/exit/buy/sell/short/cover/hedge
intent, but it remains a research proposal until an execution gate accepts it.
It must include:

- thesis and portfolio source artifact references;
- current holdings context used by the decision;
- decision action: `buy`, `sell`, `short`, `cover`, `add`, `trim`, `exit`,
  `hold`, `watch`, `hedge`, or `blocked`;
- rationale, invalidation triggers, execution window, and risk notes;
- risk sizing fields such as max notional, max loss, stop reference, and
  portfolio impact;
- authority fields.

`decision_projection.csv` and `decision_projection.json` are Vibe-side backtest
projection artifacts. They are derived from a position decision and normalized
trade proposal so historical tests can evaluate the decision logic. They are
not Moirix evidence, not event weights, and not broker orders.

`trade_proposal.json` is a normalized order-intent proposal, not an order. It
may contain one or more proposed orders, but by default the writer keeps:

```json
{
  "research_only": true,
  "paper_trade_proposal_allowed": false,
  "broker_submit_allowed": false,
  "ready_for_real_money_trading_authority": false
}
```

An execution approval is a separate JSON artifact that must reference the exact
proposal hash and explicitly grant paper execution authority:

```json
{
  "approved": true,
  "scope": "paper",
  "proposal_sha256": "...",
  "authority": {
    "paper_trade_proposal_allowed": true,
    "broker_submit_allowed": true,
    "ready_for_real_money_trading_authority": false
  }
}
```

Without this approval, `moirix_execute_trade_proposal` writes a blocked
`execution_status.json` and never calls a broker. The proposal itself remains
research-only by default; the separate approval artifact is the paper-execution
authority grant.

## Tool Surface

Canonical tools:

- `moirix_status`
- `moirix_query_news`
- `moirix_portfolio_context`
- `moirix_write_event_thesis`
- `moirix_write_position_decision`
- `moirix_export_decision_projection`
- `moirix_execute_trade_proposal`
- `moirix_authority_guard`

Removed Vibe-side tools:

- `moirix_build_event_graph`
- `moirix_export_event_signal`
- `moirix_event_signal_backtest`

These were removed rather than marked legacy so the Agent cannot accidentally
route new research through the old numeric graph/signal path.

## Agent Workflow

The normal Agent flow is:

1. Load `moirix-event-graph` skill when the user asks for news/event/PIT/Moirix
   analysis.
2. Call `moirix_status`.
3. Call `moirix_query_news`.
4. Call `moirix_portfolio_context` when holdings, cash, open orders, or IBKR
   paper context matter. Missing context is `blocked` or `unavailable`, not fake
   positions.
5. Synthesize a thesis with:
   - evidence item truth status;
   - source quality;
   - semantic event-to-event relations;
   - target/sector/supply-chain impact path;
   - current stance and actionability;
   - execution window;
   - open questions and invalidation triggers;
   - authority fields.
6. Call `moirix_write_event_thesis`.
7. If the user asks for a current-position or new-target decision, synthesize a
   position decision and call `moirix_write_position_decision`.
8. If the user asks for historical evaluation or backtesting, call
   `moirix_export_decision_projection`. The projection must remain research-only
   and must not be treated as Moirix evidence or a broker order.
9. Use `moirix_authority_guard` for proposal checks.
10. Only if the user has provided an explicit execution approval artifact, call
   `moirix_execute_trade_proposal`. In v1, live execution is blocked. Paper
   execution is allowed only when the proposal hash, approval authority,
   selected connector, and trading service all pass their own gates.

## Decision And Execution Boundary

The decision layer answers:

- should the current position be held, added, trimmed, exited, hedged, or
  watched;
- should a new target be proposed long, short, or avoided;
- how large the proposal may be relative to cash, portfolio value, thesis
  uncertainty, and risk budget;
- what invalidates the proposal.

The backtest projection layer answers:

- how the research proposal is represented as dated, auditable rows;
- which symbol/action/side/size the backtest may consume;
- which source decision hash and authority fields bound the projection.

The execution layer answers a different question:

- is this exact proposal authorized for paper execution now;
- does the selected trading connector support the requested order path;
- did the broker accept, reject, or fail the order request.

The thesis and decision layers must never self-enable execution. The execution
layer must be independently auditable and fail closed.

## TradingAgents Reference Boundary

TauricResearch/TradingAgents is used as an architectural reference for role
separation only: analyst, researcher, risk, and portfolio-manager style agents.
This fork does not vendor TradingAgents or embed its LangGraph runtime in v1.
Re-evaluate an optional adapter only after the thesis schema and local workflow
are stable.

## UI Contract

Home shows only canonical Moirix event thesis or position-decision runs. A run
with only old numeric graph/signal artifacts is not a Moirix Event Thesis or
Position Decision success.

Run Detail tabs:

- Moirix Evidence
- Event Thesis
- Decision Context
- Position Decision
- Authority

The Position Decision tab shows both the backtest projection and the execution
gate status when those artifacts exist. No special legacy graph/signal manifest
is exposed in the Moirix UI.

## Acceptance Criteria

- Missing Moirix adapter returns `unavailable`, not a crash.
- Blocked source coverage does not create fake `news_evidence.jsonl`.
- `moirix_write_event_thesis` refuses `strength`, `weight`, numeric
  `confidence`, and `impact_score`.
- `moirix_portfolio_context` does not fabricate positions when read-only
  context is missing.
- `moirix_write_position_decision` refuses to write a trade proposal without an
  existing thesis and portfolio context.
- `moirix_write_position_decision` writes research-only proposal artifacts by
  default.
- `moirix_export_decision_projection` writes research-only backtest projection
  artifacts and refuses broker-authorized proposals.
- `moirix_execute_trade_proposal` blocks without an explicit approval artifact
  and blocks all live execution in v1.
- All authority fields remain research-only and false for broker/real-money
  paths.
- New tool registry and MCP surfaces expose the canonical tools and do not
  expose the removed graph/signal tools.
- Home and Run Detail render thesis/context artifacts and ignore old
  graph/signal artifacts as success evidence.
