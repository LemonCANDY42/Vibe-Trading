import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock3,
  FileText,
  GitCompare,
  Loader2,
  PlayCircle,
  UserCircle2,
  Zap,
} from "lucide-react";
import { api, type RunData, type RunListItem } from "@/lib/api";
import { formatMetricVal } from "@/lib/formatters";
import { isReportWorthyRun } from "@/lib/runReports";
import { cn } from "@/lib/utils";

const RECENT_RUN_LIMIT = 6;

export function Home() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runDetails, setRunDetails] = useState<Record<string, RunData | null>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const FEATURES = [
    { icon: Bot, title: "AI Agent", desc: "Natural language strategy generation with ReAct reasoning" },
    { icon: BarChart3, title: "Built-in Backtest", desc: "7 data sources across A-shares, US/HK & Crypto" },
    { icon: Zap, title: "Real-time Streaming", desc: "Watch the agent think, call tools, and iterate" },
    { icon: UserCircle2, title: "Strategy Replay", desc: "Trade journal analyzer + Shadow Account — extract your rules, backtest them, attribute PnL delta" },
  ];

  useEffect(() => {
    let cancelled = false;

    async function loadRecentRuns() {
      setLoading(true);
      setError(null);
      try {
        const items = await api.listRuns();
        if (cancelled) return;

        const recentRuns = Array.isArray(items) ? items.slice(0, RECENT_RUN_LIMIT) : [];
        setRuns(recentRuns);

        const detailResults = await Promise.allSettled(
          recentRuns.map(async (run) => [run.run_id, await api.getRun(run.run_id)] as const),
        );
        if (cancelled) return;

        const nextDetails: Record<string, RunData | null> = {};
        for (const result of detailResults) {
          if (result.status === "fulfilled") {
            const [runId, detail] = result.value;
            nextDetails[runId] = detail;
          }
        }
        for (const run of recentRuns) {
          nextDetails[run.run_id] ??= null;
        }
        setRunDetails(nextDetails);
      } catch (err) {
        if (!cancelled) {
          setRuns([]);
          setRunDetails({});
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

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border px-3 py-1.5">
      <div className="text-[11px] uppercase text-muted-foreground">{label}</div>
      <div className="font-mono text-sm font-medium">{value}</div>
    </div>
  );
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
