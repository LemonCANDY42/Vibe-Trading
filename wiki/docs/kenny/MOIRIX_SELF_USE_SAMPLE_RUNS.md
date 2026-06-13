# Moirix Self-Use Sample Runs

Date: 2026-06-13

This document is intentionally reset for the Agent-driven Moirix event thesis
workflow. Older local runs that produced `event_impact_graph.json`,
`event_signal.csv`, or forward-return studies were removed from the active
workflow because they implied numeric event weights were the decision logic.

Current canonical sample runs must prove this chain instead:

```text
moirix_status
  -> moirix_query_news
  -> moirix_portfolio_context
  -> moirix_write_event_thesis
  -> moirix_authority_guard when a proposal needs review
```

## Required Artifacts

Each accepted sample run should include:

- `artifacts/moirix/news_evidence.jsonl`
- `artifacts/moirix/event_thesis_graph.json`
- `artifacts/moirix/event_thesis_report.md`
- `artifacts/moirix/event_decision_context.json`
- `artifacts/moirix/authority_status.json`
- `artifacts/moirix/vibe_run_card_patch.json`

## Boundaries

- Moirix provides PIT evidence and source-lake coverage state.
- Vibe Agent synthesizes semantic event relations, portfolio context, bull/bear
  arguments, risk review, and the final thesis.
- Missing evidence or portfolio context remains `blocked` or `unavailable`.
- No run may fabricate holdings, evidence, or coverage.
- No run may submit, cancel, or modify broker orders.
- `broker_submit_allowed` and
  `ready_for_real_money_trading_authority` must stay `false`.

## Samples To Re-Run

The following samples should be re-run with the new thesis workflow before this
document is treated as complete:

| Sample | Target | Market | Status | Required outcome |
| --- | --- | --- | --- | --- |
| US semiconductor | NVDA or SMH | US | pending | thesis graph + report + decision context |
| HK tech | 0700.HK or sector basket | HK | pending | thesis graph + report + decision context |
| CN policy / A-share impact | policy topic or target basket | CN | pending | thesis graph + report + decision context |

Historical event-signal metrics are no longer acceptance evidence for this
workflow.
