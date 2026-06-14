import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RunDetail } from "../RunDetail";
import type { RunData } from "@/lib/api";

const apiMock = vi.hoisted(() => ({
  getRun: vi.fn(),
  getRunCode: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
}));

vi.mock("@/components/charts/CandlestickChart", () => ({
  CandlestickChart: ({ data }: { data: Array<{ code?: string; time: string }> }) => (
    <div data-testid={`chart-${data[0]?.code || data[0]?.time}`}>{data[0]?.code || data[0]?.time}</div>
  ),
}));

vi.mock("@/components/charts/EquityChart", () => ({
  EquityChart: () => <div data-testid="equity-chart" />,
}));

function renderRunDetail(initialEntry = "/runs/run-1") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

function makeRun(symbol: string, overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "run-1",
    status: "success",
    chart_symbols: ["AAA", "BBB", "CCC"],
    price_series: {
      [symbol]: [
        { time: "2024-01-02", code: symbol, open: 1, high: 2, low: 0.5, close: 1.5, volume: 100 },
      ],
    },
    indicator_series: {},
    trade_markers: [{ time: "2024-01-02", code: symbol, side: "BUY", price: 1.5 }],
    equity_curve: [{ time: "2024-01-02", equity: 1000, drawdown: 0 }],
    ...overrides,
  };
}

describe("RunDetail chart loading", () => {
  beforeEach(() => {
    apiMock.getRun.mockReset();
    apiMock.getRunCode.mockReset();
    apiMock.getRunCode.mockResolvedValue({});
    apiMock.getRun.mockImplementation((_runId: string, params?: { chart_symbol?: string; chart_payload?: "summary" }) => {
      if (params?.chart_payload === "summary") {
        return Promise.resolve(makeRun("AAA", {
          price_series: {},
          indicator_series: {},
          trade_markers: [],
        }));
      }
      return Promise.resolve(makeRun(params?.chart_symbol || "AAA"));
    });
  });

  it("loads an added chart symbol without replacing existing charts", async () => {
    renderRunDetail();

    expect(await screen.findByTestId("chart-AAA")).toBeInTheDocument();
    expect(apiMock.getRun).toHaveBeenCalledWith("run-1", { chart_payload: "summary" });
    expect(apiMock.getRun).toHaveBeenCalledWith("run-1", { chart_symbol: "AAA" });

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "BBB" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByTestId("chart-BBB")).toBeInTheDocument();
    expect(screen.getByTestId("chart-AAA")).toBeInTheDocument();
    expect(apiMock.getRun).toHaveBeenCalledWith("run-1", { chart_symbol: "BBB" });
  });

  it("progressively loads all symbols and reports progress", async () => {
    renderRunDetail();

    expect(await screen.findByTestId("chart-AAA")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load all" }));

    expect(await screen.findByTestId("chart-CCC")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("3 / 3 (100%)")).toBeInTheDocument());
    expect(apiMock.getRun).toHaveBeenCalledWith("run-1", { chart_symbol: "BBB" });
    expect(apiMock.getRun).toHaveBeenCalledWith("run-1", { chart_symbol: "CCC" });
  });

  it("renders Moirix event thesis and decision context tabs", async () => {
    apiMock.getRun.mockResolvedValue(makeRun("AAA", {
      moirix_artifacts: {
        event_thesis_graph: {
          current_thesis: {
            stance: "bullish",
            actionability: "watch",
            execution_window: { start: "2025-05-01", end: "2025-05-20", reason: "fixture" },
          },
          evidence_items: [{ event_id: "event:1", truth_status: "likely", summary: "Fixture event" }],
          relations: [{ source_event_id: "event:1", relation_type: "confirms", target_event_id: "event:1", explanation: "Fixture" }],
        },
        market_context: {
          status: "ok",
          source: { requested: "auto", detected: "tushare", effective: "baostock", fallback_used: true },
          series_summary: {
            first_date: "2025-04-21",
            last_date: "2025-05-01",
            bars: 8,
            total_return: 0.08,
          },
          technical_summary: {
            trend_state: "uptrend",
            sma_20: 120,
          },
          event_window: {
            as_of: "2025-05-01",
            pre_window_return: 0.02,
            post_window_return: null,
            retrospective_validation: false,
          },
          benchmark_comparison: {
            target_total_return: 0.08,
            benchmark_total_return: 0.03,
            excess_return: 0.05,
          },
        },
        event_thesis_report_markdown: "# Event Thesis\n\nWatch only.",
        event_decision_context: {
          status: "ok",
          position_counts: { positions: 1, open_orders: 0, executions: 0 },
          account_summary: { AvailableFunds_USD: "1000000.00" },
          portfolio_source: { type: "ibkr_paper_readiness", status: "blocked" },
          positions: [{ symbol: "NVDA", position: 10 }],
        },
        position_decision: {
          status: "ok",
          action: "add",
          execution_window: { start: "2025-05-02", end: "2025-05-10", reason: "fixture" },
          risk_sizing: { max_loss_notional: 250 },
        },
        trade_proposal: {
          status: "proposed",
          orders: [{ symbol: "NVDA", side: "buy", quantity: 1, order_type: "limit", limit_price: 100 }],
        },
        risk_sizing_report: {
          status: "ok",
          risk_sizing: { max_loss_notional: 250 },
        },
        decision_projection_preview: [
          { known_at: "2025-05-01", symbol: "NVDA", action: "add", side: "buy" },
        ],
        backtest_projection_manifest: {
          status: "ok",
          row_count: 1,
        },
        execution_status: {
          status: "blocked",
          claim_gate: { blockers: ["approval_missing"] },
        },
        portfolio_adjustment_plan_markdown: "# Portfolio Adjustment Plan\n\nPaper proposal only.",
      },
      artifacts: [{ name: "moirix/event_thesis_graph.json", path: "/tmp/event_thesis_graph.json", type: "json", size: 10, exists: true }],
    }));

    renderRunDetail("/runs/run-1?tab=moirixThesis");

    expect(await screen.findByText("Event Thesis Report")).toBeInTheDocument();
    expect(screen.getAllByText("bullish").length).toBeGreaterThan(0);
    expect(screen.getAllByText("watch").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Market Context/i }));
    expect(await screen.findByText("Series Summary")).toBeInTheDocument();
    expect(screen.getByText("baostock")).toBeInTheDocument();
    expect(screen.getAllByText("uptrend").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Decision Context/i }));
    expect(await screen.findByText("Account Summary")).toBeInTheDocument();
    expect(screen.getByText("1000000.00")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Position Decision/i }));
    expect((await screen.findAllByText("Portfolio Adjustment Plan")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("add").length).toBeGreaterThan(0);
    expect(screen.getByText("Trade Proposal")).toBeInTheDocument();
    expect(screen.getByText("Backtest Projection")).toBeInTheDocument();
    expect(screen.getAllByText("blocked").length).toBeGreaterThan(0);
  });
});
