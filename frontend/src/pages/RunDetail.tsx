import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  Code2,
  Database,
  Download,
  FileCheck2,
  Fingerprint,
  Gauge,
  List,
  Loader2,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type BacktestMetrics, type RunCard, type RunData } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EquityChart } from "@/components/charts/EquityChart";
import { MetricsCard } from "@/components/chat/MetricsCard";
import { ValidationPanel } from "@/components/charts/ValidationPanel";
import { Skeleton, SkeletonMetrics, SkeletonChart } from "@/components/common/Skeleton";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";

const rehypePlugins = [rehypeHighlight];

type Tab = "chart" | "trades" | "runCard" | "code" | "validation" | "moirixEvidence" | "moirixGraph" | "moirixAuthority";
type ChartPayload = Pick<RunData, "price_series" | "indicator_series" | "trade_markers">;
type ChartCache = Record<string, ChartPayload>;
type ChartLoadProgress = { done: number; total: number };

const MULTI_CHART_PAGE_SIZE = 8;

function parseTab(value: string | null): Tab {
  switch (value) {
    case "chart":
    case "trades":
    case "runCard":
    case "code":
    case "validation":
    case "moirixEvidence":
    case "moirixGraph":
    case "moirixAuthority":
      return value;
    default:
      return "chart";
  }
}

function downloadCsv(filename: string, csvContent: string) {
  const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function escapeCsvField(value: unknown): string {
  const str = String(value ?? "");
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function buildTradesCsv(trades: Array<Record<string, string>>): string {
  if (trades.length === 0) return "";
  const keys = [...new Set(trades.flatMap(Object.keys))];
  const header = keys.map(escapeCsvField).join(",");
  const rows = trades.map(tr => keys.map(k => escapeCsvField(tr[k])).join(","));
  return [header, ...rows].join("\n");
}

function buildMetricsCsv(metrics: BacktestMetrics): string {
  const header = "metric,value";
  const rows = Object.entries(metrics).map(([k, v]) => `${escapeCsvField(k)},${escapeCsvField(v)}`);
  return [header, ...rows].join("\n");
}

function cacheFromRun(run: RunData | null, requestedSymbol?: string): ChartCache {
  if (!run?.price_series) return {};
  const cache: ChartCache = {};
  const markerRows = run.trade_markers || [];
  for (const [symbol, bars] of Object.entries(run.price_series)) {
    cache[symbol] = {
      price_series: { [symbol]: bars },
      indicator_series: run.indicator_series?.[symbol] ? { [symbol]: run.indicator_series[symbol] } : {},
      trade_markers: markerRows.filter((marker) => !marker.code || marker.code === symbol),
    };
  }
  if (requestedSymbol && !cache[requestedSymbol]) {
    cache[requestedSymbol] = { price_series: {}, indicator_series: {}, trade_markers: [] };
  }
  return cache;
}

function mergeChartCache(current: ChartCache, next: ChartCache): ChartCache {
  return { ...current, ...next };
}

function yieldToBrowser(): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, 0);
  });
}

export function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [run, setRun] = useState<RunData | null>(null);
  const [code, setCode] = useState<Record<string, string>>({});
  const [tab, setTab] = useState<Tab>(() => parseTab(searchParams.get("tab")));
  const [loading, setLoading] = useState(true);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [chartPickerSymbol, setChartPickerSymbol] = useState("");
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [chartCache, setChartCache] = useState<ChartCache>({});
  const [chartLoadingSymbols, setChartLoadingSymbols] = useState<Record<string, boolean>>({});
  const [bulkChartLoading, setBulkChartLoading] = useState(false);
  const [bulkChartProgress, setBulkChartProgress] = useState<ChartLoadProgress>({ done: 0, total: 0 });
  const chartCacheRef = useRef<ChartCache>({});
  const cancelBulkChartLoadRef = useRef(false);

  const hasValidation = !!run?.validation;
  const hasRunCard = !!run?.run_card;
  const hasMoirix = hasMoirixArtifacts(run);
  const TABS: { id: Tab; label: string; icon: typeof BarChart3; hidden?: boolean }[] = [
    { id: "chart", label: "Chart", icon: BarChart3 },
    { id: "trades", label: "Trades", icon: List },
    { id: "validation", label: "Validation", icon: ShieldCheck, hidden: !hasValidation },
    { id: "runCard", label: "Run Card", icon: FileCheck2, hidden: !hasRunCard },
    { id: "moirixEvidence", label: "Moirix Evidence", icon: Database, hidden: !hasMoirix },
    { id: "moirixGraph", label: "Moirix Graph", icon: BarChart3, hidden: !hasMoirix },
    { id: "moirixAuthority", label: "Moirix Authority", icon: ShieldCheck, hidden: !hasMoirix },
    { id: "code", label: "Code", icon: Code2 },
  ];

  useEffect(() => {
    if (!runId) return;
    Promise.all([
      api.getRun(runId).catch(() => null),
      api.getRunCode(runId).catch(() => ({})),
    ]).then(([r, c]) => {
      setRun(r);
      setCode(c || {});
      const firstSymbol = r?.chart_symbols?.[0] || Object.keys(r?.price_series || {})[0] || "";
      setSelectedSymbol(firstSymbol);
      setChartPickerSymbol(firstSymbol);
      setSelectedSymbols(firstSymbol ? [firstSymbol] : []);
      const initialCache = cacheFromRun(r, firstSymbol);
      chartCacheRef.current = initialCache;
      setChartCache(initialCache);
    }).finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => {
    setTab(parseTab(searchParams.get("tab")));
  }, [searchParams]);

  if (loading) {
    return (
      <div className="p-8 space-y-4">
        <Skeleton className="h-6 w-48" />
        <SkeletonMetrics />
        <SkeletonChart height={400} />
      </div>
    );
  }
  if (!run) return (
    <div className="p-8 space-y-2">
      <p className="text-red-500 font-medium">Run not found</p>
      <p className="text-sm text-muted-foreground">
        The run directory may have been removed, or your browser may not have API access configured.
        Check that the API authentication key is set in Settings if accessing remotely.
      </p>
      <button
        onClick={() => navigate(-1)}
        className="text-sm text-primary hover:underline inline-flex items-center gap-1.5"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Go back
      </button>
    </div>
  );

  const ok = run.status === "success";

  async function loadChartSymbol(symbol: string) {
    if (!runId || !symbol) return;
    if (chartCacheRef.current[symbol]?.price_series?.[symbol]?.length) return;
    setChartLoadingSymbols((prev) => ({ ...prev, [symbol]: true }));
    try {
      const nextRun = await api.getRun(runId, { chart_symbol: symbol });
      const nextCache = cacheFromRun(nextRun, symbol);
      const mergedCache = mergeChartCache(chartCacheRef.current, nextCache);
      chartCacheRef.current = mergedCache;
      setChartCache(mergedCache);
      setRun((prev) => prev ? {
        ...prev,
        chart_symbols: nextRun.chart_symbols?.length ? nextRun.chart_symbols : prev.chart_symbols,
        equity_curve: nextRun.equity_curve?.length ? nextRun.equity_curve : prev.equity_curve,
      } : nextRun);
    } finally {
      setChartLoadingSymbols((prev) => {
        const next = { ...prev };
        delete next[symbol];
        return next;
      });
    }
  }

  async function handleAddChartSymbol(symbol: string) {
    if (!symbol) return;
    setSelectedSymbol(symbol);
    setChartPickerSymbol(symbol);
    setSelectedSymbols((prev) => prev.includes(symbol) ? prev : [...prev, symbol]);
    await loadChartSymbol(symbol);
  }

  async function handleCurrentChartOnly(symbol: string) {
    if (!symbol) return;
    setSelectedSymbol(symbol);
    setChartPickerSymbol(symbol);
    setSelectedSymbols([symbol]);
    await loadChartSymbol(symbol);
  }

  function handleRemoveChartSymbol(symbol: string) {
    const nextSymbols = selectedSymbols.filter((item) => item !== symbol);
    setSelectedSymbols(nextSymbols);
    if (selectedSymbol === symbol) {
      const fallback = nextSymbols[0] || chartPickerSymbol || run?.chart_symbols?.[0] || "";
      setSelectedSymbol(fallback);
      setChartPickerSymbol(fallback);
    }
  }

  async function handleLoadAllChartSymbols() {
    const symbols = run?.chart_symbols || [];
    if (symbols.length === 0 || bulkChartLoading) return;
    cancelBulkChartLoadRef.current = false;
    setBulkChartLoading(true);
    setBulkChartProgress({ done: 0, total: symbols.length });
    try {
      for (let index = 0; index < symbols.length; index += 1) {
        if (cancelBulkChartLoadRef.current) break;
        const symbol = symbols[index];
        setSelectedSymbol(symbol);
        setChartPickerSymbol(symbol);
        setSelectedSymbols((prev) => prev.includes(symbol) ? prev : [...prev, symbol]);
        await loadChartSymbol(symbol);
        setBulkChartProgress({ done: index + 1, total: symbols.length });
        await yieldToBrowser();
      }
    } finally {
      setBulkChartLoading(false);
    }
  }

  function handleCancelLoadAllCharts() {
    cancelBulkChartLoadRef.current = true;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b p-4 space-y-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="p-1 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title="Go back"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          {ok ? <CheckCircle2 className="h-5 w-5 text-success" /> : <XCircle className="h-5 w-5 text-danger" />}
          <h1 className="font-mono text-sm font-medium">{runId}</h1>
          {run.elapsed_seconds && <span className="text-xs text-muted-foreground">{run.elapsed_seconds.toFixed(1)}s</span>}
        </div>
        {run.prompt && <p className="text-sm text-muted-foreground">{run.prompt}</p>}
        {run.metrics && <MetricsCard metrics={run.metrics as Record<string, number>} />}
        {run.llm_usage && <LLMUsagePanel usage={run.llm_usage} />}

        <div className="flex items-center gap-1">
          {TABS.filter(t => !t.hidden).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors",
                tab === id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              )}
            >
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}

          <div className="ml-auto flex gap-1">
            {run.trade_log && run.trade_log.length > 0 && (
              <button
                onClick={() => downloadCsv(`trades_${runId}.csv`, buildTradesCsv(run.trade_log!))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs text-muted-foreground hover:bg-muted transition-colors"
                title="Download Trades CSV"
              >
                <Download className="h-3.5 w-3.5" /> Download Trades CSV
              </button>
            )}
            {run.metrics && (
              <button
                onClick={() => downloadCsv(`metrics_${runId}.csv`, buildMetricsCsv(run.metrics!))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs text-muted-foreground hover:bg-muted transition-colors"
                title="Download Metrics CSV"
              >
                <Download className="h-3.5 w-3.5" /> Download Metrics CSV
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <ErrorBoundary>
          {tab === "chart" && (
            <ChartTab
              run={run}
              selectedSymbol={selectedSymbol}
              chartPickerSymbol={chartPickerSymbol}
              selectedSymbols={selectedSymbols}
              chartCache={chartCache}
              loadingSymbols={chartLoadingSymbols}
              bulkLoading={bulkChartLoading}
              bulkProgress={bulkChartProgress}
              onPickSymbol={setChartPickerSymbol}
              onAddSymbol={handleAddChartSymbol}
              onCurrentOnly={handleCurrentChartOnly}
              onRemoveSymbol={handleRemoveChartSymbol}
              onLoadAll={handleLoadAllChartSymbols}
              onCancelLoadAll={handleCancelLoadAllCharts}
            />
          )}
          {tab === "trades" && <TradesTab run={run} />}
          {tab === "validation" && run.validation && <ValidationPanel data={run.validation} />}
          {tab === "runCard" && run.run_card && <RunCardTab card={run.run_card} />}
          {tab === "moirixEvidence" && <MoirixTab run={run} kind="evidence" />}
          {tab === "moirixGraph" && <MoirixTab run={run} kind="graph" />}
          {tab === "moirixAuthority" && <MoirixTab run={run} kind="authority" />}
          {tab === "code" && <CodeTab code={code} />}
        </ErrorBoundary>
      </div>
    </div>
  );
}

function hasMoirixArtifacts(run: RunData | null): boolean {
  if (!run) return false;
  if (run.moirix_artifacts && Object.keys(run.moirix_artifacts).length > 0) return true;
  return (run.artifacts || []).some((artifact) => artifact.name.startsWith("moirix/") || artifact.path.includes("/artifacts/moirix/"));
}

function LLMUsagePanel({ usage }: { usage: NonNullable<RunData["llm_usage"]> }) {
  const iterations = (usage.iterations || [])
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      iter: toFiniteNumber(item.iter),
      input: toFiniteNumber(item.input_tokens),
      output: toFiniteNumber(item.output_tokens),
      cache: toFiniteNumber(item.cache_creation_input_tokens) + toFiniteNumber(item.cache_read_input_tokens),
      total: toFiniteNumber(item.total_tokens),
    }))
    .filter((item) => item.input || item.output || item.total);
  const maxTotal = Math.max(1, ...iterations.map((item) => item.total || item.input + item.output + item.cache));
  const calls = typeof usage.calls === "number" ? usage.calls : iterations.length;
  const providerModel = [usage.provider, usage.model].filter(Boolean).join(" / ") || "Unknown provider";
  const cacheTokens = toFiniteNumber(usage.cache_creation_input_tokens) + toFiniteNumber(usage.cache_read_input_tokens);

  return (
    <section className="rounded-md border bg-card p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium">
        <Gauge className="h-4 w-4 text-muted-foreground" />
        Agent Usage
      </div>
      <div className="grid gap-3 md:grid-cols-5">
        <RunCardStat label="Input tokens" value={formatTokenCount(usage.input_tokens)} />
        <RunCardStat label="Output tokens" value={formatTokenCount(usage.output_tokens)} />
        <RunCardStat label="Cache tokens" value={formatTokenCount(cacheTokens)} />
        <RunCardStat label="Total tokens" value={formatTokenCount(usage.total_tokens)} />
        <RunCardStat label="LLM calls" value={String(calls)} />
      </div>
      <div className="mt-3 truncate text-xs text-muted-foreground">{providerModel}</div>
      {iterations.length > 0 && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-sky-500" />Input</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-emerald-500" />Output</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-amber-500" />Cache</span>
            <span className="ml-auto">per iteration</span>
          </div>
          {iterations.slice(0, 20).map((item, index) => {
            const total = item.total || item.input + item.output + item.cache;
            const totalWidth = Math.max(2, Math.min(100, (total / maxTotal) * 100));
            const inputShare = total > 0 ? Math.min(100, (item.input / total) * 100) : 0;
            const outputShare = total > 0 ? Math.min(100, (item.output / total) * 100) : 0;
            const cacheShare = total > 0 ? Math.max(0, 100 - inputShare - outputShare) : 0;
            return (
              <div key={`${item.iter}-${index}`} className="grid grid-cols-[3rem_1fr_5.5rem] items-center gap-2 text-xs">
                <div className="font-mono text-muted-foreground">#{item.iter || index + 1}</div>
                <div className="h-3 overflow-hidden rounded-sm bg-muted">
                  <div className="flex h-full" style={{ width: `${totalWidth}%` }}>
                    <div className="h-full bg-sky-500" style={{ width: `${inputShare}%` }} />
                    <div className="h-full bg-emerald-500" style={{ width: `${outputShare}%` }} />
                    <div className="h-full bg-amber-500" style={{ width: `${cacheShare}%` }} />
                  </div>
                </div>
                <div className="text-right font-mono tabular-nums text-muted-foreground">
                  {formatTokenCount(total)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function MoirixTab({ run, kind }: { run: RunData; kind: "evidence" | "graph" | "authority" }) {
  const data = run.moirix_artifacts || {};
  const artifacts = (run.artifacts || []).filter((artifact) => artifact.name.startsWith("moirix/") || artifact.path.includes("/artifacts/moirix/"));
  if (Object.keys(data).length === 0 && artifacts.length === 0) {
    return <div className="p-8 text-sm text-muted-foreground">No Moirix artifacts recorded.</div>;
  }

  if (kind === "evidence") {
    return (
      <div className="p-4 space-y-4">
        {typeof data.moirix_summary_markdown === "string" && (
          <RunCardPanel title="Summary" icon={FileCheck2}>
            <div className="prose prose-sm max-w-none dark:prose-invert">
              <ReactMarkdown rehypePlugins={rehypePlugins}>{data.moirix_summary_markdown}</ReactMarkdown>
            </div>
          </RunCardPanel>
        )}
        <div className="grid gap-4 xl:grid-cols-2">
          <RunCardPanel title="Status" icon={Database}>
            <JsonBlock value={data.status} />
          </RunCardPanel>
          <RunCardPanel title="Coverage" icon={ShieldCheck}>
            <JsonBlock value={data.coverage_status} />
          </RunCardPanel>
        </div>
        <RunCardPanel title="News Evidence Preview" icon={List}>
          <PreviewTable value={data.news_evidence_preview} empty="No news evidence preview recorded." />
        </RunCardPanel>
      </div>
    );
  }

  if (kind === "graph") {
    return (
      <div className="p-4 space-y-4">
        <RunCardPanel title="Event Impact Graph" icon={BarChart3}>
          <JsonBlock value={data.event_impact_graph} />
        </RunCardPanel>
        <div className="grid gap-4 xl:grid-cols-2">
          <RunCardPanel title="Event Signal Preview" icon={Database}>
            <PreviewTable value={data.event_signal_preview} empty="No event signal preview recorded." />
          </RunCardPanel>
          <RunCardPanel title="Forward Returns Preview" icon={BarChart3}>
            <PreviewTable value={data.event_signal_forward_returns_preview} empty="No forward-return preview recorded." />
          </RunCardPanel>
        </div>
        <RunCardPanel title="Event Signal Study" icon={FileCheck2}>
          <JsonBlock value={data.event_signal_backtest_summary} />
        </RunCardPanel>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <RunCardPanel title="Authority Status" icon={ShieldCheck}>
          <JsonBlock value={data.authority_status || data.moirix_authority_status} />
        </RunCardPanel>
        <RunCardPanel title="Run Card Patch" icon={FileCheck2}>
          <JsonBlock value={data.vibe_run_card_patch} />
        </RunCardPanel>
      </div>
      <RunCardPanel title="Authority Checks" icon={ShieldCheck}>
        <JsonBlock value={data.authority_checks} />
      </RunCardPanel>
      <RunCardPanel title="Moirix Artifact Manifest" icon={Database}>
        <PreviewTable value={(data.artifact_names as string[] | undefined)?.map((name) => ({ artifact: name }))} empty="No Moirix artifact manifest recorded." />
      </RunCardPanel>
    </div>
  );
}

function RunCardTab({ card }: { card: RunCard }) {
  const backtest = card.backtest || {};
  const reproducibility = card.reproducibility || {};
  const metrics = card.metrics || {};
  const artifacts = card.artifacts || [];
  const warnings = card.warnings || [];
  const dataSources = card.data_sources || [];

  return (
    <div className="p-4 space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <RunCardStat label="Schema" value={card.schema_version || "unknown"} />
        <RunCardStat label="Generated" value={formatRunCardValue(card.generated_at)} />
        <RunCardStat label="Data sources" value={dataSources.length ? dataSources.join(", ") : "None recorded"} />
        <RunCardStat label="Warnings" value={String(warnings.length)} tone={warnings.length ? "warning" : "normal"} />
      </div>

      {warnings.length > 0 && (
        <section className="rounded-md border border-amber-500/25 bg-amber-500/5 p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-300">
            <AlertTriangle className="h-4 w-4" />
            Warnings
          </div>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {warnings.map((warning, index) => <li key={index}>{warning}</li>)}
          </ul>
        </section>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <RunCardPanel title="Backtest Summary" icon={Database}>
          <KeyValueTable data={backtest} empty="No backtest summary recorded." />
        </RunCardPanel>
        <RunCardPanel title="Reproducibility" icon={Fingerprint}>
          <KeyValueTable data={reproducibility} empty="No reproducibility hashes recorded." monospaceValues />
        </RunCardPanel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <RunCardPanel title="Metrics" icon={BarChart3}>
          <KeyValueTable data={metrics} empty="No scalar metrics recorded." />
        </RunCardPanel>
        <RunCardPanel title="Validation" icon={ShieldCheck}>
          {card.validation ? (
            <pre className="max-h-80 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
              {JSON.stringify(card.validation, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">No validation payload recorded.</p>
          )}
        </RunCardPanel>
      </div>

      <RunCardPanel title="Artifact Checksums" icon={FileCheck2}>
        {artifacts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-4">Path</th>
                  <th className="py-2 pr-4">Size</th>
                  <th className="py-2">SHA-256</th>
                </tr>
              </thead>
              <tbody>
                {artifacts.map((artifact) => (
                  <tr key={`${artifact.path}-${artifact.sha256}`} className="border-b last:border-0">
                    <td className="py-2 pr-4 font-mono text-xs">{artifact.path}</td>
                    <td className="py-2 pr-4 tabular-nums text-muted-foreground">{formatBytes(artifact.size_bytes)}</td>
                    <td className="py-2 font-mono text-xs text-muted-foreground">{shortHash(artifact.sha256)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No artifact checksums recorded.</p>
        )}
      </RunCardPanel>
    </div>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  if (value === undefined || value === null || value === "") {
    return <p className="text-sm text-muted-foreground">Not recorded.</p>;
  }
  return (
    <pre className="max-h-[32rem] overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}

function PreviewTable({ value, empty }: { value: unknown; empty: string }) {
  if (!Array.isArray(value) || value.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  const rows = value.filter((row): row is Record<string, unknown> => typeof row === "object" && row !== null && !Array.isArray(row));
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))].slice(0, 10);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            {columns.map((column) => <th key={column} className="py-2 pr-4">{column}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((row, index) => (
            <tr key={index} className="border-b last:border-0">
              {columns.map((column) => (
                <td key={column} className="max-w-80 truncate py-2 pr-4 align-top font-mono text-xs">
                  {formatRunCardValue(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunCardStat({ label, value, tone = "normal" }: { label: string; value: string; tone?: "normal" | "warning" }) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("mt-1 truncate text-sm font-medium", tone === "warning" ? "text-amber-700 dark:text-amber-300" : "")}>{value}</div>
    </div>
  );
}

function RunCardPanel({ title, icon: Icon, children }: { title: string; icon: typeof FileCheck2; children: ReactNode }) {
  return (
    <section className="rounded-md border bg-card p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium">
        <Icon className="h-4 w-4 text-muted-foreground" />
        {title}
      </div>
      {children}
    </section>
  );
}

function KeyValueTable({ data, empty, monospaceValues = false }: { data: Record<string, unknown>; empty: string; monospaceValues?: boolean }) {
  const entries = Object.entries(data).filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <table className="w-full table-fixed text-sm">
      <tbody>
        {entries.map(([key, value]) => (
          <tr key={key} className="border-b last:border-0">
            <td className="w-36 py-2 pr-4 align-top text-muted-foreground">{key}</td>
            <td className={cn("py-2 align-top", monospaceValues ? "break-all font-mono text-xs" : "break-words text-right tabular-nums")}>{formatRunCardValue(value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function formatRunCardValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return String(value ?? "");
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value)) return "-";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function toFiniteNumber(value: unknown): number {
  const numeric = typeof value === "number" ? value : Number(value || 0);
  return Number.isFinite(numeric) ? Math.max(0, numeric) : 0;
}

function formatTokenCount(value: unknown): string {
  return Math.round(toFiniteNumber(value)).toLocaleString();
}

function shortHash(value: string): string {
  return value.length > 16 ? `${value.slice(0, 12)}...${value.slice(-6)}` : value;
}

function ChartTab({
  run,
  selectedSymbol,
  chartPickerSymbol,
  selectedSymbols,
  chartCache,
  loadingSymbols,
  bulkLoading,
  bulkProgress,
  onPickSymbol,
  onAddSymbol,
  onCurrentOnly,
  onRemoveSymbol,
  onLoadAll,
  onCancelLoadAll,
}: {
  run: RunData;
  selectedSymbol: string;
  chartPickerSymbol: string;
  selectedSymbols: string[];
  chartCache: ChartCache;
  loadingSymbols: Record<string, boolean>;
  bulkLoading: boolean;
  bulkProgress: ChartLoadProgress;
  onPickSymbol: (symbol: string) => void;
  onAddSymbol: (symbol: string) => void;
  onCurrentOnly: (symbol: string) => void;
  onRemoveSymbol: (symbol: string) => void;
  onLoadAll: () => void;
  onCancelLoadAll: () => void;
}) {
  const [visibleChartCount, setVisibleChartCount] = useState(MULTI_CHART_PAGE_SIZE);
  const chartSymbols = run.chart_symbols || [];
  const activeSymbols = selectedSymbols.length ? selectedSymbols : selectedSymbol ? [selectedSymbol] : [];
  const entries = activeSymbols.flatMap((symbol) => {
    const payload = chartCache[symbol];
    const bars = payload?.price_series?.[symbol];
    return bars?.length ? [{ symbol, bars, payload }] : [];
  });
  const visibleEntries = entries.slice(0, visibleChartCount);
  const loadingSelectedSymbols = activeSymbols.filter((symbol) => loadingSymbols[symbol] && !chartCache[symbol]?.price_series?.[symbol]?.length);
  const hasEquity = run.equity_curve && run.equity_curve.length > 0;
  const progressPct = bulkProgress.total > 0 ? Math.round((bulkProgress.done / bulkProgress.total) * 100) : 0;
  const pickerValue = chartPickerSymbol || selectedSymbol || chartSymbols[0] || "";

  useEffect(() => {
    setVisibleChartCount(selectedSymbols.length > 1 ? MULTI_CHART_PAGE_SIZE : 1);
  }, [selectedSymbols.join("|")]);

  if (entries.length === 0 && loadingSelectedSymbols.length === 0 && !hasEquity) {
    return (
      <div className="p-8 text-center text-muted-foreground space-y-2">
        <p className="text-sm">No chart data available</p>
        <p className="text-xs">The backtest engine may not have generated price data. Check the artifacts/ directory.</p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {chartSymbols.length > 1 && (
        <div className="space-y-3 rounded-md border bg-card p-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs font-medium uppercase text-muted-foreground">Chart symbols</label>
            <select
              value={pickerValue}
              onChange={(event) => onPickSymbol(event.target.value)}
              disabled={bulkLoading}
              className="rounded-md border bg-background px-2 py-1 text-sm outline-none transition focus:border-primary disabled:opacity-60"
            >
              {chartSymbols.map((symbol) => (
                <option key={symbol} value={symbol}>{symbol}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => onAddSymbol(pickerValue)}
              disabled={!pickerValue || bulkLoading || !!loadingSymbols[pickerValue]}
              className="rounded-md border px-2.5 py-1 text-xs font-medium transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              Add
            </button>
            <button
              type="button"
              onClick={() => onCurrentOnly(pickerValue)}
              disabled={!pickerValue || bulkLoading || !!loadingSymbols[pickerValue]}
              className="rounded-md border px-2.5 py-1 text-xs font-medium transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              Current only
            </button>
            <button
              type="button"
              onClick={onLoadAll}
              disabled={bulkLoading || chartSymbols.length === 0}
              className="rounded-md border px-2.5 py-1 text-xs font-medium transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              Load all
            </button>
            {bulkLoading && (
              <button
                type="button"
                onClick={onCancelLoadAll}
                className="rounded-md border border-amber-500/30 px-2.5 py-1 text-xs font-medium text-amber-700 transition hover:bg-amber-500/10 dark:text-amber-300"
              >
                Cancel
              </button>
            )}
            {loadingSymbols[pickerValue] && (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading {pickerValue}
              </span>
            )}
            <span className="ml-auto text-xs text-muted-foreground">
              {activeSymbols.length} selected / {chartSymbols.length} available; charts load progressively.
            </span>
          </div>

          {bulkProgress.total > 0 && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{bulkLoading ? "Loading charts" : "Chart load progress"}</span>
                <span>{bulkProgress.done} / {bulkProgress.total} ({progressPct}%)</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-primary transition-[width]" style={{ width: `${progressPct}%` }} />
              </div>
            </div>
          )}

          {activeSymbols.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {activeSymbols.slice(0, 48).map((symbol) => (
                <button
                  key={symbol}
                  type="button"
                  onClick={() => onRemoveSymbol(symbol)}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs transition hover:bg-muted",
                    symbol === selectedSymbol ? "border-primary/50 text-primary" : "text-muted-foreground"
                  )}
                  title={`Remove ${symbol}`}
                >
                  {loadingSymbols[symbol] && <Loader2 className="h-3 w-3 animate-spin" />}
                  {symbol}
                  <span aria-hidden="true">x</span>
                </button>
              ))}
              {activeSymbols.length > 48 && (
                <span className="rounded-md border px-2 py-1 text-xs text-muted-foreground">
                  +{activeSymbols.length - 48} more selected
                </span>
              )}
            </div>
          )}
        </div>
      )}
      {loadingSelectedSymbols.map((symbol) => (
        <div key={`loading-${symbol}`} className="rounded-md border bg-card p-4 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading {symbol}
          </span>
        </div>
      ))}
      {visibleEntries.map(({ symbol, bars, payload }) => (
        <div key={symbol}>
          <h3 className="text-sm font-medium mb-1">{symbol}</h3>
          <CandlestickChart data={bars} markers={limitedMarkers(payload.trade_markers?.filter(m => !m.code || m.code === symbol))} indicators={payload.indicator_series?.[symbol]} height={500} />
        </div>
      ))}
      {entries.length > visibleEntries.length && (
        <div className="rounded-md border bg-card p-3 text-center">
          <button
            type="button"
            onClick={() => setVisibleChartCount((count) => Math.min(entries.length, count + MULTI_CHART_PAGE_SIZE))}
            className="rounded-md border px-3 py-1.5 text-sm font-medium transition hover:bg-muted"
          >
            Show {Math.min(MULTI_CHART_PAGE_SIZE, entries.length - visibleEntries.length)} more charts
          </button>
          <p className="mt-2 text-xs text-muted-foreground">
            Showing {visibleEntries.length} of {entries.length} loaded charts to keep the page responsive.
          </p>
        </div>
      )}
      {hasEquity && (
        <div>
          <h3 className="text-sm font-medium mb-1">Equity & Drawdown</h3>
          <EquityChart data={run.equity_curve!} height={280} />
        </div>
      )}
    </div>
  );
}

function limitedMarkers(markers: RunData["trade_markers"]): RunData["trade_markers"] {
  if (!markers || markers.length <= 1000) return markers;
  return markers.slice(-1000);
}

function TradesTab({ run }: { run: RunData }) {
  const trades = run.trade_log || [];
  if (trades.length === 0) return <div className="p-8 text-muted-foreground text-sm">No trades recorded.</div>;
  return (
    <div className="p-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2 pr-4">Time</th>
            <th className="py-2 pr-4">Code</th>
            <th className="py-2 pr-4">Side</th>
            <th className="py-2 pr-4">Price</th>
            <th className="py-2 pr-4">Qty</th>
            <th className="py-2">Reason</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((tr, i) => (
            <tr key={i} className="border-b last:border-0 hover:bg-muted/20">
              <td className="py-2 pr-4 font-mono text-xs">{tr.time || tr.timestamp}</td>
              <td className="py-2 pr-4">{tr.code}</td>
              <td className={cn("py-2 pr-4 font-medium", tr.side === "BUY" ? "text-success" : "text-danger")}>{tr.side}</td>
              <td className="py-2 pr-4 tabular-nums">{tr.price}</td>
              <td className="py-2 pr-4 tabular-nums">{tr.qty}</td>
              <td className="py-2 text-muted-foreground">{tr.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CodeTab({ code }: { code: Record<string, string> }) {
  const files = Object.entries(code);
  const [active, setActive] = useState(files[0]?.[0] || "");
  if (files.length === 0) return <div className="p-8 text-muted-foreground text-sm">No code files.</div>;
  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-1 p-2 border-b">
        {files.map(([name]) => (
          <button key={name} onClick={() => setActive(name)} className={cn("px-3 py-1 rounded text-xs font-mono", active === name ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>{name}</button>
        ))}
      </div>
      <div className="flex-1 overflow-auto p-3 text-[11px] leading-relaxed bg-muted/20 [&_pre]:m-0 [&_pre]:bg-transparent [&_code]:text-[11px]">
        <ReactMarkdown rehypePlugins={rehypePlugins}>
          {`\`\`\`python\n${code[active] || ""}\n\`\`\``}
        </ReactMarkdown>
      </div>
    </div>
  );
}
