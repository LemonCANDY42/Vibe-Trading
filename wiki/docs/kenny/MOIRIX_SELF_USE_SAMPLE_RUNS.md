# Moirix Self-Use Sample Runs

Date: 2026-06-12

These runs are local Vibe run artifacts generated for the personal
Vibe-Moirix workbench PRD. The runtime artifacts live under `agent/runs/`, which
is intentionally git-ignored. This document is the durable repo record of what
was run and what acceptance criteria were observed.

## Shared Boundaries

- Moirix source-lake was read through the local adapter only.
- No Moirix source-lake, graph-truth, portfolio, ledger, broker, or audit state
  was written.
- All generated authority artifacts kept:
  - `broker_submit_supported=false`
  - `live_broker_execution_enabled=false`
  - `real_order_authority=false`
  - `ready_for_real_money_trading_authority=false`
- Coverage is bounded to the specific PIT query windows and must not be treated
  as a universal news-lake coverage claim.

## Runs

### `moirix_sample_us_semiconductor`

- Query: target `英伟达`, market `US`, as of `2018-01-31`, lookback 7 days.
- Graph target: `NVDA`.
- Source-lake evidence rows: 2.
- `event_signal.csv` rows: 2.
- Price source for event study:
  `/Volumes/FileBackup/Moirix/data-lake/catalog/moirix.duckdb`,
  `market_data.bars_canonical_v1`, `instrument:NVDA`,
  `2018-01-20` through `2018-03-15`.
- Forward-return study output:
  - horizons: 1, 3, 5, 10, 20 trading rows;
  - forward-return rows: 10;
  - evidence tier: `pit_source_lake`;
  - status: `ok`.

Observed mean forward returns:

| Horizon | Count | Mean Forward Return |
| --- | ---: | ---: |
| 1 | 2 | 0.029532471 |
| 3 | 2 | 0.026951518 |
| 5 | 2 | 0.017558663 |
| 10 | 2 | -0.079669956 |
| 20 | 2 | 0.040533115 |

### `moirix_sample_hk_tech`

- Query: target `腾讯`, market `HK`, as of `2018-01-31`, lookback 7 days.
- Graph target: `0700.HK`.
- Source-lake evidence rows: 5.
- `event_signal.csv` rows: 5.
- Backtest: not required for this sample because G7 requires at least one
  example to complete an event-signal backtest, satisfied by
  `moirix_sample_us_semiconductor`.
- Status: `ok`.

### `moirix_sample_cn_policy`

- Query: target `监管`, market `CN`, as of `2018-01-31`, lookback 30 days.
- Graph target: `CN_POLICY`.
- Source-lake evidence rows: 10.
- `event_signal.csv` rows: 10.
- Backtest: not required for this sample because G7 requires at least one
  example to complete an event-signal backtest, satisfied by
  `moirix_sample_us_semiconductor`.
- Status: `ok`.

## Verification Commands

```bash
/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix \
  python -m moirix_vibe_adapter query-news \
  --target 英伟达 --market US --as-of 2018-01-31 \
  --lookback-days 7 --limit 5 --out /tmp/moirix-g7-us

/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix \
  python -m moirix_vibe_adapter query-news \
  --target 腾讯 --market HK --as-of 2018-01-31 \
  --lookback-days 7 --limit 5 --out /tmp/moirix-g7-hk

/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix \
  python -m moirix_vibe_adapter query-news \
  --target 监管 --market CN --as-of 2018-01-31 \
  --lookback-days 30 --limit 10 --out /tmp/moirix-g7-cn

/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix \
  python -m moirix_vibe_adapter build-event-graph \
  --input /tmp/moirix-g7-us/news_evidence.jsonl \
  --target NVDA --as-of 2018-01-31 --out /tmp/moirix-g7-us

/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix \
  python -m moirix_vibe_adapter build-event-graph \
  --input /tmp/moirix-g7-hk/news_evidence.jsonl \
  --target 0700.HK --as-of 2018-01-31 --out /tmp/moirix-g7-hk

/Users/kennymccormick/opt/miniconda3/bin/conda run -n moirix \
  python -m moirix_vibe_adapter build-event-graph \
  --input /tmp/moirix-g7-cn/news_evidence.jsonl \
  --target CN_POLICY --as-of 2018-01-31 --out /tmp/moirix-g7-cn

VIBE_TRADING_ALLOWED_RUN_ROOTS=/Users/kennymccormick/github/Vibe-Trading-Kenny/agent/runs \
  uv run --extra dev python -c \
  "import json; from src.tools.moirix_event_signal_backtest_tool import MoirixEventSignalBacktestTool; print(MoirixEventSignalBacktestTool().execute(run_dir='/Users/kennymccormick/github/Vibe-Trading-Kenny/agent/runs/moirix_sample_us_semiconductor', horizons=[1,3,5,10,20]))"
```
