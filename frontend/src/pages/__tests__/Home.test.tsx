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
    run_id: "moirix_run",
    status: "success",
    created_at: "2026-06-12T08:00:00Z",
    prompt: "Run Moirix evidence workflow for NVDA",
    ...overrides,
  };
}

function makeRunDetail(overrides: Partial<RunData> = {}): RunData {
  return {
    run_id: "moirix_run",
    status: "success",
    moirix_artifacts: {
      status: { status: "ok" },
      coverage_status: { status: "partial", caveat: "Low-confidence evidence coverage." },
      news_evidence_preview: [{ id: "n1" }, { id: "n2" }],
      event_impact_graph: { nodes: [] },
      event_signal_backtest_summary: { total_events: 2 },
      authority_status: {
        status: "checked",
        authority: { ready_for_real_money_trading_authority: false },
      },
    },
    artifacts: [{ name: "moirix/status.json", path: "/runs/moirix/artifacts/moirix/status.json", type: "json", size: 12, exists: true }],
    ...overrides,
  };
}

describe("Home Moirix research dashboard", () => {
  beforeEach(() => {
    apiMock.listRuns.mockReset();
    apiMock.getRun.mockReset();
  });

  it("shows recent Moirix artifact runs and links to Run Detail Moirix tabs", async () => {
    apiMock.listRuns.mockResolvedValue([
      makeRun(),
      makeRun({ run_id: "ordinary_run", prompt: "Normal backtest" }),
    ]);
    apiMock.getRun.mockImplementation((runId: string) => {
      if (runId === "moirix_run") return Promise.resolve(makeRunDetail());
      return Promise.resolve({ run_id: runId, status: "success" });
    });

    renderHome();

    expect(await screen.findByText("Moirix Research Evidence")).toBeInTheDocument();
    expect(screen.getByText("moirix_run")).toBeInTheDocument();
    expect(screen.queryByText("ordinary_run")).not.toBeInTheDocument();
    expect(screen.getByText("2 preview rows")).toBeInTheDocument();
    expect(screen.getByText("graph artifact present")).toBeInTheDocument();
    expect(screen.getByText("backtest summary present")).toBeInTheDocument();
    expect(screen.getByText(/real-money=false/)).toBeInTheDocument();
    expect(screen.getByText("Low-confidence evidence coverage.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Evidence" })).toHaveAttribute("href", "/runs/moirix_run?tab=moirixEvidence");
    expect(screen.getByRole("link", { name: "Graph" })).toHaveAttribute("href", "/runs/moirix_run?tab=moirixGraph");
    expect(screen.getByRole("link", { name: "Authority" })).toHaveAttribute("href", "/runs/moirix_run?tab=moirixAuthority");
  });

  it("keeps ordinary Vibe home usable when no Moirix artifacts exist", async () => {
    apiMock.listRuns.mockResolvedValue([makeRun({ run_id: "ordinary_run" })]);
    apiMock.getRun.mockResolvedValue({ run_id: "ordinary_run", status: "success" });

    renderHome();

    expect(await screen.findByText("No Moirix run artifacts found in recent runs. Ordinary Vibe workflows are unaffected.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Start Research/i })).toHaveAttribute("href", "/agent");
  });
});
