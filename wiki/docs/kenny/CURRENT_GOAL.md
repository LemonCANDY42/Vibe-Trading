# Current Goal: Daily Moirix/Vibe Decision Reliability

## Source Of Truth

- Plan: `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md`
- Maintenance paradigm: `wiki/docs/kenny/MAINTENANCE_PARADIGM.md`
- Historical input PRD: `wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md`
- Upstream sync policy: `wiki/docs/kenny/UPSTREAM_SYNC_POLICY.md`

The historical PRD remains useful background, but the current canonical goal is
the event-thesis plus position-decision workflow hardened enough for serious
daily research operations. Any old instruction that makes
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

Make the Kenny fork's Moirix/Vibe workflow reliable enough for daily
public-equity decision operations while keeping real-money execution authority
disabled by default. The target workflow is:

```text
PIT evidence
  -> semantic event relationships
  -> target/sector impact analysis
  -> read-only portfolio context
  -> bull/bear/risk synthesis
  -> research-only event thesis artifacts
  -> research-only position decision and trade proposal artifacts
  -> sized, research-only backtest projection artifacts when historical evaluation is requested
  -> explicit paper execution gate when separately approved and idempotency gates pass
```

Moirix remains optional and fail-closed. Vibe remains the primary research
workbench. Real-money authority remains false. Broker submit is available only
through a separate execution gate and remains blocked unless a future explicit
approval artifact, connector profile, and runtime gate all pass.

IBKR paper execution is handled by Vibe, not Moirix. The read-only readiness
profile remains `ibkr-paper-local`; paper order execution uses the separate
`ibkr-paper-trade` profile only after an explicit paper approval artifact and
execution gate pass. IBKR live profiles remain read-only.

Daily reliability means:

- every Moirix adapter call that writes run artifacts also writes
  `adapter_call_status.json` with phase, status, timeout, blockers, command
  source, cwd, and fail-closed state;
- every accepted thesis is grounded in PIT `news_evidence.jsonl`;
- every position decision is grounded in a thesis and read-only portfolio
  context;
- every backtest projection maps risk sizing into `target_weight` when a
  portfolio base is available, or uses explicit `risk_sizing.target_weight`
  when the Agent provides a bounded target exposure directly;
- every paper execution attempt uses the same request hash and approval hash
  that the gate evaluated;
- repeated execution requests are idempotent and append to the audit ledger
  rather than silently placing duplicate orders.

## Canonical Outcome

A successful Moirix thesis run writes:

```text
artifacts/moirix/news_evidence.jsonl
artifacts/moirix/adapter_call_status.json
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

- harden `moirix_query_news` and the shared adapter wrapper so timeouts and
  adapter failures leave `adapter_call_status.json` instead of hanging silently;
- harden `moirix_write_event_thesis` so a thesis is accepted only when
  `news_evidence.jsonl`, `request.json`, `status.json`, and
  `coverage_status.json` prove a nonblocked `query-news` result with matching
  `target`, `market`, `as_of`, referenced `event_id`s, and `visible_at <= as_of`;
- harden `moirix_write_position_decision` so a decision is accepted only when
  both `event_thesis_graph.json` and `event_decision_context.json` are `ok`,
  blocker-free, and identity-matched;
- harden `moirix_execute_trade_proposal` and Agent-facing paper mutating
  `trading_*` tools behind a v2 approval artifact, profile capability checks,
  paper kill switch, max-notional bound, gate-derived idempotency, and an
  append-only paper audit ledger;
- keep `ibkr-paper-trade` paper-only and block `client_id=0` write paths;
- make `moirix_export_decision_projection` produce a tested Vibe signal-engine
  consumer template that uses `target_weight` from risk sizing when portfolio
  base is available and clearly degrades to direction-only when it is not.

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
- `moirix_query_news` and adapter-backed tools write `adapter_call_status.json`
  and fail closed on timeout, invalid JSON, blocked source coverage, or adapter
  unavailability.
- `moirix_write_event_thesis` writes thesis/report/authority artifacts when
  matching nonblocked PIT evidence exists.
- `moirix_write_event_thesis` rejects empty evidence, non-`query-news`
  request artifacts, future `visible_at`, and thesis event IDs not present in
  PIT evidence.
- `moirix_write_event_thesis` blocks old numeric graph fields.
- `moirix_portfolio_context` writes blocked/unavailable context without fake
  positions when no read-only portfolio artifact exists.
- `moirix_write_position_decision` writes position decision, normalized trade
  proposal, risk sizing report, and portfolio adjustment plan artifacts.
- `moirix_write_position_decision` blocks when portfolio context is
  blocked/unavailable or identity-mismatched.
- `moirix_write_position_decision` keeps proposal authority research-only and
  broker-submit false by default.
- `moirix_export_decision_projection` writes research-only backtest projection
  artifacts from position decisions without broker authority.
- `moirix_export_decision_projection` writes a Vibe-compatible signal-engine
  template and manifest pointer so the projection has a tested backtest
  consumption path.
- `moirix_export_decision_projection` writes `target_weight`,
  `max_position_notional`, `max_loss_notional`, and `weight_basis`; when an
  explicit target weight or portfolio-derived target weight is available, the
  signal engine uses it rather than full notional direction.
- `moirix_execute_trade_proposal` blocks when approval authority, proposal hash,
  request hash, account, connector profile, expiry, max notional, kill switch,
  or execution mode is missing or unsafe.
- Agent-facing paper mutating trading tools require explicit approval when
  `dry_run=false`, derive idempotency from approval/request hash, and append to
  the paper audit ledger.
- Live execution remains blocked in this goal.
- Run API surfaces `event_thesis_graph`, `event_thesis_report_markdown`, and
  `event_decision_context`, plus position decision artifacts when present.
- Home only treats canonical thesis/context/position artifacts as Moirix Event
  Thesis or Position Decision runs.
- Run Detail displays Evidence, Event Thesis, Decision Context, Position
  Decision, and Authority.
- Tests cover backend tools, Run API preview, Home, Run Detail, skill/swarm
  packaging, and MCP/tool registry.
