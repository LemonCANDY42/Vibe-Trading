import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Reports } from "../Reports";
import type { RunListItem } from "@/lib/api";

const apiMock = vi.hoisted(() => ({
  listRuns: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
}));

function renderReports() {
  return render(
    <MemoryRouter>
      <Reports />
    </MemoryRouter>,
  );
}

function makeRun(overrides: Partial<RunListItem> = {}): RunListItem {
  return {
    run_id: "run-1",
    status: "success",
    created_at: "2026-06-12T08:00:00Z",
    prompt: "Backtest a momentum report",
    total_return: 0.12,
    sharpe: 1.2,
    codes: ["AAPL.US"],
    start_date: "2024-01-01",
    end_date: "2024-06-30",
    ...overrides,
  };
}

describe("Reports page", () => {
  beforeEach(() => {
    apiMock.listRuns.mockReset();
  });

  it("lists historical reports and links to full report", async () => {
    apiMock.listRuns.mockResolvedValue([makeRun()]);

    renderReports();

    expect(await screen.findByText("Backtest Report Library")).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
    expect(screen.getByText("AAPL.US")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Full Report/i })).toHaveAttribute("href", "/runs/run-1");
    expect(apiMock.listRuns).toHaveBeenCalledWith({ limit: 100, with_usage: true });
  });

  it("filters reports by prompt and symbol", async () => {
    apiMock.listRuns.mockResolvedValue([
      makeRun({ run_id: "run-aapl", codes: ["AAPL.US"], prompt: "Apple momentum" }),
      makeRun({ run_id: "run-nvda", codes: ["NVDA.US"], prompt: "Nvidia breakout" }),
    ]);

    renderReports();
    expect(await screen.findByText("run-aapl")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search run id, prompt, symbol, status..."), {
      target: { value: "NVDA" },
    });

    expect(screen.queryByText("run-aapl")).not.toBeInTheDocument();
    expect(screen.getByText("run-nvda")).toBeInTheDocument();
  });
});
