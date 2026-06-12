# Moirix Extension Plan

This fork keeps Moirix integration as an optional local extension. The goal is
to use Moirix's PIT evidence, event-impact graph, and authority-boundary
contracts without making upstream Vibe-Trading depend on Moirix.

The product roadmap source is
`wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md`. The current bounded target
is tracked in `wiki/docs/kenny/CURRENT_GOAL.md`.

## G1 Contract Freeze

The adopted adapter command contract is:

```text
status
query-news
build-event-graph
export-vibe-artifacts
authority-check
```

`export-vibe-artifacts` is the canonical Moirix-side export command for Vibe.
It owns the Vibe artifact bundle, including `event_signal.csv` when the event
signal artifact exists. The Vibe-side tool may still be named
`moirix_export_event_signal` because that is the user-facing workflow action,
but it must call `export-vibe-artifacts` unless a future Moirix adapter version
adds an explicit compatible `export-event-signal` alias.

This resolves the PRD wording that mentioned `export-event-signal` against the
current Moirix implementation and docs, which expose `export-vibe-artifacts`.

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

## Agent News-Driven Backtest Target

The next active Kenny-fork goal is to make the above sequence executable from a
normal Agent prompt rather than only from manual tool calls. The expected
Agent-run sequence is:

```text
Agent prompt
  -> load moirix-event-graph skill when the request asks for news/event impact
  -> moirix_status
  -> moirix_query_news(target, market, as_of, lookback_days)
  -> moirix_build_event_graph(target, as_of)
  -> moirix_export_event_signal
  -> moirix_event_signal_backtest(price_csv_path=explicit_daily_close_csv)
  -> summarize evidence tier, graph hypothesis, event signal, forward returns,
     blocked/unavailable states, and authority status
```

This target must keep the same boundary rules:

- `event_signal.csv` may feed an event-study or strategy signal path, but news
  must not be routed through `backtest/loaders`;
- Moirix `blocked` and `unavailable` responses are valid user-visible outputs,
  not failures to hide;
- all live-trading, broker-submit, and real-money authority fields stay false;
- the run should also persist AgentLoop usage under `artifacts/llm_usage.json`
  and expose it in Run Detail as a per-iteration token-usage chart. Provider
  cache tokens, when reported, must be persisted separately and rendered as
  cache usage rather than hidden inside input/output bars.

## Artifacts

Moirix artifacts live under the current Vibe run directory:

```text
artifacts/moirix/
  status.json
  request.json
  coverage_status.json
  news_evidence.jsonl
  event_impact_graph.json
  event_signal.csv
  moirix_summary.md
  authority_status.json
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
- `moirix_export_event_signal`;
- `moirix_event_signal_backtest`;
- `moirix_authority_guard`;
- `moirix-event-graph` skill;
- `moirix_event_impact_desk` swarm preset;
- run artifact writes under `artifacts/moirix/`;
- standard Moirix artifact manifest under `artifacts/moirix/`, including
  `status.json`, `request.json`, `coverage_status.json`,
  `authority_status.json`, `moirix_authority_status.json`, and
  `vibe_run_card_patch.json`;
- explicit-price event-signal forward-return study through
  `moirix_event_signal_backtest`, writing `event_signal_forward_returns.csv`
  and `event_signal_backtest_summary.json`;
- `/runs/{id}` Moirix artifact previews and Run Detail tabs for Evidence,
  Graph, and Authority;
- `artifacts/llm_usage.json` for normal AgentLoop runs, including MiniMax-M3
  cache usage when provider-reported;
- Run Detail Agent Usage chart with input, output, cache, total, and call count;
- MiniMax-M3 standard mode through the Anthropic-compatible Messages endpoint
  `https://api.minimaxi.com/anthropic`;
- three local self-use sample runs documented in
  `wiki/docs/kenny/MOIRIX_SELF_USE_SAMPLE_RUNS.md`:
  - `moirix_sample_us_semiconductor`;
  - `moirix_sample_hk_tech`;
  - `moirix_sample_cn_policy`;
- IBKR paper read-only readiness through `ibkr_paper_readiness`, with local
  artifact `artifacts/ibkr/ibkr_paper_readiness.json` and no order/cancel path;
- fail-closed handling for missing adapter, blocked adapter, invalid JSON,
  unknown status, authority contract violations, and artifact paths outside the
  current run artifact directory.

Implemented in the local Moirix adapter for G2:

- `status`;
- `query-news`;
- `build-event-graph`;
- `export-vibe-artifacts`;
- `authority-check`;
- `build-event-graph` writes `event_signal.csv` from visible evidence rows;
- `export-vibe-artifacts` copies `event_signal.csv` when present;
- adapter commands that write artifacts also write standard status, request,
  coverage, authority, summary, and Run Card patch files;
- broker-write proposals are blocked by `authority-check`.

Deferred Vibe-side work:

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
