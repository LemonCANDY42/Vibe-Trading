---
name: moirix-event-graph
description: Use the optional Moirix local adapter for PIT news evidence, Agent-driven event thesis synthesis, portfolio-aware position decisions, trade proposals, and authority-boundary reporting.
category: strategy
---
# Moirix Event Thesis And Position Decision

This is a Kenny-fork-only skill. Do not present it as a general upstream
Vibe-Trading feature or include it in upstream PR work. It may use Kenny's local
Moirix adapter, fork-owned Moirix run artifacts, and fork-owned Moirix UI
surfaces.

Use this skill when the user asks how news, announcements, filings, macro
events, policy events, or supply-chain events may affect a target instrument,
sector, ETF, or related assets. Also use it when the user asks for a
news-aware, event-driven, portfolio-aware, or Moirix-backed event thesis. Also
use it when the user asks whether to add, trim, exit, hedge, buy, sell, short,
or cover based on Moirix evidence and current holdings.

The canonical workflow is thesis-first. Do not build numeric event-impact
graphs, edge weights, confidence scores, impact scores, or event_signal CSVs as
the primary output. Those were removed because they made a candidate weighted
graph look like the decision logic. Moirix provides PIT evidence; Vibe's Agent
produces the auditable thesis.

## Workflow

1. Call `moirix_status` first to check adapter availability, source-lake
   readiness, supported scopes, and fail-closed authority fields.
2. Call `moirix_query_news` with `target`, `market`, `as_of`, and
   `lookback_days` to request PIT-valid evidence from Moirix.
3. If current holdings, cash, open orders, or paper account state matter, call
   `moirix_portfolio_context` after a read-only portfolio snapshot or
   `ibkr_paper_readiness` artifact exists. Missing portfolio context must remain
   `blocked` or `unavailable`; do not invent positions.
4. Synthesize the event thesis as structured JSON with semantic relations:
   `supports`, `contradicts`, `supersedes`, `updates`, `duplicates`,
   `weakens`, `confirms`, or `causal_chain`.
5. Call `moirix_write_event_thesis` to persist:
   - `event_thesis_graph.json`;
   - `event_thesis_report.md`;
   - `authority_status.json`;
   - `vibe_run_card_patch.json`.
   This write must fail closed unless the same run has nonblocked
   `query-news` evidence with matching `target`, `market`, `as_of`, referenced
   event IDs, and `visible_at <= as_of`.
6. When the user asks for a position decision or new-target action proposal,
   synthesize `vibe.moirix_position_decision.v1` and call
   `moirix_write_position_decision` to persist:
   - `position_decision.json`;
   - `trade_proposal.json`;
   - `risk_sizing_report.json`;
   - `portfolio_adjustment_plan.md`.
7. If the user asks for historical evaluation or backtesting, call
   `moirix_export_decision_projection`. This writes research-only backtest
   projection artifacts and a Vibe signal-engine template; it is not Moirix
   evidence and not an order. When portfolio base and risk sizing exist, the
   projection must use `target_weight`; direction-only output is only a degraded
   fallback.
8. If the user provides an explicit paper execution approval artifact, call
   `moirix_execute_trade_proposal`. Without approval it must return blocked.
   The approval must use schema `vibe.paper_execution_approval.v2` and bind the
   request hash, connector, account, expiry, and max notional. Live execution is
   blocked in v1.
9. If checking a proposal, call `moirix_authority_guard`. Its outputs live under
   `artifacts/moirix/authority_checks/<proposal-id>/` so a blocked proposal does
   not overwrite the primary thesis artifacts.
10. State the authority boundary: event thesis and position decision artifacts
   are research proposals, not direct trading orders.

## Labels

- If Moirix returns `status: "ok"`, label the result according to its
  `evidence_coverage` and source-lake fields. Do not overclaim universal news
  coverage.
- If Moirix returns `status: "blocked"`, show the blockers and do not fabricate
  missing evidence.
- If Moirix returns `status: "unavailable"`, fall back only when useful to
  `web_search`, `read_url`, and the existing `event-driven` CSV flow. Label that
  fallback as ad-hoc web research, not PIT source-lake research.

## Thesis Schema Requirements

`event_thesis_graph.json` must use `schema_version:
vibe.moirix_event_thesis.v1` and include:

- evidence item truth state: `verified`, `likely`, `uncertain`, `disputed`, or
  `superseded`;
- source quality: `high`, `medium`, `low`, or `unknown`;
- target relevance: `direct`, `indirect`, `sector`, `macro`, or `none`;
- impact path: `revenue`, `margin`, `valuation`, `liquidity`, `sentiment`,
  `supply_chain`, `policy`, or `unknown`;
- current thesis stance, actionability, execution window, invalidation
  triggers, open questions, supporting events, and contradicting events;
- authority fields with `research_only=true`,
  `paper_trade_proposal_allowed=false`, `broker_submit_allowed=false`, and
  `ready_for_real_money_trading_authority=false`.

Do not use `strength`, `weight`, numeric `confidence`, or `impact_score` in the
canonical thesis graph.

## Position Decision Requirements

`position_decision.json` must use `schema_version:
vibe.moirix_position_decision.v1` and include:

- action: `buy`, `sell`, `short`, `cover`, `add`, `trim`, `exit`, `hold`,
  `watch`, `hedge`, or `blocked`;
- rationale tied to the thesis and portfolio context;
- execution window and invalidation triggers;
- risk sizing: explicit target weight or max position notional, max loss, and
  portfolio impact;
- proposed orders only as normalized research intent;
- authority fields with `research_only=true`,
  `paper_trade_proposal_allowed=false`, `broker_submit_allowed=false`, and
  `ready_for_real_money_trading_authority=false`.

`trade_proposal.json` is not an order. It can be executed only by
`moirix_execute_trade_proposal` after explicit paper execution approval and the
existing Vibe trading connector gates pass.

The approval artifact, not the proposal, grants paper execution authority. It
must reference the exact request hash and keep real-money authority false.

`decision_projection.csv` and `decision_projection.json` are the only canonical
backtest projection artifacts for this workflow. They are derived from
`position_decision.json` and remain research-only. Serious backtests should use
`target_weight`, `max_position_notional`, `max_loss_notional`, and
`weight_basis` from the projection rather than treating add/buy/short as
full-notional direction signals. For `trim`, `sell`, and `cover`, use explicit
target weight or current position value; do not infer a full flat target from a
partial order when that context is missing.

## Safety

- Do not turn event theses or position decisions into direct orders.
- Do not call broker, order, custody, or live-trading tools directly from thesis
  or decision synthesis.
- For execution, use only `moirix_execute_trade_proposal`; it must verify an
  explicit approval artifact and fail closed. Live execution is blocked in v1.
- Do not route news through market-data loaders.
- Do not claim historical or real-time news coverage unless Moirix returns
  coverage evidence for the requested window.
- Treat missing `adapter_call_status.json` on adapter-backed runs as an
  observability gap; successful daily-operation runs should preserve adapter
  timeout/status/blocker state.
- Do not write outside the current run artifacts. Primary Moirix tool outputs
  belong under `artifacts/moirix/`; proposal authority checks belong under
  `artifacts/moirix/authority_checks/`.
