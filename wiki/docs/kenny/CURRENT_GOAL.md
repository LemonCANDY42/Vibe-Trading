# Current Goal: Moirix Agent-Driven Event Thesis And Position Decision Workflow

## Source Of Truth

- Plan: `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md`
- Maintenance paradigm: `wiki/docs/kenny/MAINTENANCE_PARADIGM.md`
- Historical input PRD: `wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md`
- Upstream sync policy: `wiki/docs/kenny/UPSTREAM_SYNC_POLICY.md`

The historical PRD remains useful background, but the current canonical goal is
the event-thesis plus position-decision workflow. Any old instruction that makes
`event_impact_graph.json`, edge weights, `event_signal.csv`, or forward-return
studies the main Moirix output is superseded.

## Repository Scope

This goal is Kenny-fork-only. The Moirix thesis, position-decision, backtest
projection, and paper execution-gate surfaces are personal workflow extensions
for `LemonCANDY42/Vibe-Trading-Kenny` on
`feat/moirix-event-graph-extension-v0`.

Do not submit this Moirix workflow as a feature PR to `HKUDS/Vibe-Trading`.
Upstream-friendly work must remain separate and generic, for example run
library, usage artifacts, report navigation, or chart-payload optimization.
The Moirix integration may be rebased or synced with upstream, but it should
stay isolated in Kenny-owned docs, `moirix_*` tools, Moirix skills, Moirix swarm
presets, and Moirix UI panels.

## Objective

Turn the Kenny fork's Moirix integration into an Agent-driven event thesis and
position decision workflow:

```text
PIT evidence
  -> semantic event relationships
  -> target/sector impact analysis
  -> read-only portfolio context
  -> bull/bear/risk synthesis
  -> research-only event thesis artifacts
  -> research-only position decision and trade proposal artifacts
  -> research-only backtest projection artifacts when historical evaluation is requested
  -> explicit paper execution gate when separately approved
```

Moirix remains optional and fail-closed. Vibe remains the primary research
workbench. Real-money authority remains false. Broker submit is available only
through a separate execution gate and remains blocked unless a future explicit
approval artifact, connector profile, and runtime gate all pass.

## Canonical Outcome

A successful Moirix thesis run writes:

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

`event_thesis_graph.json` must:

- use `schema_version: "vibe.moirix_event_thesis.v1"`;
- use semantic event relations rather than weights;
- include truth status, source quality, target relevance, impact path, impact
  direction, impact horizon, invalidation triggers, and open questions;
- keep `research_only=true`;
- keep `paper_trade_proposal_allowed=false`;
- keep `broker_submit_allowed=false`;
- keep `ready_for_real_money_trading_authority=false`.

Forbidden in the canonical thesis graph:

- `strength`;
- `weight`;
- numeric `confidence`;
- `impact_score`.

## Implementation Status

Active implementation branch:

```text
feat/moirix-event-graph-extension-v0
```

Current stage:

- remove the old Vibe-side numeric graph/signal tools;
- add `moirix_write_event_thesis`;
- add `moirix_portfolio_context`;
- add `moirix_write_position_decision`;
- add `moirix_export_decision_projection`;
- add `moirix_execute_trade_proposal` as a fail-closed execution gate;
- replace `moirix_event_impact_desk` with `moirix_event_thesis_committee`;
- update Agent routing, skill docs, Home, Run Detail, API previews, and tests;
- remove old local numeric Moirix run artifacts from this workspace.

## In Scope

- `moirix_status`
- `moirix_query_news`
- `moirix_portfolio_context`
- `moirix_write_event_thesis`
- `moirix_write_position_decision`
- `moirix_export_decision_projection`
- `moirix_execute_trade_proposal`
- `moirix_authority_guard`
- `moirix-event-graph` skill rewritten as event thesis guidance
- `moirix_event_thesis_committee` swarm preset
- `moirix_position_decision_committee` swarm preset
- Run API previews for thesis/context/position artifacts
- Home Moirix Event Thesis and Position Decision dashboard
- Run Detail tabs:
  - Moirix Evidence
  - Event Thesis
  - Decision Context
  - Position Decision
  - Authority

## Out Of Scope

- Direct broker submit.
- Real-money authority.
- Paper-order execution without an explicit execution approval artifact.
- Vendor or runtime integration of TauricResearch/TradingAgents.
- News routed through market-data loaders.
- Reintroducing `event_signal.csv` as a primary Moirix output.
- Treating backtest projections as Moirix evidence or broker orders.

## Acceptance Criteria

- Tool registry exposes the canonical Moirix tools and not the removed
  graph/signal/backtest tools.
- `moirix_write_event_thesis` writes thesis/report/authority artifacts when
  PIT evidence exists.
- `moirix_write_event_thesis` blocks old numeric graph fields.
- `moirix_portfolio_context` writes blocked/unavailable context without fake
  positions when no read-only portfolio artifact exists.
- `moirix_write_position_decision` writes position decision, normalized trade
  proposal, risk sizing report, and portfolio adjustment plan artifacts.
- `moirix_write_position_decision` keeps proposal authority research-only and
  broker-submit false by default.
- `moirix_export_decision_projection` writes research-only backtest projection
  artifacts from position decisions without broker authority.
- `moirix_execute_trade_proposal` blocks when approval authority, proposal hash,
  connector profile, or execution mode is missing or unsafe.
- Live execution remains blocked in this goal.
- Run API surfaces `event_thesis_graph`, `event_thesis_report_markdown`, and
  `event_decision_context`, plus position decision artifacts when present.
- Home only treats canonical thesis/context/position artifacts as Moirix Event
  Thesis or Position Decision runs.
- Run Detail displays Evidence, Event Thesis, Decision Context, Position
  Decision, and Authority.
- Tests cover backend tools, Run API preview, Home, Run Detail, skill/swarm
  packaging, and MCP/tool registry.
