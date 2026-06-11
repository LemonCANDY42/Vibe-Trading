**以 Vibe-Trading fork 作为主自用工作台，Moirix 集成进 fork，保持上游 Vibe-Trading 可持续同步，同时让 fork 拥有 Moirix 的新闻/事件影响图/可信边界能力。**

------

# PRD：Personal Vibe-Trading Fork with Integrated Moirix Extension

## 1. 产品名称

**Kenny Vibe-Trading Workbench with Moirix Extension**

内部简称：

```text
Vibe-Moirix Personal Workbench
```

代码仓库建议：

```text
LemonCANDY42/Vibe-Trading-Kenny
```

Moirix 集成模块名称：

```text
Moirix Extension
```

------

## 2. 背景

Vibe-Trading 当前已经是更接近个人自用目标的主工作台。它的 README 将其定义为一个把金融问题转化为可运行分析的 open-source research workspace，连接自然语言 prompt、market-data loaders、strategy generation、backtest engines、reports、exports 和 persistent research memory。([GitHub](https://github.com/HKUDS/Vibe-Trading))

它已经提供 CLI/TUI、Web server、MCP server 三类入口，安装后命令包括 `vibe-trading`、`vibe-trading serve`、`vibe-trading-mcp`。([GitHub](https://github.com/HKUDS/Vibe-Trading)) 它也已经覆盖自用工作台所需的大量基础能力：自然语言研究、回测、交易记录分析、persistent memory、multi-agent teams、报告导出、Alpha Zoo 等。([GitHub](https://github.com/HKUDS/Vibe-Trading))

Moirix 当前公开定位仍是 “Financial spatiotemporal event-impact graph intelligence framework”，强调 dynamic event-impact graph、point-in-time evidence ledger、canonical impact claims、active view、graph propagation、probabilistic forecasts、visual replay 和 paper portfolio evaluation；它也明确不是 live trading bot。([GitHub](https://github.com/LemonCANDY42/Moirix)) Moirix 当前 baseline 包含 daily-bar runtime portfolio validation、candidate-surface parity、inspection artifacts、DuckDB + partitioned Parquet lakehouse、OpenBB/yFinance 和 Tushare daily-bar lanes，以及 quick paper-simulation snapshot path，但 `ready_for_paper_or_live_runtime=false`、`ready_for_trading_authority=false`。([GitHub](https://github.com/LemonCANDY42/Moirix))

因此，本 PRD 的核心判断是：

> **Vibe-Trading 做主工作台。Moirix 不再作为独立主应用开发，而是作为 Vibe-Trading fork 中的新闻/事件影响图/可信边界插件集成进去。**

------

## 3. 产品目标

### 3.1 一句话目标

构建一个自用的个人交易研究 agent 工作台：基于最新 Vibe-Trading fork，持续吸收上游更新，同时集成 Moirix 的新闻证据、事件影响图、PIT/replay/coverage 校验和交易权限防误触能力，用于 US / HK / A股 / 股票 / ETF / 基金研究、回测、决策辅助和模拟盘前置检查。

### 3.2 实际使用目标

本项目服务于以下个人工作流：

```text
1. 用自然语言提出市场问题。
2. 让 agent 自动拉取行情、财报、公告、新闻、宏观、资金流等上下文。
3. 对 US / HK / A股 / ETF / 基金做研究和回测。
4. 利用 Moirix 对新闻和事件做 PIT 证据归档、实体关联、事件聚类和影响路径图。
5. 将 Moirix 事件图结果导出为 Vibe-Trading 可用的 event CSV / factor feature / run artifact。
6. 在 Vibe-Trading 中继续使用原生 backtest、Alpha Zoo、swarm、session、memory 和 Web UI。
7. 在 IBKR 模拟盘可用后，先做 read-only / paper proposal / authority guard，不默认启用真实资金交易。
8. 长期保持 fork 能从 HKUDS/Vibe-Trading 上游持续更新。
```

------

## 4. 产品原则

### 4.1 Vibe first

Vibe-Trading 是主工作台。不要重写 Vibe 已经有的：

```text
CLI / TUI
Web UI
MCP server
session
persistent memory
skills
swarm
backtest engine
Alpha Zoo
settings
upload
run detail
broker connector surface
```

### 4.2 Moirix as extension, not replacement

Moirix 只负责它最有价值的部分：

```text
PIT news/source evidence
event-impact graph
source coverage / no-future-leakage checks
evidence ledger
run artifact validator
authority guard
paper proposal guard
broker-readiness status
```

### 4.3 Upstream-compatible fork

本 fork 必须能持续吸收 Vibe-Trading 上游更新。GitHub 官方文档建议为 fork 配置 upstream remote，用于从原始仓库同步更新。([GitHub Docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/configuring-a-remote-repository-for-a-fork?utm_source=chatgpt.com)) GitHub CLI 也支持通过 `gh repo sync owner/fork -b BRANCH-NAME` 同步 fork 分支。([GitHub Docs](https://docs.github.com/articles/syncing-a-fork?utm_source=chatgpt.com))

因此，自定义代码必须尽量隔离在固定路径，降低 upstream merge conflict。

### 4.4 Research-only by default

默认只允许：

```text
research
backtest
paper simulation
paper proposal review
IBKR paper read-only
```

默认禁止：

```text
real-money execution
silent broker submit
live order without manual approval
agent 自行解除 kill switch
把新闻图谱分数直接转为下单指令
```

### 4.5 Fail closed

当 Moirix 不可用、新闻源不可用、PIT coverage 不足、broker 状态不明、quote evidence 不足、risk gate 不通过时，系统必须返回 blocked / unavailable / insufficient evidence，而不是降级后继续声称已经完成可信研究或交易准备。

------

## 5. 用户画像

本产品只有一个主用户：

```text
Kenny
```

使用模式：

```text
个人本地使用为主
偶尔在云主机 / Docker / NAS / 外接硬盘环境运行
关注 US / HK / A股 / ETF / 基金
希望能利用 agent 做研究、回测、事件分析、策略比较和模拟盘检查
不追求多用户 SaaS
不追求 marketplace
不追求 copy trading
不追求对外商业化 API
```

------

## 6. 非目标

本阶段明确不做：

```text
1. 不做新的独立 Moirix Web Workbench。
2. 不重写 Vibe-Trading 的 agent loop。
3. 不重写 Vibe-Trading 的 session / memory / skill system。
4. 不重写 Vibe-Trading 的 Alpha Zoo。
5. 不重写 Vibe-Trading 的 Backtest UI。
6. 不把 Moirix 做成新的主 CLI。
7. 不默认启用 IBKR 实盘。可以启用模拟盘。
8. 暂不支持真实资金交易权限，后续支持。
9. 不做交易信号 marketplace。
10. 不做社交化 copy trading。
11. 不把 web_search 结果伪装成 PIT 新闻数据库。
12. 不把日线 bar 数据伪装成 quote/tick/order-book evidence。
```

------

## 7. 核心产品形态

### 7.1 总体架构

```text
Vibe-Trading-Kenny fork
│
├── upstream-compatible Vibe core
│   ├── CLI / TUI
│   ├── FastAPI server
│   ├── Web UI
│   ├── MCP server
│   ├── agent loop
│   ├── skills
│   ├── swarm
│   ├── session / memory
│   ├── backtest engines
│   ├── data loaders
│   └── broker connector surface
│
└── Moirix Extension
    ├── PIT news/source evidence adapter
    ├── event-impact graph builder
    ├── event signal exporter
    ├── evidence ledger writer
    ├── coverage / leakage validator
    ├── authority guard
    ├── IBKR paper readiness checker
    └── Vibe artifact patcher
```

### 7.2 推荐仓库结构

```text
Vibe-Trading-Kenny/
  AGENTS.md

  docs/
    kenny/
      PRD_PERSONAL_VIBE_MOIRIX_FORK.md
      UPSTREAM_SYNC_POLICY.md
      LOCAL_USAGE_GUIDE.md
      IBKR_PAPER_RUNBOOK.md

    moirix/
      MOIRIX_EXTENSION_PLAN.md
      MOIRIX_EVENT_GRAPH_SKILL_SPEC.md
      MOIRIX_AUTHORITY_GUARD_BOUNDARY.md
      MOIRIX_ARTIFACT_CONTRACT.md
      MOIRIX_NEWS_EVIDENCE_CONTRACT.md

  extensions/
    moirix/
      README.md
      packages/
        moirix-vibe-adapter/
          pyproject.toml
          src/
            moirix_vibe_adapter/
              __init__.py
              cli.py
              schemas.py
              status.py
              news_query.py
              event_graph.py
              event_signal_export.py
              authority_guard.py
              vibe_artifacts.py
          tests/

  agent/
    src/
      tools/
        moirix_status_tool.py
        moirix_news_tool.py
        moirix_event_graph_tool.py
        moirix_event_signal_tool.py
        moirix_authority_guard_tool.py

      skills/
        moirix-trust/
          SKILL.md
        moirix-event-graph/
          SKILL.md
        moirix-authority-guard/
          SKILL.md

      swarm/
        presets/
          moirix_event_impact_desk.yaml
          moirix_news_to_backtest_desk.yaml

    tests/
      test_moirix_tool_optional.py
      test_moirix_news_tool.py
      test_moirix_event_graph_tool.py
      test_moirix_authority_guard_fail_closed.py

  frontend/
    src/
      components/
        moirix/
          MoirixEvidencePanel.tsx
          MoirixEventGraphPanel.tsx
          MoirixAuthorityPanel.tsx
```

### 7.3 为什么把 Moirix 放在 `extensions/moirix/`

原因：

```text
1. 和 Vibe upstream 文件隔离。
2. 后续 git merge upstream/main 时冲突少。
3. 可以将 Moirix adapter 作为可选模块。
4. Vibe 原生功能不可用时不受 Moirix 影响。
5. Moirix 可逐步缩小成 self-contained extension。
```

------

## 8. Git 分支与上游同步策略

### 8.1 远程仓库

```bash
origin   = LemonCANDY42/Vibe-Trading-Kenny
upstream = HKUDS/Vibe-Trading
moirix   = LemonCANDY42/Moirix
```

### 8.2 分支策略

```text
main
  仅跟踪 upstream/main。
  尽量不放个人定制代码。

kenny/main
  自用主分支。
  基于 main，集成 Moirix extension。
  日常运行使用这个分支。

kenny/moirix-extension-v0
  当前功能开发分支。

kenny/upstream-sync-YYYYMMDD
  每次同步上游时临时创建，用于解决冲突和跑测试。

kenny/ibkr-paper
  IBKR 模拟盘相关功能分支。
  不与新闻事件图第一阶段混在一起。
```

### 8.3 同步流程

```bash
git checkout main
git fetch upstream
git merge --ff-only upstream/main
git push origin main

git checkout kenny/main
git merge main
pytest --tb=short -q
cd frontend && npm test -- --run
git push origin kenny/main
```

或者使用 GitHub CLI：

```bash
gh repo sync LemonCANDY42/Vibe-Trading-Kenny -b main
```

### 8.4 冲突控制规则

禁止在没有充分理由时修改这些上游高频文件：

```text
README.md
README_zh.md
agent/src/agent/loop.py
agent/src/agent/context.py
agent/src/tools.py
agent/api_server.py
agent/mcp_server.py
frontend/src/pages/*
docker-compose.yml
pyproject.toml
```

允许修改但必须最小化 diff 的文件：

```text
agent/src/tools registry
agent/src/skills registry
agent/src/swarm preset registry
frontend RunDetail tab registry
.env.example
```

优先新增文件，而不是大面积改动原文件。

------

## 9. 核心用户故事

### 9.1 新闻事件影响研究

作为 Kenny，我希望输入：

```text
分析最近 30 天 NVDA、AMD、TSM、SMH 相关半导体新闻，
判断哪些事件可能影响未来 5-20 个交易日的收益和波动。
```

系统应该：

```text
1. 使用 Vibe agent 接收自然语言任务。
2. 识别这是新闻/事件影响研究。
3. 调用 Moirix PIT news query。
4. 返回 source coverage 状态。
5. 生成 news_evidence.jsonl。
6. 生成 event_impact_graph.json。
7. 生成 bull/bear/event-path summary。
8. 导出 event_signal.csv。
9. 交给 Vibe backtest 使用。
10. 在 run report 中标明：
    - 哪些是 PIT source-lake evidence；
    - 哪些只是 web_search/read_url ad-hoc evidence；
    - 哪些 source 缺失；
    - 不构成交易建议或下单权限。
```

### 9.2 新闻事件转回测特征

作为 Kenny，我希望系统把新闻事件图结果转成可以回测的特征：

```text
event_date
known_at
symbol
event_type
sentiment_score
impact_score
confidence
source_count
decay_half_life
affected_symbols
```

Vibe backtest 应能消费：

```text
moirix/event_signal.csv
```

并测试：

```text
1. 事件发生后 1 / 3 / 5 / 10 / 20 个交易日收益。
2. 对主标的和关联标的的影响。
3. 单独事件特征与技术指标组合后的效果。
4. 不同 source coverage 下结果是否稳定。
```

### 9.3 跨市场研究

作为 Kenny，我希望能研究：

```text
US: NVDA, AMD, AAPL, QQQ, SPY, SMH
HK: 0700.HK, 9988.HK, 2800.HK
A股: 沪深300、中证500、半导体、消费、银行、ETF
基金: ETF 优先，场外基金后置
```

Vibe 已经说明 yfinance 可覆盖 HK/US，mootdx 和 AKShare 可覆盖 A股，Tushare token 是可选项。([GitHub](https://github.com/HKUDS/Vibe-Trading)) 本 fork 应复用 Vibe 的数据入口，不在 Moirix 中重建全市场行情 loader。

### 9.4 上游更新不中断自用能力

作为 Kenny，我希望每周或按需从 HKUDS/Vibe-Trading 拉取最新更新，同时保留 Moirix 集成。

验收标准：

```text
1. upstream/main 可合并到 kenny/main。
2. Moirix extension 路径不产生大面积冲突。
3. Vibe 原有 CLI/Web/MCP 启动不受影响。
4. Moirix 不可用时，Vibe 原功能仍可用。
5. sync 后有一组 smoke tests 验证。
```

### 9.5 IBKR 模拟盘前置检查

作为 Kenny，我希望 IBKR paper 激活后，先让系统只读检查：

```text
account
positions
open orders
executions
quotes
historical bars
```

然后 Moirix Authority Guard 给出：

```text
ready_for_paper_proposal_review
ready_for_ibkr_paper_readonly
ready_for_ibkr_paper_submit
ready_for_real_money_trading_authority
```

默认必须是：

```json
{
  "ready_for_real_money_trading_authority": false
}
```

------

## 10. 功能需求

## P0：Fork 基础与上游同步

### P0.1 Fork 仓库建立

必须完成：

```text
1. Fork HKUDS/Vibe-Trading 到 LemonCANDY42/Vibe-Trading-Kenny。
2. 添加 upstream remote。
3. 创建 kenny/main。
4. 添加 docs/kenny/UPSTREAM_SYNC_POLICY.md。
5. 添加 AGENTS.md，明确 fork 规则。
```

验收：

```bash
git remote -v
git branch
git fetch upstream
git merge --ff-only upstream/main
```

### P0.2 自定义代码隔离

所有 Moirix 相关代码默认只能进入：

```text
extensions/moirix/
docs/moirix/
agent/src/tools/moirix_*.py
agent/src/skills/moirix-*/
agent/src/swarm/presets/moirix_*.yaml
frontend/src/components/moirix/
```

任何对上游核心文件的修改，必须在 PR 描述中说明：

```text
why this cannot be done by adding a new file
expected upstream conflict risk
test coverage
rollback path
```

------

## P0：Moirix Extension Adapter

### P0.3 Adapter CLI

Moirix extension 必须提供本地 JSON CLI：

```bash
python -m moirix_vibe_adapter status

python -m moirix_vibe_adapter query-news \
  --target NVDA \
  --market US \
  --as-of 2025-05-01T00:00:00Z \
  --lookback-days 30 \
  --out <run_root>/moirix

python -m moirix_vibe_adapter build-event-graph \
  --input <run_root>/moirix/news_evidence.jsonl \
  --target NVDA \
  --as-of 2025-05-01T00:00:00Z \
  --out <run_root>/moirix

python -m moirix_vibe_adapter export-event-signal \
  --graph <run_root>/moirix/event_impact_graph.json \
  --out <run_root>/moirix/event_signal.csv

python -m moirix_vibe_adapter authority-check \
  --proposal <proposal.json> \
  --out <run_root>/moirix
```

CLI 规则：

```text
1. stdout 只输出 JSON。
2. artifact 只写入 --out 指定目录。
3. 不读取 broker credentials。
4. 不连接真实 broker。
5. 不执行订单。
6. 不可用时返回 status=unavailable 或 status=blocked。
```

### P0.4 Adapter status schema

`status` 输出：

```json
{
  "adapter": "moirix_vibe_adapter",
  "version": "0.1.0",
  "available": true,
  "supported_scopes": [
    "research_only",
    "backtest_feature_generation",
    "paper_proposal_review"
  ],
  "unsupported_scopes": [
    "real_money_execution",
    "broker_submit"
  ],
  "ready_for_real_money_trading_authority": false
}
```

------

## P0：Vibe Tool 集成

### P0.5 新增 Vibe tools

新增：

```text
agent/src/tools/moirix_status_tool.py
agent/src/tools/moirix_news_tool.py
agent/src/tools/moirix_event_graph_tool.py
agent/src/tools/moirix_event_signal_tool.py
agent/src/tools/moirix_authority_guard_tool.py
```

工具行为：

```text
moirix_status
  检查 adapter 是否可用。

moirix_query_news
  调用 Moirix 查询 PIT news/source evidence。

moirix_build_event_graph
  基于 news_evidence.jsonl 生成 event_impact_graph.json。

moirix_export_event_signal
  将 event graph 转为 Vibe backtest 可消费 event_signal.csv。

moirix_authority_guard
  对策略候选或 paper proposal 做 fail-closed 权限检查。
```

工具发现要求：

```text
1. Moirix 不安装时，Vibe 工具注册不崩溃。
2. 工具返回 unavailable。
3. agent 报告中说明 Moirix unavailable。
4. Vibe 原有 web_search/read_url/event-driven CSV 流程仍可使用。
```

------

## P0：Moirix 新闻证据能力

### P0.6 News evidence contract

每条新闻证据必须包含：

```json
{
  "evidence_id": "string",
  "source": "tushare_news | gdelt | sec | web_search | read_url | user_upload | other",
  "source_tier": "pit_source_lake | provider_api | ad_hoc_web | user_file",
  "title": "string",
  "url": "string|null",
  "published_at": "datetime|null",
  "observed_at": "datetime",
  "ingested_at": "datetime",
  "known_at_for_backtest": "datetime",
  "content_hash": "string",
  "language": "en|zh|mixed|unknown",
  "entities": ["NVDA", "TSM", "SMH"],
  "instruments": ["US:XNAS:NVDA", "US:ARCX:SMH"],
  "event_type": "earnings|guidance|supply_chain|macro|policy|flow|litigation|other",
  "summary": "string",
  "sentiment_score": -0.2,
  "impact_score": 0.4,
  "confidence": 0.7,
  "coverage_notes": ["string"]
}
```

关键规则：

```text
published_at 不等于 known_at_for_backtest。
盘后发布、时区不明、来源延迟、网页抓取时间不明时，必须保守处理。
没有 PIT 证据时，不能声称 PIT-valid。
web_search/read_url 只能标记为 ad_hoc_web。
```

### P0.7 Coverage status

每次 Moirix news query 必须输出：

```json
{
  "target": "NVDA",
  "market": "US",
  "as_of": "2025-05-01T00:00:00Z",
  "lookback_days": 30,
  "pit_valid": true,
  "coverage_level": "partial",
  "sources_used": ["tushare_news", "web_search"],
  "sources_unavailable": ["gdelt"],
  "warnings": [
    "web_search evidence is ad-hoc and not PIT-valid unless archived before as_of"
  ]
}
```

------

## P0：事件影响图

### P0.8 Event graph output

`event_impact_graph.json` schema：

```json
{
  "graph_id": "string",
  "target": "NVDA",
  "as_of": "2025-05-01T00:00:00Z",
  "nodes": [
    {
      "node_id": "event:123",
      "node_type": "event",
      "label": "NVDA earnings guidance",
      "event_type": "earnings",
      "known_at": "datetime",
      "evidence_ids": ["e1", "e2"]
    },
    {
      "node_id": "instrument:US:XNAS:NVDA",
      "node_type": "instrument",
      "symbol": "NVDA"
    }
  ],
  "edges": [
    {
      "source": "event:123",
      "target": "instrument:US:XNAS:NVDA",
      "edge_type": "direct_impact",
      "direction": "positive",
      "lag_days": [1, 5, 20],
      "impact_score": 0.72,
      "confidence": 0.65,
      "evidence_ids": ["e1", "e2"]
    }
  ],
  "coverage": {
    "pit_valid": true,
    "coverage_level": "partial"
  },
  "authority": {
    "trading_authority": false,
    "real_money_authority": false
  }
}
```

### P0.9 Event signal export

导出为：

```text
moirix/event_signal.csv
```

字段：

```csv
known_at,symbol,event_type,sentiment_score,impact_score,confidence,source_count,decay_half_life_days,source_tier,pit_valid
```

用途：

```text
1. 被 Vibe backtest engine 作为外生事件特征。
2. 和技术指标、Alpha Zoo 因子、基本面指标组合。
3. 验证事件图是否有可测试价值。
```

------

## P0：Run artifacts

每次调用 Moirix 的 Vibe run 必须生成：

```text
<run_root>/moirix/
  status.json
  request.json
  coverage_status.json
  news_evidence.jsonl
  event_impact_graph.json
  event_signal.csv
  moirix_summary.md
  authority_status.json
  vibe_run_card_patch.json
```

`vibe_run_card_patch.json` 用于增强 Vibe 原生 run card：

```json
{
  "moirix_section": {
    "title": "Moirix Event Evidence",
    "summary_path": "moirix/moirix_summary.md",
    "coverage_status_path": "moirix/coverage_status.json",
    "event_graph_path": "moirix/event_impact_graph.json",
    "event_signal_path": "moirix/event_signal.csv",
    "authority_status_path": "moirix/authority_status.json"
  }
}
```

------

## P0：Authority Guard

### P0.10 Authority status

Moirix Authority Guard 必须输出：

```json
{
  "scope": "research_only",
  "ready_for_backtest_research": true,
  "ready_for_paper_proposal_review": true,
  "ready_for_ibkr_paper_readonly": false,
  "ready_for_ibkr_paper_submit": false,
  "ready_for_real_money_trading_authority": false,
  "blocked_by": [],
  "warnings": [
    "Moirix V0 does not submit broker orders."
  ]
}
```

### P0.11 真实资金永久 fail-closed

任何 proposal 出现以下字段时必须 blocked：

```json
{
  "execution_mode": "real_money"
}
```

返回：

```json
{
  "allowed": false,
  "reason": "real_money_execution_not_supported",
  "ready_for_real_money_trading_authority": false
}
```

------

## P1：Web UI 集成

### P1.1 Run Detail 添加 Moirix tab

在 Vibe Web Run Detail 页面加入：

```text
Moirix Evidence
Moirix Event Graph
Moirix Authority
```

第一版可以只显示 JSON / Markdown，不需要复杂图可视化。

### P1.2 Event Graph 可视化

第二版再做：

```text
1. 事件节点列表。
2. 影响路径列表。
3. 标的节点列表。
4. source evidence 展开。
5. edge confidence / lag days / source count。
```

------

## P1：Moirix Skill

### P1.3 新增 `moirix-event-graph` skill

路径：

```text
agent/src/skills/moirix-event-graph/SKILL.md
```

内容要求：

```text
Use when:
- 用户问新闻、公告、政策、财报、宏观事件对股票/ETF/行业影响。
- 用户希望构建事件驱动策略。
- 用户希望把新闻转成回测特征。
- 用户希望判断某个市场事件的传播路径。

Do not use when:
- 用户只是要普通技术分析。
- 用户要直接下单。
- 用户要真实资金交易授权。
- Moirix adapter unavailable 且用户要求 PIT-valid evidence。

Required flow:
1. moirix_status
2. moirix_query_news
3. moirix_build_event_graph
4. moirix_export_event_signal
5. optional Vibe backtest
6. report coverage and authority boundary
```

------

## P1：Moirix Swarm

### P1.4 新增 `moirix_event_impact_desk.yaml`

路径：

```text
agent/src/swarm/presets/moirix_event_impact_desk.yaml
```

角色：

```text
evidence_librarian
  查询 Moirix PIT evidence 和 coverage。

event_graph_analyst
  构建事件影响图。

bull_bear_debate
  基于证据形成正反 thesis。

strategy_translator
  把事件图转成 event_signal.csv / factor feature。

risk_reviewer
  检查数据覆盖、future leakage、authority boundary。
```

禁止：

```text
broker submit
real-money trading
automatic order approval
```

------

## P2：IBKR Paper 只读集成

### P2.1 IBKR paper readiness

IBKR paper 激活后，优先做只读检查：

```text
connectivity
account summary
positions
open orders
executions
market data permission
historical data permission
```

输出：

```text
<run_root>/moirix/ibkr_paper_readiness.json
```

### P2.2 Paper proposal guard

只在 Vibe 或 IBKR connector 生成 paper proposal 后调用 Moirix：

```text
proposal -> moirix_authority_guard -> allowed/blocked
```

第一版不由 Moirix 提交订单。

### P2.3 Paper submit 仍不在本 PRD V0 范围

只有当以下条件都满足，才另写 PRD：

```text
PostgreSQL authoritative state
idempotency key
order lifecycle state machine
broker reconciliation
manual approval artifact
kill switch
IBKR paper evidence
independent review
```

------

## 11. 示例用户命令

### 11.1 新闻事件图研究

```bash
vibe-trading run -p "
Use Moirix to analyze how recent semiconductor news may affect NVDA, AMD, TSM, SMH, and QQQ.
Use PIT-valid evidence when available.
Build an event-impact graph.
Export event_signal.csv for backtesting.
Clearly label coverage gaps and do not make any trading-authority claim.
"
```

### 11.2 A股事件驱动研究

```bash
vibe-trading run -p "
使用 Moirix 分析最近 60 天 A股半导体板块的政策、公告、新闻事件，
构建事件影响图，并导出适合回测的事件特征。
如果新闻源不是 PIT-valid，必须标明为 ad-hoc research。
"
```

### 11.3 回测事件特征

```bash
vibe-trading run -p "
Use the Moirix event_signal.csv from the previous run.
Backtest whether positive high-confidence event clusters improve 5-day and 20-day forward returns
for NVDA, AMD, TSM, SMH, and QQQ.
Compare against a baseline momentum strategy.
"
```

### 11.4 IBKR paper readiness

```bash
vibe-trading run -p "
Check whether my IBKR paper environment is ready for read-only inspection.
Do not submit orders.
Return Moirix authority status and blockers.
"
```

------

## 12. 测试要求

### 12.1 Vibe fork tests

```bash
pytest agent/tests/test_moirix_tool_optional.py -q
pytest agent/tests/test_moirix_news_tool.py -q
pytest agent/tests/test_moirix_event_graph_tool.py -q
pytest agent/tests/test_moirix_authority_guard_fail_closed.py -q
```

### 12.2 Moirix adapter tests

```bash
pytest extensions/moirix/packages/moirix-vibe-adapter/tests -q
python -m moirix_vibe_adapter status
```

### 12.3 Upstream sync smoke

```bash
git fetch upstream
git checkout kenny/main
git merge upstream/main

python -m py_compile agent/api_server.py agent/mcp_server.py
pytest --tb=short -q
cd frontend && npm install && npm run build
```

### 12.4 Fail-closed tests

必须覆盖：

```text
1. Moirix adapter missing。
2. Moirix source lake missing。
3. query-news 无 provider token。
4. event graph input empty。
5. request tries to write outside run_root。
6. proposal requests real_money execution。
7. proposal requests broker_submit。
8. IBKR status unknown。
```

------

## 13. 成功指标

### 13.1 V0 成功指标

```text
1. Vibe-Trading 原生功能不受影响。
2. Moirix 不可用时，Vibe 仍能正常运行。
3. Moirix 可用时，agent 可以调用 moirix_query_news 和 moirix_build_event_graph。
4. 每次 Moirix run 都生成 artifacts。
5. event_signal.csv 能被后续 Vibe backtest 使用。
6. 所有 Moirix 输出都明确 coverage 和 authority。
7. real_money authority 永远 false。
8. upstream/main 合并到 kenny/main 时冲突集中在少数集成点。
```

### 13.2 V1 成功指标

```text
1. Run Detail 页面能显示 Moirix evidence / graph / authority。
2. 至少完成 3 个真实自用样例：
   - US semiconductor news graph
   - HK tech news graph
   - A股政策/公告事件图
3. 至少 1 个 Moirix event_signal.csv 回测跑通。
4. IBKR paper read-only readiness 跑通。
5. 所有 broker-write 行为仍默认禁用。
```

------

## 14. 里程碑

### Milestone 0：Fork hygiene

目标：

```text
创建 Vibe-Trading-Kenny fork。
配置 upstream。
建立 kenny/main。
添加 AGENTS.md 和 docs/kenny/UPSTREAM_SYNC_POLICY.md。
```

完成标准：

```text
可以成功从 upstream/main 合并。
Vibe 原生命令能启动。
```

### Milestone 1：Moirix adapter V0

目标：

```text
在 extensions/moirix/ 中实现 moirix_vibe_adapter。
提供 status / query-news / build-event-graph / export-event-signal / authority-check。
```

完成标准：

```text
CLI JSON 输出稳定。
缺少数据源时 fail closed。
无 broker 行为。
```

### Milestone 2：Vibe tool integration

目标：

```text
Vibe agent 可发现 moirix_* tools。
Moirix 不安装时不崩溃。
Moirix 安装时可生成 run artifacts。
```

完成标准：

```text
vibe-trading run -p "Use Moirix ..." 能跑通一次示例。
```

### Milestone 3：Skill + swarm

目标：

```text
新增 moirix-event-graph skill。
新增 moirix_event_impact_desk swarm。
```

完成标准：

```text
agent 能按 skill flow 自动调用 Moirix 工具。
```

### Milestone 4：Event signal to backtest

目标：

```text
Moirix event graph 导出 event_signal.csv。
Vibe backtest 可消费该文件。
```

完成标准：

```text
NVDA / SMH / AMD 示例跑出回测报告。
```

### Milestone 5：Web UI tab

目标：

```text
Run Detail 添加 Moirix Evidence / Event Graph / Authority tab。
```

完成标准：

```text
Web UI 能查看 Moirix artifacts。
```

### Milestone 6：IBKR paper read-only

目标：

```text
IBKR paper 激活后，只读检查 account / positions / open orders / executions。
```

完成标准：

```text
生成 ibkr_paper_readiness.json。
ready_for_real_money_trading_authority=false。
```

------

## 15. 给 coding agent 的操作清单

下面这部分可以直接复制给不同 agent。

------

### Agent 0：Root fork setup

工作目录：

```text
/path/to/Vibe-Trading-Kenny
```

任务：

```text
Create a personal fork integration foundation for Vibe-Trading-Kenny.

Read:
- README.md
- AGENT_CONTRIBUTOR_GUIDE.md
- pyproject.toml
- agent/src/tools
- agent/src/skills
- agent/src/swarm/presets

Implement:
1. Add AGENTS.md at repository root.
2. Add docs/kenny/PRD_PERSONAL_VIBE_MOIRIX_FORK.md.
3. Add docs/kenny/UPSTREAM_SYNC_POLICY.md.
4. Add docs/kenny/LOCAL_USAGE_GUIDE.md.
5. Do not modify Vibe core behavior.
6. Document branch strategy:
   - main tracks upstream/main
   - kenny/main contains personal integration
   - custom code isolated under extensions/moirix and moirix_* paths

Acceptance:
- git diff only docs + AGENTS.md.
- No functional code changed.
```

------

### Agent 1：Moirix adapter

工作目录：

```text
/path/to/Vibe-Trading-Kenny/extensions/moirix
```

任务：

```text
Implement Moirix adapter package for Vibe integration.

Create:
- packages/moirix-vibe-adapter/pyproject.toml
- packages/moirix-vibe-adapter/src/moirix_vibe_adapter/
- packages/moirix-vibe-adapter/tests/

Required CLI:
- python -m moirix_vibe_adapter status
- python -m moirix_vibe_adapter query-news
- python -m moirix_vibe_adapter build-event-graph
- python -m moirix_vibe_adapter export-event-signal
- python -m moirix_vibe_adapter authority-check

Rules:
- JSON stdout only.
- Artifacts only under --out.
- No broker API calls.
- No credential writes.
- ready_for_real_money_trading_authority always false in V0.
- Missing source lake returns blocked/unavailable, not fake data.

Tests:
- status works.
- missing source lake fail-closed.
- tiny fixture builds event_impact_graph.json.
- event_signal.csv exported.
- authority-check blocks real_money and broker_submit.
```

------

### Agent 2：Vibe tools integration

工作目录：

```text
/path/to/Vibe-Trading-Kenny
```

任务：

```text
Add optional Moirix tools to Vibe.

Create:
- agent/src/tools/moirix_status_tool.py
- agent/src/tools/moirix_news_tool.py
- agent/src/tools/moirix_event_graph_tool.py
- agent/src/tools/moirix_event_signal_tool.py
- agent/src/tools/moirix_authority_guard_tool.py

Behavior:
- Tools call MOIRIX_ADAPTER_CMD if set.
- Else try python -m moirix_vibe_adapter.
- If unavailable, return structured unavailable response.
- Never crash Vibe if Moirix missing.
- Never submit broker orders.
- Write outputs only into current run artifact root.

Tests:
- tools discoverable.
- Moirix missing returns unavailable.
- path traversal blocked.
- real_money request blocked.
```

------

### Agent 3：Skill and swarm

工作目录：

```text
/path/to/Vibe-Trading-Kenny
```

任务：

```text
Add Moirix research skill and swarm preset.

Create:
- agent/src/skills/moirix-event-graph/SKILL.md
- agent/src/skills/moirix-trust/SKILL.md
- agent/src/skills/moirix-authority-guard/SKILL.md
- agent/src/swarm/presets/moirix_event_impact_desk.yaml
- agent/src/swarm/presets/moirix_news_to_backtest_desk.yaml
- docs/moirix/MOIRIX_EVENT_GRAPH_SKILL_SPEC.md

Skill rules:
- Use Moirix for news/event impact research.
- Query evidence first.
- Build graph second.
- Export event signal third.
- Optional backtest fourth.
- Never convert graph score into direct trade.
- Clearly label PIT evidence vs ad-hoc web evidence.
- If Moirix unavailable, fall back to Vibe web_search/read_url only with explicit label.

Swarm roles:
- evidence_librarian
- event_graph_analyst
- bull_bear_debate
- strategy_translator
- risk_reviewer

No broker tools in swarm.
```

------

### Agent 4：Run artifact integration

工作目录：

```text
/path/to/Vibe-Trading-Kenny
```

任务：

```text
Integrate Moirix artifacts into Vibe run output.

Implement:
1. Locate current Vibe run artifact root helper.
2. Ensure moirix tools write to <run_root>/moirix/.
3. Add vibe_run_card_patch.json generation.
4. Ensure reports mention Moirix artifacts when present.
5. Do not break existing run cards.

Artifacts:
- moirix/status.json
- moirix/request.json
- moirix/coverage_status.json
- moirix/news_evidence.jsonl
- moirix/event_impact_graph.json
- moirix/event_signal.csv
- moirix/moirix_summary.md
- moirix/authority_status.json
- moirix/vibe_run_card_patch.json

Tests:
- run with mock adapter produces all artifacts.
- run without adapter produces no crash.
```

------

### Agent 5：Frontend Moirix tab

工作目录：

```text
/path/to/Vibe-Trading-Kenny/frontend
```

任务：

```text
Add a minimal Moirix section to RunDetail.

Create:
- frontend/src/components/moirix/MoirixEvidencePanel.tsx
- frontend/src/components/moirix/MoirixEventGraphPanel.tsx
- frontend/src/components/moirix/MoirixAuthorityPanel.tsx

Behavior:
- Show Moirix tab only when run artifacts include moirix/vibe_run_card_patch.json.
- First version may render Markdown/JSON.
- Do not implement complex graph visualization in V0.
- Do not modify unrelated pages.

Tests:
- frontend build passes.
- RunDetail without Moirix artifacts unchanged.
- RunDetail with Moirix artifacts shows tabs.
```

------

### Agent 6：Independent review

工作目录：

```text
/path/to/Vibe-Trading-Kenny
```

任务：

```text
Review the Moirix integration.

Check:
1. Upstream compatibility.
2. No broker write path.
3. No real-money authority.
4. Missing Moirix fails closed.
5. Path writes restricted to run artifact root.
6. Vibe original tools still work.
7. README/docs do not overclaim PIT news coverage.
8. Web_search/read_url evidence is labeled ad-hoc.
9. event_signal.csv does not use future information.
10. Tests actually run.

Produce:
- docs/kenny/REVIEW_MOIRIX_EXTENSION_V0.md

Include:
- commands run
- blocking findings
- non-blocking findings
- exact files reviewed
- merge recommendation
```

------

## 16. 最终推荐路线

实际执行顺序：

```text
1. Fork Vibe-Trading 最新 main。
2. 建立 main / kenny/main 分支策略。
3. 添加 AGENTS.md 和 PRD。
4. 在 fork 内新增 extensions/moirix/moirix-vibe-adapter。
5. 在 Vibe agent tools 中新增 moirix_* tools。
6. 新增 moirix-event-graph skill。
7. 新增 moirix_event_impact_desk swarm。
8. 先跑 NVDA / SMH 新闻事件图示例。
9. 再导出 event_signal.csv 跑 Vibe backtest。
10. 最后接 RunDetail UI。
11. IBKR paper 只读检查单独开分支做。
```

项目定位最终应固定为：

```text
Vibe-Trading-Kenny = Kenny 的个人交易研究 agent 工作台
Moirix Extension = 新闻/事件影响图/可信证据/权限边界插件
```

这条路线能满足三个核心约束：

```text
1. 自用优先，尽快可用。
2. 持续吸收 Vibe-Trading 上游能力。
3. 保留 Moirix 的差异化价值，而不是重复造完整工作台。
```