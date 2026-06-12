---
name: moirix-event-graph
description: Use the optional Moirix local adapter for PIT news evidence, event-impact graph hypotheses, and authority-boundary reporting.
category: strategy
---
# Moirix Event Graph

Use this skill when the user asks how news, announcements, filings, macro
events, policy events, or supply-chain events may affect a target instrument,
sector, ETF, or related assets.

## Workflow

1. Call `moirix_status` first to check adapter availability, source-lake
   readiness, supported scopes, and fail-closed authority fields.
2. Call `moirix_query_news` with `target`, `market`, `as_of`, and
   `lookback_days` to request PIT-valid evidence from Moirix.
3. If evidence is available, call `moirix_build_event_graph` to produce
   `event_impact_graph.json` and related Moirix artifacts.
4. If event features are needed, call `moirix_export_event_signal` to expose
   `event_signal.csv` under `artifacts/moirix/`.
5. If the user asks for forward returns or event-study validation, call
   `moirix_event_signal_backtest` with an explicit daily close price CSV.
   Treat forward returns as outcome labels, not features visible at `known_at`.
6. Convert the graph output into hypotheses, impacted-instrument paths,
   coverage gaps, and possible event CSV or factor candidates for later Vibe
   backtesting.
7. State the authority boundary: graph scores are research hypotheses, not
   direct trading orders.

## Labels

- If Moirix returns `status: "ok"`, label the result according to its
  `evidence_coverage` and source-lake fields. Do not overclaim universal news
  coverage.
- If Moirix returns `status: "blocked"`, show the blockers and do not fabricate
  missing evidence.
- If Moirix returns `status: "unavailable"`, fall back only when useful to
  `web_search`, `read_url`, and the existing `event-driven` CSV flow. Label that
  fallback as ad-hoc web research, not PIT source-lake research.

## Safety

- Do not turn graph scores into direct orders.
- Do not call broker, order, custody, or live-trading tools from this workflow.
- Do not route news through market-data loaders; `moirix_event_signal_backtest`
  consumes `event_signal.csv` and explicit price CSV artifacts only.
- Do not claim historical or real-time news coverage unless Moirix returns
  coverage evidence for the requested window.
- Do not write outside the current run artifacts. Moirix tool outputs belong
  under `artifacts/moirix/`.
