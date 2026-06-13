import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Home } from "../Home";
import type { RunData, RunListItem } from "@/lib/api";

const apiMock = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
}));

function renderHome() {
  return render(
    <MemoryRouter>
      <Home />
    </MemoryRouter>,
  );
}

function makeRun(overrides: Partial<RunListItem> = {}): RunListItem {
  return {
    run_id: "run-1",
    status: "success",
    created_at: "2025-01-02T03:04:05Z",
    prompt: "Backtest a simple moving average strategy",
    total_return: 0.1234,
    sharpe: 1.2,
    codes: ["AAPL.US", "MSFT.US"],
    start_date: "2024-01-01",
    end_date: "2024-06-30",
    ...overrides,
  };
}

function makeRunDetail(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "run-1",
    status: "success",
    metrics: {
      final_value: 1123400,
      total_return: 0.1234,
      annual_return: 0.251,
      max_drawdown: -0.08,
      sharpe: 1.2,
      win_rate: 0.58,
      trade_count: 12,
    },
    artifacts: [],
    ...overrides,
  };
}

function makeMoirixDetail(overrides: Partial<RunData> = {}): RunData {
  return makeRunDetail({
    run_id: "moirix_run",
    moirix_artifacts: {
      status: { status: "ok" },
      coverage_status: { status: "partial", caveat: "Low-confidence evidence coverage." },
      news_evidence_preview: [{ id: "n1" }, { id: "n2" }],
      event_thesis_graph: {
        current_thesis: {
          stance: "bullish",
          actionability: "watch",
        },
      },
      event_decision_context: {
        status: "ok",
        position_counts: { positions: 1, open_orders: 0, executions: 0 },
      },
      position_decision: {
        status: "ok",
        action: "add",
      },
      trade_proposal: {
        status: "proposed",
        orders: [{ symbol: "NVDA", side: "buy", quantity: 1 }],
        authority: {
          broker_submit_allowed: false,
          ready_for_real_money_trading_authority: false,
        },
      },
      execution_status: {
        status: "blocked",
      },
      authority_status: {
        status: "checked",
        authority: { ready_for_real_money_trading_authority: false },
      },
    },
    artifacts: [{ name: "moirix/status.json", path: "/runs/moirix/artifacts/moirix/status.json", type: "json", size: 12, exists: true }],
    ...overrides,
  });
}

describe("Home workbench", () => {
  beforeEach(() => {
    apiMock.listRuns.mockReset();
    apiMock.getRun.mockReset();
  });

  it("shows an empty run library state", async () => {
    apiMock.listRuns.mockResolvedValue([]);

    renderHome();

    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
    expect(screen.getByText("No Moirix event thesis or position decision artifacts found in recent runs. Ordinary Vibe workflows are unaffected.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Agent/i })).toHaveAttribute("href", "/agent");
    expect(apiMock.getRun).not.toHaveBeenCalled();
  });

  it("renders recent runs with detail and compare links", async () => {
    apiMock.listRuns.mockResolvedValue([makeRun()]);
    apiMock.getRun.mockResolvedValue(makeRunDetail({
      elapsed_seconds: 12.4,
      equity_curve: [{ time: "2024-01-02", equity: 1001000, drawdown: 0 }],
      trade_log: [{ date: "2024-01-02", action: "BUY" }],
      run_card: { schema_version: "1.0" },
    }));

    renderHome();

    expect(await screen.findByText("run-1")).toBeInTheDocument();
    expect(screen.getByText("Backtest a simple moving average strategy")).toBeInTheDocument();
    expect(screen.getByText("AAPL.US")).toBeInTheDocument();
    expect(screen.getByText("Report")).toBeInTheDocument();
    expect(screen.getByText("Equity")).toBeInTheDocument();
    expect(screen.getByText("Trades")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View Detail/i })).toHaveAttribute("href", "/runs/run-1");
    expect(screen.getAllByRole("link", { name: /Compare/i })[0]).toHaveAttribute("href", "/compare");
  });

  it("shows recent Moirix artifact runs and links to Run Detail Moirix tabs", async () => {
    apiMock.listRuns.mockResolvedValue([
      makeRun({ run_id: "moirix_run", prompt: "Run Moirix evidence workflow for NVDA" }),
      makeRun({ run_id: "ordinary_run", prompt: "Normal backtest" }),
    ]);
    apiMock.getRun.mockImplementation((runId: string) => {
      if (runId === "moirix_run") return Promise.resolve(makeMoirixDetail());
      return Promise.resolve(makeRunDetail({ run_id: runId }));
    });

    renderHome();

    expect(await screen.findByText("Moirix Event Thesis")).toBeInTheDocument();
    expect(screen.getAllByText("moirix_run")).toHaveLength(2);
    expect(screen.getByText("ordinary_run")).toBeInTheDocument();
    expect(screen.getByText("2 preview rows")).toBeInTheDocument();
    expect(screen.getByText("bullish · watch")).toBeInTheDocument();
    expect(screen.getByText("1 positions · 0 orders")).toBeInTheDocument();
    expect(screen.getByText("add · 1 proposed")).toBeInTheDocument();
    expect(screen.getByText(/real-money=false/)).toBeInTheDocument();
    expect(screen.getByText("Low-confidence evidence coverage.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Evidence" })).toHaveAttribute("href", "/runs/moirix_run?tab=moirixEvidence");
    expect(screen.getByRole("link", { name: "Thesis" })).toHaveAttribute("href", "/runs/moirix_run?tab=moirixThesis");
    expect(screen.getByRole("link", { name: "Context" })).toHaveAttribute("href", "/runs/moirix_run?tab=moirixDecision");
    expect(screen.getByRole("link", { name: "Position" })).toHaveAttribute("href", "/runs/moirix_run?tab=moirixPosition");
    expect(screen.getByRole("link", { name: "Authority" })).toHaveAttribute("href", "/runs/moirix_run?tab=moirixAuthority");
  });

  it("shows blocked Moirix decision context instead of zero positions", async () => {
    apiMock.listRuns.mockResolvedValue([
      makeRun({ run_id: "moirix_run", prompt: "Run Moirix evidence workflow for NVDA" }),
    ]);
    apiMock.getRun.mockResolvedValue(makeMoirixDetail({
      moirix_artifacts: {
        status: { status: "ok" },
        event_thesis_graph: { current_thesis: { stance: "mixed", actionability: "watch" } },
        event_decision_context: {
          status: "blocked",
          position_counts: { positions: 0, open_orders: 0 },
          claim_gate: { blockers: ["positions_unavailable"] },
        },
        authority_status: {
          status: "checked",
          authority: { ready_for_real_money_trading_authority: false },
        },
      },
      artifacts: [{ name: "moirix/event_thesis_graph.json", path: "/runs/moirix/artifacts/moirix/event_thesis_graph.json", type: "json", size: 12, exists: true }],
    }));

    renderHome();

    expect(await screen.findByText("blocked · positions_unavailable")).toBeInTheDocument();
    expect(screen.queryByText("0 positions · 0 orders")).not.toBeInTheDocument();
  });

  it("does not surface legacy graph-only Moirix runs as event thesis runs", async () => {
    apiMock.listRuns.mockResolvedValue([
      makeRun({ run_id: "legacy_moirix_run", prompt: "Legacy Moirix graph workflow" }),
    ]);
    apiMock.getRun.mockResolvedValue(makeRunDetail({
      run_id: "legacy_moirix_run",
      moirix_artifacts: {
        status: { status: "ok" },
        event_impact_graph: { nodes: [] },
      },
      artifacts: [{ name: "moirix/status.json", path: "/runs/moirix/artifacts/moirix/status.json", type: "json", size: 12, exists: true }],
    }));

    renderHome();

    expect(await screen.findByText("legacy_moirix_run")).toBeInTheDocument();
    expect(screen.getByText("No Moirix event thesis or position decision artifacts found in recent runs. Ordinary Vibe workflows are unaffected.")).toBeInTheDocument();
  });

  it("requests details only for the Moirix scan limit", async () => {
    const runs = Array.from({ length: 14 }, (_, index) => makeRun({ run_id: `run-${index + 1}` }));
    apiMock.listRuns.mockResolvedValue(runs);
    apiMock.getRun.mockImplementation((runId: string) => Promise.resolve(makeRunDetail({ run_id: runId })));

    renderHome();

    expect(await screen.findByText("run-1")).toBeInTheDocument();
    expect(screen.queryByText("run-7")).not.toBeInTheDocument();
    expect(apiMock.getRun).toHaveBeenCalledTimes(12);
  });
});
