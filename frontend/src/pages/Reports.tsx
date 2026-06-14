import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  GitCompare,
  Loader2,
  RefreshCw,
  Search,
  XCircle,
} from "lucide-react";
import { api, type RunListItem } from "@/lib/api";
import { formatMetricVal } from "@/lib/formatters";
import { cn } from "@/lib/utils";

const REPORT_SCAN_LIMIT = 100;
type ReportSortKey = "created_desc" | "created_asc" | "return_desc" | "sharpe_desc" | "status_asc" | "run_id_desc";

export function Reports() {
  const { t } = useTranslation();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<ReportSortKey>("created_desc");
  const [error, setError] = useState<string | null>(null);

  async function loadReports(mode: "initial" | "refresh" = "refresh") {
    if (mode === "initial") setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const list = await api.listRuns({ limit: REPORT_SCAN_LIMIT, with_usage: true });
      setRuns(Array.isArray(list) ? list : []);
    } catch (err) {
      setRuns([]);
      setError(err instanceof Error ? err.message : t("reports.loadError"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadReports("initial");
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filteredRuns = needle ? runs.filter((run) => {
      const haystack = [
        run.run_id,
        run.status,
        run.prompt,
        ...(run.codes || []),
        run.start_date,
        run.end_date,
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(needle);
    }) : runs;
    return [...filteredRuns].sort((a, b) => compareReports(a, b, sortKey));
  }, [runs, query, sortKey]);
  const sortOptions: { value: ReportSortKey; label: string }[] = [
    { value: "created_desc", label: t("reports.sortNewest") },
    { value: "created_asc", label: t("reports.sortOldest") },
    { value: "return_desc", label: t("reports.sortBestReturn") },
    { value: "sharpe_desc", label: t("reports.sortBestSharpe") },
    { value: "status_asc", label: t("reports.sortStatus") },
    { value: "run_id_desc", label: t("reports.sortRunId") },
  ];

  return (
    <div className="min-h-screen p-6 lg:p-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <section className="flex flex-col gap-4 border-b pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium text-muted-foreground">
              <FileText className="h-3.5 w-3.5" />
              {t("reports.badge")}
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight">{t("reports.title")}</h1>
              <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
                {t("reports.subtitle")}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => loadReports("refresh")}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition hover:bg-muted disabled:opacity-50"
          >
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {t("reports.refresh")}
          </button>
        </section>

        <section className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <label className="relative block md:w-96">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("reports.searchPlaceholder")}
              className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm outline-none transition focus:border-primary"
            />
          </label>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between xl:justify-end">
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">{t("reports.sortLabel")}</span>
              <select
                value={sortKey}
                onChange={(event) => setSortKey(event.target.value as ReportSortKey)}
                className="rounded-md border bg-background px-2 py-1.5 text-sm outline-none transition focus:border-primary"
                aria-label={t("reports.sortAria")}
              >
                {sortOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <div className="text-sm text-muted-foreground">
              {t("reports.count", { shown: filtered.length, total: runs.length })}
            </div>
          </div>
        </section>

        {loading ? (
          <div className="grid gap-3">
            {[1, 2, 3, 4].map((item) => (
              <div key={item} className="h-28 animate-pulse rounded-md border bg-muted/40" />
            ))}
          </div>
        ) : null}

        {!loading && error ? (
          <section className="rounded-md border border-amber-500/30 bg-amber-500/5 p-5">
            <div className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
              <AlertTriangle className="h-5 w-5" />
              {t("reports.unavailableTitle")}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{error}</p>
          </section>
        ) : null}

        {!loading && !error && filtered.length === 0 ? (
          <section className="rounded-md border border-dashed p-8 text-center">
            <FileText className="mx-auto h-8 w-8 text-muted-foreground" />
            <h2 className="mt-3 font-medium">{runs.length === 0 ? t("reports.emptyTitle") : t("reports.noMatchesTitle")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {runs.length === 0 ? t("reports.emptyBody") : t("reports.noMatchesBody")}
            </p>
          </section>
        ) : null}

        {!loading && !error && filtered.length > 0 ? (
          <section className="grid gap-3">
            {filtered.map((run) => (
              <ReportRow key={run.run_id} run={run} />
            ))}
          </section>
        ) : null}
      </div>
    </div>
  );
}

function ReportRow({ run }: { run: RunListItem }) {
  const { t } = useTranslation();
  const hasUsage = Boolean(run.llm_usage);
  return (
    <article className="rounded-md border p-4 transition hover:border-primary/40 hover:bg-muted/30">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={run.status} />
            <Link to={`/runs/${run.run_id}`} className="truncate font-mono text-sm font-medium hover:text-primary">
              {run.run_id}
            </Link>
            <span className="text-xs text-muted-foreground">{formatRunDate(run.created_at)}</span>
            {hasUsage ? <span className="rounded bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">{t("reports.usageBadge")}</span> : null}
          </div>
          <p className="line-clamp-2 text-sm text-muted-foreground">{run.prompt || t("reports.noPrompt")}</p>
          <div className="flex flex-wrap gap-1.5">
            {(run.codes || []).slice(0, 6).map((code) => (
              <span key={code} className="rounded border px-2 py-0.5 font-mono text-xs text-muted-foreground">
                {code}
              </span>
            ))}
            {run.start_date || run.end_date ? (
              <span className="rounded border px-2 py-0.5 text-xs text-muted-foreground">
                {t("reports.dateRange", { start: run.start_date || "?", end: run.end_date || "?" })}
              </span>
            ) : null}
          </div>
        </div>

        <div className="flex flex-col gap-3 lg:items-end">
          <div className="grid grid-cols-2 gap-2 text-right sm:flex sm:flex-wrap sm:justify-end">
            <MetricPill label={t("reports.return")} value={formatOptionalMetric("total_return", run.total_return)} />
            <MetricPill label={t("reports.sharpe")} value={formatOptionalMetric("sharpe", run.sharpe)} />
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <Link
              to={`/runs/${run.run_id}`}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition hover:opacity-90"
            >
              {t("reports.fullReport")} <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <Link
              to="/compare"
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition hover:bg-muted"
            >
              <GitCompare className="h-3.5 w-3.5" />
              {t("reports.compare")}
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const normalized = status.toLowerCase();
  const ok = ["success", "done", "completed", "complete"].includes(normalized);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium",
        ok ? "bg-success/10 text-success" : "bg-muted text-muted-foreground",
      )}
    >
      {ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {status || t("reports.unknown")}
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

function compareReports(a: RunListItem, b: RunListItem, sortKey: ReportSortKey): number {
  switch (sortKey) {
    case "created_asc":
      return compareNumbers(parseReportTime(a), parseReportTime(b), "asc") || compareStrings(a.run_id, b.run_id, "asc");
    case "return_desc":
      return compareNumbers(metricValue(a.total_return), metricValue(b.total_return), "desc") || compareReports(a, b, "created_desc");
    case "sharpe_desc":
      return compareNumbers(metricValue(a.sharpe), metricValue(b.sharpe), "desc") || compareReports(a, b, "created_desc");
    case "status_asc":
      return compareStrings(a.status, b.status, "asc") || compareReports(a, b, "created_desc");
    case "run_id_desc":
      return compareStrings(a.run_id, b.run_id, "desc");
    case "created_desc":
    default:
      return compareNumbers(parseReportTime(a), parseReportTime(b), "desc") || compareStrings(a.run_id, b.run_id, "desc");
  }
}

function parseReportTime(run: RunListItem): number {
  const created = run.created_at || "";
  const normalized = created.includes("T") ? created : created.replace(" ", "T");
  const parsed = Date.parse(normalized);
  if (Number.isFinite(parsed)) return parsed;
  const match = run.run_id.match(/^(\d{8})_(\d{6})/);
  if (!match) return 0;
  const [, date, time] = match;
  return Date.parse(`${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}T${time.slice(0, 2)}:${time.slice(2, 4)}:${time.slice(4, 6)}`) || 0;
}

function metricValue(value: number | undefined): number {
  return Number.isFinite(value) ? value as number : Number.NEGATIVE_INFINITY;
}

function compareNumbers(a: number, b: number, direction: "asc" | "desc"): number {
  return direction === "asc" ? a - b : b - a;
}

function compareStrings(a: string | undefined, b: string | undefined, direction: "asc" | "desc"): number {
  const result = String(a || "").localeCompare(String(b || ""));
  return direction === "asc" ? result : -result;
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
