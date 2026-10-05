import { render, screen, within } from "@testing-library/react";
import chartsSource from "./Charts.tsx?raw";
import { describe, expect, it } from "vitest";

import { toChartPoints } from "../../lib/chartData";
import { emptyPoint, makePoints } from "../../test/timeseriesServer";
import { ChartCard } from "./ChartCard";
import { ChartTable } from "./ChartTable";
import { CostChart, LatencyChart, RequestsChart } from "./Charts";

const data = toChartPoints(makePoints(6), "hour");

describe("ChartCard", () => {
  it("is a figure named by its caption", () => {
    render(
      <ChartCard title="Requests" description="How many.">
        <p>chart</p>
      </ChartCard>,
    );
    const figure = screen.getByRole("figure", { name: /Requests/ });
    expect(within(figure).getByText("How many.")).toBeInTheDocument();
    expect(within(figure).getByText("chart")).toBeInTheDocument();
  });
});

describe("the charts", () => {
  it("draw the requests as stacked bars, with a legend that names both parts", () => {
    const { container } = render(<RequestsChart data={data} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
    expect(container.querySelectorAll(".recharts-bar")).toHaveLength(2);
    expect(screen.getByText("Accepted by the cascade")).toBeInTheDocument();
    expect(screen.getByText("Sent to a person")).toBeInTheDocument();
  });

  it("draw the running cost as a line", () => {
    const { container } = render(<CostChart data={data} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(1);
  });

  it("draw the latency as a line", () => {
    const { container } = render(<LatencyChart data={data} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
    expect(container.querySelectorAll(".recharts-line")).toHaveLength(1);
  });

  it("label the time axis with the short UTC labels", () => {
    const { container } = render(<RequestsChart data={data} />);
    const ticks = Array.from(container.querySelectorAll(".recharts-cartesian-axis-tick-value")).map((tick) => tick.textContent);
    expect(ticks.slice(0, 6)).toEqual(["00:00", "01:00", "02:00", "03:00", "04:00", "05:00"]);
  });

  it.each([
    ["requests", RequestsChart],
    ["cost", CostChart],
    ["latency", LatencyChart],
  ])("copes with a single bucket (%s)", (_name, Chart) => {
    const { container } = render(<Chart data={toChartPoints(makePoints(1), "hour")} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("copes with a gap in the latency", () => {
    const withGap = toChartPoints([...makePoints(2), emptyPoint("2026-10-05T02:00:00Z"), ...makePoints(1, "hour", "2026-10-05T03:00:00Z")], "hour");
    expect(withGap[2]?.avgLatency).toBeNull();
    const { container } = render(<LatencyChart data={withGap} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("do not animate, so they are ready at once and respect people who dislike motion", () => {
    const { container } = render(<RequestsChart data={data} />);
    expect(container.querySelector(".recharts-bar-rectangle")).toBeInTheDocument();
  });
});

describe("ChartTable", () => {
  it("sits behind a summary", () => {
    render(<ChartTable data={data} />);
    expect(screen.getByText("Show the data as a table")).toBeInTheDocument();
  });

  it("has a row for every period, named by its full UTC time", () => {
    render(<ChartTable data={data} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(6);
    expect(within(rows[0] as HTMLElement).getByRole("rowheader")).toHaveTextContent("Oct 5, 00:00 UTC");
  });

  it("shows the counts, the cost and the latency of each period", () => {
    render(<ChartTable data={toChartPoints([makePoints(1)[0] as ReturnType<typeof makePoints>[number]], "hour")} />);
    const cells = screen.getAllByRole("cell").map((cell) => cell.textContent);
    expect(cells).toEqual(["10", "9", "1", "$0.0001", "$0.0001", "300 ms"]);
  });

  it("says no requests instead of a latency for an empty period", () => {
    render(<ChartTable data={toChartPoints([emptyPoint("2026-10-05T02:00:00Z")], "hour")} />);
    expect(screen.getByText("no requests")).toBeInTheDocument();
    expect(screen.queryByText("<1 ms")).not.toBeInTheDocument();
  });

  it("adds the cost up down the column", () => {
    render(<ChartTable data={data} />);
    const lastRow = screen.getAllByRole("row").at(-1) as HTMLElement;
    expect(within(lastRow).getByText("$0.0006")).toBeInTheDocument();
  });

  it("has proper headers, a caption, and says the times are UTC", () => {
    render(<ChartTable data={data} />);
    expect(screen.getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "Period", "Requests", "Accepted", "Sent to a person", "Cost", "Cost so far", "Average latency",
    ]);
    expect(screen.getByText(/Times are in UTC/)).toBeInTheDocument();
  });
});

describe("the tooltip", () => {
  it("is styled with the theme colours, not Recharts' white", () => {
    const source = chartsSource;
    expect(source).toContain('background: "var(--surface)"');
    expect(source).not.toMatch(/background:\s*"#fff/i);
  });
});
