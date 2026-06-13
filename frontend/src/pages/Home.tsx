import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock3,
  Database,
  FileCheck2,
  FileText,
  Gauge,
  GitCompare,
  Loader2,
  PlayCircle,
  ShieldCheck,
  UserCircle2,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { api, type RunData, type RunListItem } from "@/lib/api";
import { formatMetricVal } from "@/lib/formatters";
import { isReportWorthyRun } from "@/lib/runReports";
import { cn } from "@/lib/utils";

const RECENT_RUN_LIMIT = 6;
const MOIRIX_RECENT_SCAN_LIMIT = 12;
const MOIRIX_RECENT_SHOW_LIMIT = 4;

export function Home() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runDetails, setRunDetails] = useState<Record<string, RunData | null>>({});
  const [moirixRuns, setMoirixRuns] = useState<MoirixRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const FEATURES = [
    { icon: Bot, title: "AI Agent", desc: "Natural language strategy generation with ReAct reasoning" },
    { icon: BarChart3, title: "Built-in Backtest", desc: "7 data sources across A-shares, US/HK & Crypto" },
    { icon: Zap, title: "Real-time Streaming", desc: "Watch agent output, tool calls, and run status stream live" },
    { icon: UserCircle2, title: "Strategy Replay", desc: "Trade journal analyzer + Shadow Account - extract your rules, backtest them, attribute PnL delta" },
  ];

  useEffect(() => {
    let cancelled = false;

    async function loadRecentRuns() {
      setLoading(true);
      setError(null);
      try {
        const items = await api.listRuns();
        if (cancelled) return;

        const allRuns = Array.isArray(items) ? items : [];
        const displayedRuns = allRuns.slice(0, RECENT_RUN_LIMIT);
        const scannedRuns = allRuns.slice(0, MOIRIX_RECENT_SCAN_LIMIT);
        setRuns(displayedRuns);

        const detailResults = await Promise.allSettled(
          scannedRuns.map(async (run) => [run, await api.getRun(run.run_id)] as const),
        );
        if (cancelled) return;

        const nextDetails: Record<string, RunData | null> = {};
        const moirixSummaries: MoirixRunSummary[] = [];
        for (const result of detailResults) {
          if (result.status !== "fulfilled") continue;
          const [run, detail] = result.value;
          if (displayedRuns.some((item) => item.run_id === run.run_id)) {
            nextDetails[run.run_id] = detail;
          }
          const moirixSummary = toMoirixRunSummary(run, detail);
          if (moirixSummary && moirixSummaries.length < MOIRIX_RECENT_SHOW_LIMIT) {
            moirixSummaries.push(moirixSummary);
          }
        }
        for (const run of displayedRuns) {
          nextDetails[run.run_id] ??= null;
        }
        setRunDetails(nextDetails);
        setMoirixRuns(moirixSummaries);
      } catch (err) {
        if (!cancelled) {
          setRuns([]);
          setRunDetails({});
          setMoirixRuns([]);
          setError(err instanceof Error ? err.message : "Unable to load recent runs.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadRecentRuns();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen p-6 lg:p-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <section className="flex flex-col gap-5 border-b pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl space-y-3">
            <div className="inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium text-muted-foreground">
              <BarChart3 className="h-3.5 w-3.5" />
              Research Workbench
            </div>
            <h1 className="text-3xl font-bold tracking-tight">AI-Powered Quant Strategy Research</h1>
            <p className="text-muted-foreground">
              Describe a trading strategy, run a backtest, then come back here to review recent results and open run artifacts.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              to="/agent"
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90"
            >
              <PlayCircle className="h-4 w-4" />
              Start Research
            </Link>
            <Link
              to="/compare"
              className="inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition hover:bg-muted"
            >
              <GitCompare className="h-4 w-4" />
              Compare Runs
            </Link>
            <Link
              to="/reports"
              className="inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition hover:bg-muted"
            >
              <FileText className="h-4 w-4" />
              Report Library
            </Link>
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Recent Runs</h2>
              <p className="text-sm text-muted-foreground">Latest backtests and agent-generated research artifacts.</p>
            </div>
            {loading && (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading
              </span>
            )}
          </div>

          {error ? (
            <div className="rounded-md border border-danger/30 bg-danger/5 p-4 text-sm">
              <p className="font-medium text-danger">Run library unavailable</p>
              <p className="mt-1 text-muted-foreground">{error}</p>
            </div>
          ) : null}

          {!loading && !error && runs.length === 0 ? (
            <div className="rounded-md border border-dashed p-8 text-center">
              <FileText className="mx-auto h-8 w-8 text-muted-foreground" />
              <h3 className="mt-3 font-medium">No runs yet</h3>
              <p className="mt-1 text-sm text-muted-foreground">Create a run from Agent, then return here to review its artifacts.</p>
              <Link
                to="/agent"
                className="mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90"
              >
                Open Agent <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          ) : null}

          {runs.length > 0 ? (
            <div className="grid gap-3">
              {runs.map((run) => (
                <RunLibraryItem key={run.run_id} run={run} detail={runDetails[run.run_id]} />
              ))}
            </div>
          ) : null}
        </section>

        <MoirixResearchSection runs={moirixRuns} loading={loading} error={error} />

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="rounded-md border p-4">
              <Icon className="h-5 w-5 text-primary" />
              <h3 className="mt-3 font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{desc}</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

interface RunLibraryItemProps {
  run: RunListItem;
  detail: RunData | null | undefined;
}

function RunLibraryItem({ run, detail }: RunLibraryItemProps) {
  const reportWorthy = isReportWorthyRun(detail);
  const artifactBadges = getArtifactBadges(detail, run, reportWorthy);
  const codes = run.codes?.filter(Boolean).slice(0, 3) || [];

  return (
    <article className="rounded-md border p-4 transition hover:border-primary/40 hover:bg-muted/30">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={run.status} />
            <Link to={`/runs/${run.run_id}`} className="truncate font-mono text-sm font-medium hover:text-primary">
              {run.run_id}
            </Link>
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Clock3 className="h-3 w-3" />
              {formatRunDate(run.created_at)}
            </span>
            {detail?.elapsed_seconds !== undefined ? (
              <span className="text-xs text-muted-foreground">{formatElapsed(detail.elapsed_seconds)}</span>
            ) : null}
          </div>

          <p className="line-clamp-2 text-sm text-muted-foreground">
            {run.prompt?.trim() || "No prompt recorded for this run."}
          </p>

          <div className="flex flex-wrap gap-1.5">
            {codes.map((code) => (
              <span key={code} className="rounded border px-2 py-0.5 font-mono text-xs text-muted-foreground">
                {code}
              </span>
            ))}
            {run.start_date || run.end_date ? (
              <span className="rounded border px-2 py-0.5 text-xs text-muted-foreground">
                {run.start_date || "?"} to {run.end_date || "?"}
              </span>
            ) : null}
            {artifactBadges.map((badge) => (
              <span key={badge} className="rounded bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                {badge}
              </span>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-3 lg:items-end">
          <div className="grid grid-cols-2 gap-2 text-right sm:flex sm:flex-wrap sm:justify-end">
            <MetricPill label="Return" value={formatOptionalMetric("total_return", run.total_return ?? detail?.metrics?.total_return)} />
            <MetricPill label="Sharpe" value={formatOptionalMetric("sharpe", run.sharpe ?? detail?.metrics?.sharpe)} />
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <Link
              to={`/runs/${run.run_id}`}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition hover:opacity-90"
            >
              View Detail <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <Link
              to="/compare"
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition hover:bg-muted"
            >
              <GitCompare className="h-3.5 w-3.5" />
              Compare
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}

interface MoirixResearchSectionProps {
  runs: MoirixRunSummary[];
  loading: boolean;
  error: string | null;
}

function MoirixResearchSection({ runs, loading, error }: MoirixResearchSectionProps) {
  return (
    <section className="rounded-md border p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded-md bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
            <Database className="h-3.5 w-3.5" />
            Kenny fork
          </div>
          <h2 className="mt-3 text-lg font-semibold">Moirix Event Thesis</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Recent PIT evidence, Agent-synthesized event theses, portfolio decision context, and authority artifacts from optional local Moirix runs.
          </p>
        </div>
        {loading && (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Loading
          </span>
        )}
      </div>

      {error ? (
        <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-muted-foreground">
          Moirix dashboard unavailable: {error}
        </div>
      ) : null}

      {!loading && !error && runs.length === 0 ? (
        <div className="mt-4 rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          No Moirix event thesis or position decision artifacts found in recent runs. Ordinary Vibe workflows are unaffected.
        </div>
      ) : null}

      {runs.length > 0 ? (
        <div className="mt-4 grid gap-3">
          {runs.map((run) => (
            <MoirixRunCard key={run.runId} run={run} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

interface MoirixRunSummary {
  runId: string;
  prompt?: string;
  createdAt: string;
  status: string;
  statusTone: PillTone;
  evidence: string;
  thesis: string;
  decision: string;
  position: string;
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
          <Link to={`/runs/${run.runId}?tab=moirixThesis`} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted">
            Thesis
          </Link>
          <Link to={`/runs/${run.runId}?tab=moirixDecision`} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted">
            Context
          </Link>
          <Link to={`/runs/${run.runId}?tab=moirixPosition`} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted">
            Position
          </Link>
          <Link to={`/runs/${run.runId}?tab=moirixAuthority`} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted">
            Authority
          </Link>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MoirixStatusTile icon={Database} label="Evidence" value={run.evidence} />
        <MoirixStatusTile icon={FileCheck2} label="Thesis" value={run.thesis} />
        <MoirixStatusTile icon={BarChart3} label="Decision Context" value={run.decision} />
        <MoirixStatusTile icon={Gauge} label="Position Decision" value={run.position} />
        <MoirixStatusTile
          icon={ShieldCheck}
          label="Authority"
          value={run.authorityFalse ? `${run.authority} · real-money=false` : run.authority}
        />
      </div>
    </article>
  );
}

function MoirixStatusTile({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
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

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const ok = ["success", "done", "completed", "complete"].includes(normalized);
  const running = ["running", "pending", "queued"].includes(normalized);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium",
        ok && "bg-success/10 text-success",
        running && "bg-amber-500/10 text-amber-700 dark:text-amber-300",
        !ok && !running && "bg-muted text-muted-foreground",
      )}
    >
      {ok ? <CheckCircle2 className="h-3 w-3" /> : null}
      {status || "unknown"}
    </span>
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

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border px-3 py-1.5">
      <div className="text-[11px] uppercase text-muted-foreground">{label}</div>
      <div className="font-mono text-sm font-medium">{value}</div>
    </div>
  );
}

function toMoirixRunSummary(run: RunListItem, detail: RunData): MoirixRunSummary | null {
  if (!hasMoirixArtifacts(detail)) return null;
  const artifacts = asRecord(detail.moirix_artifacts);
  if (
    !artifacts?.event_thesis_graph
    && !artifacts?.event_decision_context
    && !artifacts?.event_thesis_report_markdown
    && !artifacts?.position_decision
  ) return null;
  const status = statusLabel(artifacts?.status) || inferMoirixStatus(detail);
  const statusTone = toneForStatus(status);
  const coverage = asRecord(artifacts?.coverage_status);
  const thesis = asRecord(artifacts?.event_thesis_graph);
  const decisionContext = asRecord(artifacts?.event_decision_context);
  const positionDecision = asRecord(artifacts?.position_decision);
  const tradeProposal = asRecord(artifacts?.trade_proposal);
  const executionStatus = asRecord(artifacts?.execution_status);
  const authority = asRecord(artifacts?.authority_status) || asRecord(artifacts?.moirix_authority_status);
  const authorityReady = hasReadyForRealMoneyFalse(
    artifacts?.status,
    artifacts?.coverage_status,
    artifacts?.event_thesis_graph,
    artifacts?.event_decision_context,
    artifacts?.position_decision,
    artifacts?.trade_proposal,
    artifacts?.execution_status,
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
    thesis: summarizeThesis(thesis),
    decision: summarizeDecisionContext(decisionContext),
    position: summarizePositionDecision(positionDecision, tradeProposal, executionStatus),
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

function summarizeThesis(thesis: Record<string, unknown> | null): string {
  const current = asRecord(thesis?.current_thesis);
  const stance = firstString(current, ["stance"]);
  const actionability = firstString(current, ["actionability"]);
  if (stance && actionability) return `${stance} · ${actionability}`;
  if (stance || actionability) return stance || actionability;
  if (thesis) return "thesis recorded";
  return "not recorded";
}

function summarizeDecisionContext(context: Record<string, unknown> | null): string {
  const counts = asRecord(context?.position_counts);
  const status = statusLabel(context);
  if (counts) {
    const positions = Number(counts.positions ?? 0);
    const orders = Number(counts.open_orders ?? 0);
    if (Number.isFinite(positions) || Number.isFinite(orders)) {
      return `${Number.isFinite(positions) ? positions : 0} positions · ${Number.isFinite(orders) ? orders : 0} orders`;
    }
  }
  return status || (context ? "context recorded" : "not recorded");
}

function summarizePositionDecision(
  decision: Record<string, unknown> | null,
  proposal: Record<string, unknown> | null,
  execution: Record<string, unknown> | null,
): string {
  const action = firstString(decision, ["action"]);
  const status = statusLabel(decision);
  const orders = Array.isArray(proposal?.orders) ? proposal.orders.length : 0;
  const executionStatus = statusLabel(execution);
  if (action && orders > 0) return `${action} · ${orders} proposed`;
  if (action) return executionStatus ? `${action} · ${executionStatus}` : action;
  return status || (decision ? "decision recorded" : "not recorded");
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

function formatOptionalMetric(key: string, value: number | undefined): string {
  return Number.isFinite(value) ? formatMetricVal(key, value as number) : "-";
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

function formatElapsed(seconds: number): string {
  if (!Number.isFinite(seconds)) return "";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function getArtifactBadges(detail: RunData | null | undefined, run: RunListItem, reportWorthy: boolean): string[] {
  const badges = new Set<string>();
  if (reportWorthy) badges.add("Report");
  if (run.total_return !== undefined || run.sharpe !== undefined || detail?.metrics) badges.add("Metrics");
  if (detail?.equity_curve?.length) badges.add("Equity");
  if (detail?.trade_log?.length || detail?.trade_markers?.length) badges.add("Trades");
  if (detail?.validation) badges.add("Validation");
  if (detail?.run_card) badges.add("Run Card");

  for (const artifact of detail?.artifacts || []) {
    const name = artifact.name.toLowerCase();
    if (name.includes("equity")) badges.add("Equity");
    if (name.includes("trade")) badges.add("Trades");
    if (name.includes("metric")) badges.add("Metrics");
    if (name.includes("validation")) badges.add("Validation");
    if (name.includes("strategy")) badges.add("Strategy");
  }

  return Array.from(badges).slice(0, 4);
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
