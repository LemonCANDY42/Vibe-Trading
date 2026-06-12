# Current Goal: Complete The Vibe-Moirix Personal Workbench PRD

## Source Of Truth

- PRD: `wiki/docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md`
- Maintenance paradigm: `wiki/docs/kenny/MAINTENANCE_PARADIGM.md`
- Upstream sync policy: `wiki/docs/kenny/UPSTREAM_SYNC_POLICY.md`
- Vibe-side Moirix plan: `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md`
- Moirix-side contract docs:
  - `/Users/kennymccormick/github/Moirix/docs/VIBE_EXTENSION_CONTRACT.md`
  - `/Users/kennymccormick/github/Moirix/docs/VIBE_NEWS_EVENT_GRAPH_ADAPTER.md`

The repository root `docs/` directory is ignored by this fork. Fork-owned
Kenny docs therefore live under `wiki/docs/kenny/`.

## Objective

Complete the personal Vibe-Moirix PRD through staged, reviewable work that keeps
Vibe-Trading as the primary workbench, keeps Moirix optional and fail-closed,
uses the SSD-backed Moirix/news/bar data where available for testing and
backtesting, and uses the logged-in IBKR paper gateway only for read-only
readiness checks.

## Current Next Goal

G11 is the active next implementation target:

```text
Make a normal Vibe Agent run able to produce a news-aware Moirix event-signal
research run and a visible token-usage chart in Run Detail.
```

This is a new goal on top of the completed PRD foundation. G1-G10 remain the
historical baseline and acceptance evidence for the fork.

## Baseline Already Completed

The fork already has a pushed V0 foundation on
`feat/moirix-event-graph-extension-v0`:

- PRD absorbed under `wiki/docs/kenny/`.
- Maintenance paradigm codified in `wiki/docs/kenny/MAINTENANCE_PARADIGM.md`.
- Optional Vibe tools:
  - `moirix_status`
  - `moirix_query_news`
  - `moirix_build_event_graph`
- Moirix skill and swarm:
  - `moirix-event-graph`
  - `moirix_event_impact_desk`
- Tests previously passed:
  - `agent/tests/test_moirix_adapter_tools.py`: 9 passed.
  - skill/swarm/package tests: 29 passed.
- Real local adapter smoke previously observed:

  ```text
  status ok local_moirix_conda
  query initially blocked on sampled source-lane window coverage
  graph ok /private/tmp/vibe-moirix-review-smoke-run/artifacts/moirix/event_impact_graph.json
  ```

  That sampled-window blocker was fixed in the sibling Moirix branch on
  2026-06-12: `query-news` now lets the read-only news-browser query surface
  decide PIT/time/coverage blockers instead of treating sampled catalog lanes
  as full coverage proof. The fix was verified with a 2018-12-14 PIT query
  returning 2 rows.

## Active Implementation Stages

### G1: Contract Freeze

Status: complete on 2026-06-12.

Outcome:

- PRD, Vibe fork docs, and Moirix adapter docs agree on command names, artifact
  names, schema ids, authority fields, and failure states.
- `export-event-signal` vs `export-vibe-artifacts` is resolved explicitly.

Adopted decision:

- Moirix-side canonical command: `export-vibe-artifacts`.
- Standard artifact: `event_signal.csv`.
- Vibe-side workflow/tool name may be `moirix_export_event_signal`, but it wraps
  `export-vibe-artifacts` unless a future Moirix adapter release adds a
  compatible `export-event-signal` alias.

Verification:

```bash
git diff --check
node --check wiki/docs/content.js
```

Stop if:

- Moirix-side docs and implementation disagree in a way that changes the Vibe
  wrapper contract.

Observed evidence:

- Vibe docs and Moirix docs now agree that `export-vibe-artifacts` is the
  canonical export command.
- Moirix adapter allowlist includes `event_signal.csv`.
- Moirix adapter tests passed: 11 passed.
- Real adapter `status` returned `status: "ok"`, `source_lake.status:
  "available"`, and `supported_commands`:
  - `status`
  - `query-news`
  - `build-event-graph`
  - `export-vibe-artifacts`
  - `authority-check`

### G2: Moirix Adapter Completion

Status: complete on 2026-06-12 for the local adapter contract needed by Vibe
G3. Full run artifact population remains in G4.

Outcome:

- `/Users/kennymccormick/github/Moirix` exposes stable local adapter commands:
  - `status`
  - `query-news`
  - `build-event-graph`
  - `export-vibe-artifacts`
  - `authority-check`
- Adapter stdout remains a single JSON object.
- Blocked/unavailable states are explicit and do not generate fake evidence.

Verification:

```bash
/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix \
  python -m moirix_vibe_adapter status

/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix \
  python -m pytest packages/moirix-vibe-adapter/tests -q
```

Stop if:

- the SSD-backed source-lake paths cannot be found or opened read-only;
- adapter completion would require mutating Moirix source-lake, graph truth,
  ledger, portfolio, broker, or audit state.

Observed evidence:

- `status` returned JSON with `status: "ok"`, source-lake available, and
  DuckDB path `/Volumes/FileBackup/Moirix/data-lake/catalog/moirix.duckdb`.
- `build-event-graph` generated:
  - `event_impact_graph.json`
  - `news_evidence.jsonl`
  - `event_signal.csv`
  - `moirix_authority_status.json`
  - `moirix_summary.md`
  - `vibe_run_card_patch.json`
- `event_signal.csv` fixture rows included NVDA, SMH, and AMD with
  `pit_valid=true`.
- `authority-check` blocked the broker-write fixture proposal and kept
  `ready_for_real_money_trading_authority=false`.
- `export-vibe-artifacts` copied `event_signal.csv` from the graph run into the
  Vibe export output.
- Moirix adapter tests passed: 11 passed.

### G3: Vibe Tool Expansion

Status: complete on 2026-06-12.

Outcome:

- Vibe discovers Moirix tools:
  - `moirix_status`
  - `moirix_query_news`
  - `moirix_build_event_graph`
  - `moirix_export_event_signal`
  - `moirix_event_signal_backtest`
  - `moirix_authority_guard`
- Tool wrappers preserve `ok` / `blocked` / `unavailable`.
- News, graph, event-signal, and export outputs stay under the current run's
  primary `artifacts/moirix/` directory.
- `moirix_authority_guard` writes per-proposal outputs under
  `artifacts/moirix/authority_checks/<proposal-id>/` so blocked proposal checks
  cannot overwrite the run's primary `status.json`, `coverage_status.json`, or
  graph/signal artifacts.
- No broker/order/live-trading parameters are exposed.

Verification:

```bash
uv run --extra dev python -m pytest agent/tests/test_moirix_adapter_tools.py -q
uv run --extra dev python -m pytest \
  agent/tests/test_swarm_presets_packaging.py \
  agent/tests/test_swarm_preset_inspect.py \
  agent/tests/test_skills.py -q
```

Stop if:

- Vibe-side tool implementation would need to route news through
  `backtest/loaders/`;
- any authority guard payload returns real-money or broker-submit authority.

Observed evidence:

- Vibe discovers the Moirix tool set.
- `agent/tests/test_moirix_adapter_tools.py`: 12 passed.
- skill/swarm/package tests: 29 passed.
- Real Vibe wrapper smoke:
  - `moirix_build_event_graph`: `ok`, wrote `event_signal.csv`;
  - `moirix_export_event_signal`: `ok`, copied `event_signal.csv`;
  - `moirix_authority_guard`: `blocked` for broker-write proposal with
    blockers including `broker_write_requested` and `submit_order_requested`,
    with outputs isolated under `artifacts/moirix/authority_checks/`.

### G4: Run Artifact Integration

Status: complete on 2026-06-12 for Moirix tool/run artifact manifest
integration. Web Run Detail rendering remains G6.

Outcome:

- A Moirix-enabled Vibe run can attach the full artifact set:
  - `status.json`
  - `request.json`
  - `coverage_status.json`
  - `news_evidence.jsonl`
  - `event_impact_graph.json`
  - `event_signal.csv`
  - `moirix_summary.md`
  - `authority_status.json`
  - `vibe_run_card_patch.json`

Verification:

- mock adapter success produces the full artifact set;
- blocked query does not create fake `news_evidence.jsonl`;
- Vibe tool payloads expose the Moirix artifact manifest returned by the local
  adapter.

Stop if:

- artifact paths escape the run artifact root;
- blocked coverage is hidden behind an empty or success-looking artifact.

Observed evidence:

- Moirix adapter writes standard `status.json`, `request.json`,
  `coverage_status.json`, `authority_status.json`, and
  `vibe_run_card_patch.json` for adapter commands that write artifacts.
- Blocked `query-news` still does not create fake `news_evidence.jsonl`.
- Vibe mock adapter tests verify the standard artifact keys in wrapper payloads.
- Real Vibe wrapper smoke with the local Moirix checkout returned:
  - `moirix_build_event_graph`: `ok`;
  - `moirix_export_event_signal`: `ok`;
  - `moirix_authority_guard`: `blocked` for broker-write proposal;
  - primary graph/signal files present under `artifacts/moirix/`;
  - authority-check files present under
    `artifacts/moirix/authority_checks/<proposal-id>/`.

### G5: Event Signal To Backtest

Status: complete on 2026-06-12 for explicit-price event-signal forward-return
study. Broader strategy-engine integration remains out of scope for this
stage.

Outcome:

- `event_signal.csv` can be consumed by a Vibe event-study workflow without
  adding news to market-data loaders.
- At least one NVDA / SMH / AMD fixture or SSD-backed example produces a
  forward-return report using event features.

Verification:

- run validates 1 / 3 / 5 / 10 / 20 trading-day forward-return or an equivalent
  existing Vibe backtest output;
- output labels PIT source-lake evidence vs ad-hoc evidence precisely.

Stop if:

- a feature uses future-visible data;
- daily-bar data is presented as quote/tick/order-book evidence.

Observed evidence:

- Added `moirix_event_signal_backtest`, which consumes
  `artifacts/moirix/event_signal.csv` plus an explicit daily close price CSV.
- The tool writes:
  - `event_signal_forward_returns.csv`
  - `event_signal_backtest_summary.json`
- Targeted tests cover success and missing-price blocked behavior.
- Real smoke on the local Moirix fixture-generated `event_signal.csv` produced
  1 / 3 / 5 / 10 / 20 horizon forward-return rows and kept all trading
  authority fields false.

### G6: Web Run Detail Moirix Tabs

Status: complete on 2026-06-12 for minimal JSON/Markdown/table rendering.

Outcome:

- Run Detail shows minimal Moirix tabs when Moirix artifacts exist:
  - Moirix Evidence
  - Moirix Event Graph
  - Moirix Authority
- First version may render JSON/Markdown; complex graph visualization is not
  required.

Verification:

```bash
cd frontend && npm run build
npm run test:run -- src/lib/__tests__/runReports.test.ts
```

Acceptance:

- run without Moirix artifacts is unchanged;
- run with Moirix artifacts shows the three tabs.

Observed evidence:

- `/runs/{id}` now recursively lists nested artifacts such as
  `moirix/status.json` and exposes `moirix_artifacts` previews for selected
  JSON, Markdown, JSONL, and CSV files.
- Per-proposal authority checks are previewed from
  `artifacts/moirix/authority_checks/<proposal-id>/` so blocked checks remain
  visible without overwriting primary graph/signal status files.
- Run Detail conditionally shows:
  - `Moirix Evidence`
  - `Moirix Graph`
  - `Moirix Authority`
- Browser smoke on `http://127.0.0.1:5899/runs/moirix_g6_smoke` confirmed:
  - Evidence tab renders Markdown summary, status, coverage, and news preview;
  - Graph tab renders event graph and event-signal previews;
  - Authority tab renders authority status and Run Card patch.

### G7: Self-Use Sample Runs

Status: complete on 2026-06-12.

Outcome:

- Complete three real self-use examples:
  - US semiconductor news graph;
  - HK tech news graph;
  - A-share policy/announcement event graph.
- At least one example exports `event_signal.csv` and completes a backtest.

Verification:

- each run has evidence/coverage/authority artifacts;
- source gaps are represented as blocked/partial, not hidden as success;
- final summaries separate evidence, inference, and unsupported gaps.

Stop if:

- the SSD data mount cannot be found or does not contain the claimed source
  coverage;
- a run cannot prove PIT visibility for the tested window.

Observed evidence:

- Durable record: `wiki/docs/kenny/MOIRIX_SELF_USE_SAMPLE_RUNS.md`.
- Runtime artifacts were generated under git-ignored local Vibe run dirs:
  - `agent/runs/moirix_sample_us_semiconductor`;
  - `agent/runs/moirix_sample_hk_tech`;
  - `agent/runs/moirix_sample_cn_policy`.
- US semiconductor sample:
  - target `英伟达`, market `US`, graph target `NVDA`;
  - 2 PIT source-lake evidence rows;
  - 2 `event_signal.csv` rows;
  - SSD daily bars read from
    `/Volumes/FileBackup/Moirix/data-lake/catalog/moirix.duckdb`;
  - `moirix_event_signal_backtest` completed 1 / 3 / 5 / 10 / 20 trading-row
    forward-return study with 10 output rows.
- HK tech sample:
  - target `腾讯`, market `HK`, graph target `0700.HK`;
  - 5 PIT source-lake evidence rows;
  - 5 `event_signal.csv` rows.
- CN policy sample:
  - target `监管`, market `CN`, graph target `CN_POLICY`;
  - 10 PIT source-lake evidence rows;
  - 10 `event_signal.csv` rows.
- All sample authority artifacts kept real-money and broker-submit authority
  false.

### G8: IBKR Paper Read-Only Readiness

Status: complete on 2026-06-12 with one external market-data subscription
blocker recorded in the readiness artifact.

Outcome:

- With the logged-in IB Gateway paper account, Vibe can perform only read-only
  readiness checks:
  - connectivity;
  - account summary;
  - positions;
  - open orders inspection;
  - executions/history inspection;
  - market data permission;
  - historical data permission.
- It writes `ibkr_paper_readiness.json`.
- It always reports `ready_for_real_money_trading_authority=false`.

Hard constraints:

- no `placeOrder`;
- no `cancelOrder`;
- no `reqGlobalCancel`;
- no order transmit;
- no simulated or live submit;
- no broker-write helper exposed to Moirix flows;
- avoid client-id behavior that binds or mutates manually entered orders unless
  a later explicitly approved paper-order PRD allows it.

Verification:

- readiness succeeds or returns blocked/unavailable with explicit blockers;
- code review confirms no write/order API path;
- IBKR paper checks use policy-compliant read-only inspection only.

Stop if:

- the only available API route would require order placement, cancellation,
  modification, or live/paper submit;
- IBKR API policy or gateway state is unclear.

Observed evidence:

- Added `ibkr_paper_readiness`, writing:
  `artifacts/ibkr/ibkr_paper_readiness.json`.
- The tool rejects `client_id=0` to avoid API behavior that can bind manually
  entered orders.
- The tool auto-selects IB Gateway paper port `4002` when the default TWS paper
  port `7497` is closed and `4002` is open.
- Real local smoke against the logged-in IB Gateway paper session:
  - endpoint: `127.0.0.1:4002`;
  - connectivity: `ok`;
  - account summary: `ok`;
  - positions: `ok`;
  - open orders / executions: `ok`;
  - historical data: `ok`;
  - market-data quote snapshot: `blocked`;
  - blocker: `ibkr_paper_market_data_blocked`.
- IBKR printed error 10089 for AAPL market data, indicating API market data
  needs an extra subscription while delayed market data may be available.
  Vibe does not treat that as full quote readiness because bid/ask/last/close
  were not finite in the snapshot.
- `ready_for_real_money_trading_authority=false` in all readiness authority and
  claim-gate fields.

### G9: Upstream Sync Hardening

Status: complete on 2026-06-12.

Outcome:

- The Kenny integration branch can absorb current `upstream/main` without
  broad Vibe core rewrites.

Verification:

```bash
git fetch upstream
git merge upstream/main
git diff --check
uv run --extra dev python -m pytest agent/tests/test_moirix_adapter_tools.py -q
```

Acceptance:

- conflicts, if any, are limited to docs/registry/routing/count surfaces;
- sync review doc records commands and results.

Observed evidence:

- Sync review: `wiki/docs/kenny/UPSTREAM_SYNC_REVIEW.md`.
- `git fetch upstream` succeeded.
- `git rev-list --left-right --count HEAD...upstream/main` returned `2 0`.
- `merge-base` equals `upstream/main`
  (`b6817be3b2929c72f6a389873d97130e8422d1c2`), so no upstream merge was
  required at the time of review.

### G10: Final Independent Review

Status: complete on 2026-06-12.

Outcome:

- The PRD is considered fully implemented only after an independent review finds
  no blocking findings.

Verification artifact:

```text
wiki/docs/kenny/REVIEW_MOIRIX_EXTENSION_COMPLETE.md
```

The review must include:

- commands run;
- blocking findings;
- non-blocking findings;
- exact files reviewed;
- merge/use recommendation;
- remaining external gates, if any.

Observed evidence:

- Review artifact: `wiki/docs/kenny/REVIEW_MOIRIX_EXTENSION_COMPLETE.md`.
- Blocking findings: none.
- Non-blocking / external gates:
  - IBKR quote snapshot remains blocked until API market-data subscription is
    available;
  - frontend chunk-size warning remains outside this PRD;
- FastAPI `on_event` deprecation warnings remain outside this PRD.

### G11: Agent News-Driven Backtest And Usage Charts

Status: complete on 2026-06-12.

Outcome:

- A normal Vibe Agent prompt can run the Moirix news workflow without the user
  manually invoking each tool:
  - `moirix_status`
  - `moirix_query_news`
  - `moirix_build_event_graph`
  - `moirix_export_event_signal`
  - `moirix_event_signal_backtest`
- The resulting run uses Moirix PIT source-lake evidence when available and
  labels `blocked` / `unavailable` states directly when evidence is not
  available.
- The run produces auditable Moirix artifacts under `artifacts/moirix/`:
  - `status.json`
  - `request.json`
  - `coverage_status.json`
  - `news_evidence.jsonl`
  - `event_impact_graph.json`
  - `event_signal.csv`
  - `event_signal_forward_returns.csv`
  - `event_signal_backtest_summary.json`
  - authority artifacts with all live/real-money fields false.
- AgentLoop provider usage is persisted to `artifacts/llm_usage.json` in the
  Kenny fork even if the upstream PR is not yet merged.
- Run Detail shows both:
  - the existing Moirix Evidence / Graph / Authority views;
  - an Agent Usage chart that visualizes per-iteration input, output, cache,
    and total token usage from `llm_usage.iterations`.

Scope:

- Vibe-side routing, skills, prompt guidance, tool contracts, API payloads, run
  artifacts, and frontend Run Detail rendering.
- One local SSD-backed smoke run using the existing Moirix checkout and source
  lake.
- Optional local MiniMax-M3 usage for the Agent smoke, using the existing
  provider configuration.

Out of scope:

- Changing Moirix source-lake, graph-truth, portfolio, ledger, broker, or audit
  state.
- Routing news through `backtest/loaders`.
- Adding broker submit, paper submit, live trading, or real-money authority.
- Claiming PIT evidence when Moirix returns `blocked` or `unavailable`.
- Pricing/currency cost calculation beyond token usage visualization.

Implementation notes:

- MiniMax-M3 standard-mode local Agent runs use the official MiniMax
  Anthropic-compatible Messages endpoint:
  `https://api.minimaxi.com/anthropic`.
- Because Vibe's previous MiniMax path used `ChatOpenAI`, the `/anthropic`
  endpoint required a small local Messages adapter instead of reusing the
  OpenAI-compatible `/chat/completions` client.
- MiniMax provider usage includes `cache_read_input_tokens`; Vibe persists it
  separately in `artifacts/llm_usage.json` and renders it as a cache segment in
  Run Detail.

Verification:

```bash
git diff --check

uv run --extra dev python -m pytest agent/tests/test_moirix_adapter_tools.py -q

uv run --extra dev python -m pytest \
  agent/tests/test_agent_loop_terminal_state.py \
  agent/tests/test_run_card.py -q

cd frontend && npm run build
cd frontend && npm run test:run -- src/lib/__tests__/runReports.test.ts
```

Smoke acceptance:

- one Agent-triggered run, not a direct manual backtest, creates a run directory
  with:
  - `artifacts/moirix/news_evidence.jsonl` or explicit blocked/unavailable
    coverage artifacts;
  - `artifacts/moirix/event_impact_graph.json` when evidence is available;
  - `artifacts/moirix/event_signal.csv` when evidence is available;
  - `artifacts/moirix/event_signal_forward_returns.csv` or an explicit blocked
    forward-return reason;
  - `artifacts/llm_usage.json`;
  - no broker/order/live-trading artifact.
- Run Detail for that run displays Moirix Evidence / Graph / Authority tabs and
  an Agent Usage token chart.

Observed completion evidence:

- Agent-triggered smoke run:
  `agent/runs/20260612_165913_06_2efc6e`.
- Tool sequence in `trace.jsonl`:
  - `moirix_status`
  - `moirix_query_news`
  - `moirix_build_event_graph`
  - `moirix_export_event_signal`
  - `moirix_event_signal_backtest`
- Artifact counts:
  - `news_evidence.jsonl`: 27 rows
  - `event_signal.csv`: 27 signal rows plus header
  - `event_signal_forward_returns.csv`: 135 forward-return rows plus header
- `event_signal_backtest_summary.json`:
  - `status=ok`
  - `signal_count=27`
  - `forward_return_row_count=135`
  - horizons `[1, 3, 5, 10, 20]`
  - `evidence_tiers.pit_source_lake=27`
  - `missing_price_symbols=[]`
  - `blockers=[]`
- `authority_status.json` keeps:
  - `live_broker_execution_enabled=false`
  - `real_order_authority=false`
  - `broker_submit_supported=false`
  - `ready_for_real_money_trading_authority=false`
- `artifacts/llm_usage.json`:
  - `provider=minimax`
  - `model=MiniMax-M3`
  - `calls=6`
  - `input_tokens=40251`
  - `output_tokens=1689`
  - `cache_read_input_tokens=117504`
  - `total_tokens=159444`
- API verification against the current working tree returned both
  `llm_usage` and `moirix_artifacts` for the run.
- Browser verification at
  `http://127.0.0.1:5901/runs/20260612_165913_06_2efc6e` showed:
  - Agent Usage chart with Input / Output / Cache series;
  - Moirix Evidence tab content;
  - Moirix Graph tab content with candidate graph state;
  - Moirix Authority tab with broker and real-money authority fields false.

Caveat from the smoke:

- The NVDA smoke exercised the full PIT workflow, but the returned GDELT rows
  were low-confidence candidate matches around `nvdaily.com` rather than
  validated NVIDIA-specific news. This is an evidence-quality result to surface,
  not a Vibe integration failure.

Stop if:

- the SSD-backed Moirix source lake or local adapter cannot be opened read-only;
- Moirix returns blocked/unavailable and no fixture or previously generated
  evidence can honestly exercise the success path;
- implementation would require mutating Moirix source-lake, graph truth,
  broker state, or Vibe market-data loaders;
- usage metadata is unavailable from the provider and the implementation would
  need to persist estimated tokens as if they were provider-reported usage.

## Overall Completion Criteria

Status: complete on 2026-06-12. The PRD is complete because all are true:

- G1 through G10 are complete or explicitly documented as externally gated.
- Vibe original CLI/Web/MCP research workflows still work.
- Moirix unavailable and blocked states remain visible and fail-closed.
- `event_signal.csv` is generated and consumed by at least one backtest.
- Run Detail can display Moirix evidence, graph, and authority artifacts.
- Three self-use sample runs are recorded with artifacts and coverage status.
- IBKR paper readiness is read-only and writes `ibkr_paper_readiness.json`.
- `ready_for_real_money_trading_authority=false` everywhere.
- No broker submit/order path is introduced by Moirix or event-graph flows.
- Upstream sync has been tested and reviewed.
- `REVIEW_MOIRIX_EXTENSION_COMPLETE.md` has no blocking findings.

## Global Stop Conditions

Stop and ask before continuing if:

- implementation would require real-money authority, broker submit, or order
  modification;
- the logged-in IBKR paper gateway exposes only write-capable paths for the
  requested check;
- adapter contracts drift across PRD, Vibe docs, and Moirix docs;
- SSD data paths cannot be identified safely;
- PIT evidence coverage cannot be proven for a requested backtest window;
- upstream changes require broad Vibe core rewrites rather than isolated
  extension work.
