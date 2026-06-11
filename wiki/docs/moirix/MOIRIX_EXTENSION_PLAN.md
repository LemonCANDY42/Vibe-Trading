# Moirix Extension Plan

This fork keeps Moirix integration as an optional local extension. The goal is
to use Moirix's PIT evidence, event-impact graph, and authority-boundary
contracts without making upstream Vibe-Trading depend on Moirix.

The product roadmap source is
`wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md`. The current bounded target
is tracked in `wiki/docs/kenny/CURRENT_GOAL.md`.

## Boundary

Vibe owns:

- agent tools, skills, swarm presets, and run artifacts;
- optional local subprocess invocation;
- fallback labeling when Moirix is unavailable.

Moirix owns:

- point-in-time source evidence and coverage claims;
- event-impact graph candidate semantics;
- authority guard fields and fail-closed trading boundaries;
- Run Card-compatible artifact patches.

The Vibe side must not write Moirix source-lake, graph-truth, portfolio, ledger,
broker, or audit state. It must not route news through `backtest/loaders/`.

## Local Discovery

The Vibe tools resolve the adapter in this order:

1. `MOIRIX_ADAPTER_CMD`, for example:

   ```bash
   export MOIRIX_ADAPTER_CMD="/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix python -m moirix_vibe_adapter"
   export MOIRIX_REPO_DIR="/Users/kennymccormick/github/Moirix"
   ```

2. `python -m moirix_vibe_adapter` when the module is importable in the current
   Python environment.
3. A sibling checkout named `Moirix` with a local conda environment named
   `moirix` or `MOIRIX_CONDA_ENV`.
4. Otherwise the tool returns `status: "unavailable"`.

No broker credential, OAuth, or live-trading configuration is read by this
extension.

## Runtime Sequence

```text
Vibe prompt or swarm worker
  -> moirix_status
  -> moirix_query_news(target, market, as_of, lookback_days)
  -> artifacts/moirix/*
  -> moirix_build_event_graph(target, as_of, input_path?)
  -> Vibe report labels ok / blocked / unavailable states explicitly
```

If `moirix_query_news` is blocked, Vibe may fall back to `web_search`,
`read_url`, and the existing `event-driven` CSV workflow, but that output must
be labeled as ad-hoc web research rather than PIT source-lake evidence.

## Artifacts

Moirix artifacts live under the current Vibe run directory:

```text
artifacts/moirix/
  news_evidence.jsonl
  event_impact_graph.json
  moirix_summary.md
  moirix_authority_status.json
  vibe_run_card_patch.json
```

Blocked news queries must not create fake `news_evidence.jsonl` rows.

## Upstream-Friendly Shape

This fork intentionally keeps the integration isolated:

- private helper: `agent/src/tools/_moirix_adapter.py`;
- public tools: `moirix_status`, `moirix_query_news`,
  `moirix_build_event_graph`;
- bundled skill: `moirix-event-graph`;
- bundled swarm preset: `moirix_event_impact_desk`.

That keeps future upstream syncs small. If this becomes suitable for the
original Vibe-Trading project, the main remaining work is to replace local
repo/conda discovery with a generic optional plugin configuration.

## PRD Status Map

Implemented in the current Vibe-side V0 branch:

- optional local Moirix adapter subprocess wrapper;
- adapter command discovery through `MOIRIX_ADAPTER_CMD`, current Python
  environment, or sibling local Moirix checkout with conda;
- `moirix_status`;
- `moirix_query_news`;
- `moirix_build_event_graph`;
- `moirix-event-graph` skill;
- `moirix_event_impact_desk` swarm preset;
- run artifact writes under `artifacts/moirix/`;
- fail-closed handling for missing adapter, blocked adapter, invalid JSON,
  unknown status, authority contract violations, and artifact paths outside the
  current run artifact directory.

Deferred until the Moirix adapter exposes stable commands:

- `moirix_export_event_signal` wrapping `export-event-signal`;
- `moirix_authority_guard` wrapping `authority-check`;
- `event_signal.csv` handoff into Vibe backtest workflows.

Deferred to later Vibe-side work:

- Run Detail Moirix Evidence / Event Graph / Authority panels;
- IBKR paper read-only readiness;
- paper proposal guard integration;
- any broker-submit or real-money authority path.

## Acceptance Criteria

- Moirix tools are discoverable in the normal Vibe tool registry.
- Missing Moirix adapter returns `status: "unavailable"`, not a crash.
- Moirix blocked states are preserved.
- Tool artifacts are written only under the current run's `artifacts/moirix/`.
- Event graph input paths cannot escape the current run or allowed import roots.
- No broker, order, or live-trading tool path is introduced.
- All live/real-money authority booleans from Moirix remain false.
