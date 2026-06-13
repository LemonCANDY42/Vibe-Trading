# Review: Moirix Extension Complete

Date: 2026-06-12

> Status: historical review. The active Moirix implementation has moved from
> numeric event-impact graph / event_signal artifacts to the Agent-driven event
> thesis workflow documented in `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md`.

Scope:

- Vibe fork: `/Users/kennymccormick/github/Vibe-Trading-Kenny`
- Moirix adapter: `/Users/kennymccormick/github/Moirix`
- Vibe branch: `feat/moirix-event-graph-extension-v0`
- Moirix branch: `feat/vibe-event-graph-adapter-v0`

## Recommendation

Use/merge recommendation for the personal fork: proceed after committing the
Vibe and Moirix changes as coordinated commits.

Upstream recommendation: keep this as a personal fork extension for now. The
code shape is upstream-friendly because Moirix remains optional and isolated,
but an upstream PR should first replace local checkout/conda discovery with a
generic optional plugin/config surface.

## Blocking Findings

None.

## Non-Blocking Findings

- IBKR paper readiness is read-only and artifact-backed, but the real local
  Gateway smoke returned `ibkr_paper_market_data_blocked` for AAPL quote
  snapshot. IBKR printed error 10089, indicating extra API market-data
  subscription is required while delayed data may be available. This is
  correctly represented as blocked rather than ready.
- Frontend production build reports existing chunk-size warnings for large
  bundles. The Moirix tabs build and tests pass; code splitting can be handled
  separately.
- `agent/api_server.py` tests still show existing FastAPI `on_event`
  deprecation warnings. They are not introduced by the Moirix artifact preview
  behavior.

## Commands Run

Vibe validation:

```bash
git diff --check
node --check wiki/docs/content.js
uv run --extra dev python -m py_compile \
  agent/mcp_server.py \
  agent/api_server.py \
  agent/src/tools/ibkr_paper_readiness_tool.py \
  agent/src/tools/moirix_event_signal_backtest_tool.py
uv run --extra dev python -m pytest \
  agent/tests/test_moirix_adapter_tools.py \
  agent/tests/test_run_card.py \
  agent/tests/test_trading_connections.py \
  agent/tests/test_mcp_regression.py \
  agent/tests/test_mcp_server_smoke.py -q
cd frontend && npm run build
cd frontend && npm run test:run -- src/lib/__tests__/runReports.test.ts
```

Observed:

- diff/doc syntax: passed.
- py_compile: passed.
- targeted Vibe tests: 41 passed, 2 FastAPI deprecation warnings.
- frontend build: passed.
- frontend tests: 13 passed.

Moirix validation:

```bash
/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix \
  python -m pytest packages/moirix-vibe-adapter/tests -q
```

Observed:

- Moirix adapter tests: 11 passed.

Real local smokes:

```bash
VIBE_TRADING_ALLOWED_RUN_ROOTS=/Users/kennymccormick/github/Vibe-Trading-Kenny/agent/runs \
  uv run --extra dev --extra ibkr python -c "..."
```

Observed:

- IB Gateway paper endpoint auto-selected: `127.0.0.1:4002`.
- connectivity/account/positions/open orders/executions/history: `ok`.
- market-data quote snapshot: `blocked`.
- `ready_for_real_money_trading_authority=false`.

MCP catalog check:

```bash
uv run --extra dev python - <<'PY'
import asyncio
import mcp_server
async def main():
    tools = await mcp_server.mcp.list_tools()
    print(len(tools))
    print(",".join(t.name for t in tools))
asyncio.run(main())
PY
```

Observed:

- MCP catalog exposes 43 tools.
- Moirix wrappers and `ibkr_paper_readiness` are present.

Upstream sync check:

```bash
git fetch upstream
git rev-list --left-right --count HEAD...upstream/main
git merge-base HEAD upstream/main
git rev-parse upstream/main
```

Observed:

- `HEAD...upstream/main`: `2 0`.
- `merge-base` equals `upstream/main`; no upstream merge required.

## Files Reviewed

Vibe fork:

- `README.md`
- `agent/api_server.py`
- `agent/mcp_server.py`
- `agent/src/agent/context.py`
- `agent/src/tools/_moirix_adapter.py`
- `agent/src/tools/moirix_event_signal_tool.py`
- `agent/src/tools/moirix_event_signal_backtest_tool.py`
- `agent/src/tools/moirix_authority_guard_tool.py`
- `agent/src/tools/ibkr_paper_readiness_tool.py`
- `agent/src/skills/moirix-event-graph/SKILL.md`
- `agent/tests/test_moirix_adapter_tools.py`
- `agent/tests/test_run_card.py`
- `agent/tests/test_trading_connections.py`
- `agent/tests/test_mcp_regression.py`
- `agent/tests/test_mcp_server_smoke.py`
- `frontend/src/lib/api.ts`
- `frontend/src/pages/RunDetail.tsx`
- `wiki/docs/kenny/CURRENT_GOAL.md`
- `wiki/docs/kenny/MAINTENANCE_PARADIGM.md`
- `wiki/docs/kenny/MOIRIX_SELF_USE_SAMPLE_RUNS.md`
- `wiki/docs/kenny/UPSTREAM_SYNC_REVIEW.md`
- `wiki/docs/moirix/MOIRIX_EXTENSION_PLAN.md`

Moirix adapter:

- `docs/VIBE_EXTENSION_CONTRACT.md`
- `docs/VIBE_NEWS_EVENT_GRAPH_ADAPTER.md`
- `packages/moirix-vibe-adapter/src/moirix_vibe_adapter/schemas.py`
- `packages/moirix-vibe-adapter/src/moirix_vibe_adapter/news_query.py`
- `packages/moirix-vibe-adapter/src/moirix_vibe_adapter/event_graph.py`
- `packages/moirix-vibe-adapter/src/moirix_vibe_adapter/export_vibe.py`
- `packages/moirix-vibe-adapter/src/moirix_vibe_adapter/authority_guard.py`
- `packages/moirix-vibe-adapter/tests/test_cli_contract.py`
- `packages/moirix-vibe-adapter/tests/test_event_graph_fixture.py`
- `packages/moirix-vibe-adapter/tests/test_news_query_blocked.py`
- `packages/moirix-vibe-adapter/tests/test_authority_guard_fail_closed.py`

## PRD Completion Notes

- Moirix adapter contract is frozen around `export-vibe-artifacts` with
  `event_signal.csv` as the standard signal artifact.
- Vibe wraps Moirix as optional local tools and preserves
  `blocked` / `unavailable`.
- Run artifacts expose Moirix status, request, coverage, evidence, event graph,
  event signal, authority, and Run Card patch files.
- Run Detail renders Moirix Evidence, Graph, and Authority tabs when artifacts
  exist.
- Three local self-use sample runs are recorded in
  `wiki/docs/kenny/MOIRIX_SELF_USE_SAMPLE_RUNS.md`.
- IBKR paper readiness is read-only, writes `ibkr_paper_readiness.json`, and
  keeps all real-money authority fields false.
- Upstream sync check is documented in
  `wiki/docs/kenny/UPSTREAM_SYNC_REVIEW.md`.

## Remaining External Gates

- IBKR API market-data subscription is required before quote snapshot readiness
  can become `ok` for symbols like AAPL.
- Runtime sample artifacts under `agent/runs/` are intentionally local and
  git-ignored; repo durability comes from the docs and tests above.
