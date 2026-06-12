import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  BarChart3,
  Database,
  FileCheck2,
  Loader2,
  ShieldCheck,
  Zap,
  UserCircle2,
} from "lucide-react";
import { api, type RunData, type RunListItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const MOIRIX_RECENT_SCAN_LIMIT = 12;
const MOIRIX_RECENT_SHOW_LIMIT = 4;

export function Home() {
  const [moirixRuns, setMoirixRuns] = useState<MoirixRunSummary[]>([]);
  const [moirixLoading, setMoirixLoading] = useState(true);
  const [moirixError, setMoirixError] = useState<string | null>(null);

  const FEATURES = [
    { icon: Bot, title: "AI Agent", desc: "Natural language strategy generation with ReAct reasoning" },
    { icon: BarChart3, title: "Built-in Backtest", desc: "7 data sources across A-shares, US/HK & Crypto" },
    { icon: Zap, title: "Real-time Streaming", desc: "Watch the agent think, call tools, and iterate" },
    { icon: UserCircle2, title: "Strategy Replay", desc: "Trade journal analyzer + Shadow Account — extract your rules, backtest them, attribute PnL delta" },
  ];

  useEffect(() => {
    let cancelled = false;

    async function loadMoirixRuns() {
      setMoirixLoading(true);
      setMoirixError(null);
      try {
        const runs = await api.listRuns();
        if (cancelled) return;
        const recent = Array.isArray(runs) ? runs.slice(0, MOIRIX_RECENT_SCAN_LIMIT) : [];
        const details = await Promise.allSettled(
          recent.map(async (run) => [run, await api.getRun(run.run_id)] as const),
        );
        if (cancelled) return;

        const summaries = details
          .flatMap((result) => result.status === "fulfilled" ? [toMoirixRunSummary(result.value[0], result.value[1])] : [])
          .filter((summary): summary is MoirixRunSummary => summary !== null)
          .slice(0, MOIRIX_RECENT_SHOW_LIMIT);
        setMoirixRuns(summaries);
      } catch (err) {
        if (!cancelled) {
          setMoirixRuns([]);
          setMoirixError(err instanceof Error ? err.message : "Unable to load Moirix runs.");
        }
      } finally {
        if (!cancelled) setMoirixLoading(false);
      }
    }

    loadMoirixRuns();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8">
      <div className="max-w-2xl text-center space-y-6">
        <h1 className="text-4xl font-bold tracking-tight">AI-Powered Quant Strategy Research</h1>
        <p className="text-lg text-muted-foreground">Describe a trading strategy in natural language. The agent generates code, runs backtests, and optimizes — all in real time.</p>
        <Link
          to="/agent"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90 transition"
        >
          Start Research <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mt-16 max-w-5xl w-full">
        {FEATURES.map(({ icon: Icon, title, desc }) => (
          <div key={title} className="border rounded-lg p-6 space-y-3">
            <Icon className="h-8 w-8 text-primary" />
            <h3 className="font-semibold">{title}</h3>
            <p className="text-sm text-muted-foreground">{desc}</p>
          </div>
        ))}
      </div>

      <section className="mt-12 w-full max-w-5xl rounded-md border p-5 text-left">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-md bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
              <Database className="h-3.5 w-3.5" />
              Kenny fork
            </div>
            <h2 className="mt-3 text-lg font-semibold">Moirix Research Evidence</h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Recent PIT news evidence, event-impact graph, event signal, and authority artifacts from optional local Moirix runs.
            </p>
          </div>
          {moirixLoading && (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading
            </span>
          )}
        </div>

        {moirixError ? (
          <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-muted-foreground">
            Moirix dashboard unavailable: {moirixError}
          </div>
        ) : null}

        {!moirixLoading && !moirixError && moirixRuns.length === 0 ? (
          <div className="mt-4 rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            No Moirix run artifacts found in recent runs. Ordinary Vibe workflows are unaffected.
          </div>
        ) : null}

        {moirixRuns.length > 0 ? (
          <div className="mt-4 grid gap-3">
            {moirixRuns.map((run) => (
              <MoirixRunCard key={run.runId} run={run} />
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}

interface MoirixRunSummary {
  runId: string;
  prompt?: string;
  createdAt: string;
  status: string;
  statusTone: PillTone;
  evidence: string;
  graph: string;
  signal: string;
  authority: string;
  authorityFalse: boolean;
  caveat?: string;
}

type PillTone = "success" | "warning" | "danger" | "neutral";

function MoirixRunCard({ run }: { run: MoirixRunSummary }) {
  return (
    <article className="rounded-md border bg-muted/20 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill label={run.status} tone={run.statusTone} />
            <Link to={`/runs/${run.runId}?tab=moirixEvidence`} className="truncate font-mono text-sm font-medium hover:text-primary">
              {run.runId}
            </Link>
            <span className="text-xs text-muted-foreground">{formatRunDate(run.createdAt)}</span>
          </div>
          {run.prompt && <p className="mt-2 text-sm text-muted-foreground">{run.prompt}</p>}
          {run.caveat && (
            <p className="mt-2 rounded-md border border-amber-500/20 bg-amber-500/5 px-2 py-1 text-xs text-amber-700 dark:text-amber-300">
              {run.caveat}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <Link to={`/runs/${run.runId}?tab=moirixEvidence`} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted">
            Evidence
          </Link>
          <Link to={`/runs/${run.runId}?tab=moirixGraph`} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted">
            Graph
          </Link>
          <Link to={`/runs/${run.runId}?tab=moirixAuthority`} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted">
            Authority
          </Link>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <MoirixStatusTile icon={Database} label="Evidence" value={run.evidence} />
        <MoirixStatusTile icon={BarChart3} label="Graph" value={run.graph} />
        <MoirixStatusTile icon={FileCheck2} label="Signal / Backtest" value={run.signal} />
        <MoirixStatusTile
          icon={ShieldCheck}
          label="Authority"
          value={run.authorityFalse ? `${run.authority} · real-money=false` : run.authority}
        />
      </div>
    </article>
  );
}

function MoirixStatusTile({ icon: Icon, label, value }: { icon: typeof Database; label: string; value: string }) {
  return (
    <div className="rounded-md border bg-background/70 p-3">
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-2 text-sm font-medium">{value}</div>
    </div>
  );
}

function StatusPill({ label, tone }: { label: string; tone: PillTone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium",
        tone === "success" && "bg-success/10 text-success",
        tone === "warning" && "bg-amber-500/10 text-amber-700 dark:text-amber-300",
        tone === "danger" && "bg-danger/10 text-danger",
        tone === "neutral" && "bg-muted text-muted-foreground",
      )}
    >
      {label}
    </span>
  );
}

function toMoirixRunSummary(run: RunListItem, detail: RunData): MoirixRunSummary | null {
  if (!hasMoirixArtifacts(detail)) return null;
  const artifacts = asRecord(detail.moirix_artifacts);
  const status = statusLabel(artifacts?.status) || inferMoirixStatus(detail);
  const statusTone = toneForStatus(status);
  const coverage = asRecord(artifacts?.coverage_status);
  const authority = asRecord(artifacts?.authority_status) || asRecord(artifacts?.moirix_authority_status);
  const authorityReady = hasReadyForRealMoneyFalse(
    artifacts?.status,
    artifacts?.coverage_status,
    artifacts?.authority_status,
    artifacts?.moirix_authority_status,
    artifacts?.vibe_run_card_patch,
  );

  return {
    runId: run.run_id,
    prompt: run.prompt,
    createdAt: run.created_at,
    status,
    statusTone,
    evidence: summarizeEvidence(artifacts, coverage),
    graph: artifacts?.event_impact_graph ? "graph artifact present" : status === "blocked" || status === "unavailable" ? status : "not recorded",
    signal: summarizeSignal(artifacts),
    authority: statusLabel(authority) || statusLabel(asRecord(artifacts?.vibe_run_card_patch)) || (authority || authorityReady ? "checked" : "not recorded"),
    authorityFalse: authorityReady,
    caveat: firstString(coverage, ["caveat", "warning", "confidence_caveat", "coverage_caveat"]) || firstString(artifacts, ["caveat", "warning"]),
  };
}

function hasMoirixArtifacts(run: RunData): boolean {
  if (run.moirix_artifacts && Object.keys(run.moirix_artifacts).length > 0) return true;
  return (run.artifacts || []).some((artifact) => artifact.name.startsWith("moirix/") || artifact.path.includes("/artifacts/moirix/"));
}

function summarizeEvidence(artifacts: Record<string, unknown> | null, coverage: Record<string, unknown> | null): string {
  const rows = countRows(artifacts?.news_evidence_preview);
  if (rows > 0) return `${rows} preview rows`;
  const coverageStatus = statusLabel(coverage);
  if (coverageStatus) return coverageStatus;
  return artifacts?.news_evidence_preview ? "preview available" : "not recorded";
}

function summarizeSignal(artifacts: Record<string, unknown> | null): string {
  const signalRows = countRows(artifacts?.event_signal_preview);
  const forwardRows = countRows(artifacts?.event_signal_forward_returns_preview);
  if (artifacts?.event_signal_backtest_summary) return "backtest summary present";
  if (signalRows || forwardRows) return `${signalRows || forwardRows} preview rows`;
  return "not recorded";
}

function inferMoirixStatus(run: RunData): string {
  const names = (run.artifacts || []).map((artifact) => `${artifact.name} ${artifact.path}`.toLowerCase());
  if (names.some((name) => name.includes("blocked"))) return "blocked";
  if (names.some((name) => name.includes("unavailable"))) return "unavailable";
  return "ok";
}

function toneForStatus(status: string): PillTone {
  const normalized = status.toLowerCase();
  if (normalized === "ok" || normalized === "success") return "success";
  if (normalized === "blocked" || normalized === "unavailable" || normalized === "error") return "danger";
  if (normalized === "partial" || normalized === "warning") return "warning";
  return "neutral";
}

function statusLabel(value: unknown): string {
  if (typeof value === "string") return value;
  const record = asRecord(value);
  return firstString(record, ["status", "state", "coverage_status"]) || "";
}

function countRows(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function firstString(record: Record<string, unknown> | null, keys: string[]): string {
  if (!record) return "";
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function hasReadyForRealMoneyFalse(...values: unknown[]): boolean {
  for (const value of values) {
    const record = asRecord(value);
    if (!record) continue;
    if (record.ready_for_real_money_trading_authority === false) return true;
    if (hasReadyForRealMoneyFalse(record.authority, record.claim_gate)) return true;
  }
  return false;
}

function formatRunDate(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value || "unknown";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
