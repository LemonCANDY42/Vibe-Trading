import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Reports } from "../Reports";
import type { RunListItem } from "@/lib/api";
import i18n from "@/i18n";

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
    i18n.changeLanguage("en");
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

  it("renders the report library in Chinese", async () => {
    i18n.changeLanguage("zh-CN");
    apiMock.listRuns.mockResolvedValue([]);

    renderReports();

    expect(await screen.findByText("回测报告库")).toBeInTheDocument();
    expect(screen.getByText("暂无报告")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("搜索 run id、prompt、标的或状态...")).toBeInTheDocument();
  });

  it("sorts reports newest first by default", async () => {
    apiMock.listRuns.mockResolvedValue([
      makeRun({ run_id: "older", created_at: "2026-06-10T08:00:00Z" }),
      makeRun({ run_id: "newer", created_at: "2026-06-12T08:00:00Z" }),
      makeRun({ run_id: "middle", created_at: "2026-06-11 08:00:00" }),
    ]);

    renderReports();
    expect(await screen.findByText("newer")).toBeInTheDocument();

    const rows = Array.from(document.querySelectorAll("article")).map((row) => row.textContent || "");
    expect(rows[0]).toContain("newer");
    expect(rows[1]).toContain("middle");
    expect(rows[2]).toContain("older");
  });

  it("can sort reports by best return", async () => {
    apiMock.listRuns.mockResolvedValue([
      makeRun({ run_id: "low-return", created_at: "2026-06-12T08:00:00Z", total_return: 0.01 }),
      makeRun({ run_id: "high-return", created_at: "2026-06-10T08:00:00Z", total_return: 0.42 }),
    ]);

    renderReports();
    expect(await screen.findByText("high-return")).toBeInTheDocument();

    let rows = Array.from(document.querySelectorAll("article")).map((row) => row.textContent || "");
    expect(rows[0]).toContain("low-return");

    fireEvent.change(screen.getByLabelText("Sort reports"), {
      target: { value: "return_desc" },
    });

    rows = Array.from(document.querySelectorAll("article")).map((row) => row.textContent || "");
    expect(rows[0]).toContain("high-return");
    expect(rows[1]).toContain("low-return");
  });
});
