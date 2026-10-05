import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../test/server";
import { emptyPoint, makePoints, serveTimeseriesApi } from "../test/timeseriesServer";
import { renderWithProviders } from "../test/utils";
import { ChartsPage } from "./ChartsPage";

const minutesAgo = (iso: string | null | undefined) => (Date.now() - Date.parse(iso ?? "")) / 60_000;

async function renderPage(points = makePoints(24)) {
  const api = serveTimeseriesApi(points);
  const view = renderWithProviders(<ChartsPage />);
  await screen.findByRole("figure", { name: /^Requests/ });
  return { api, ...view };
}

describe("loading", () => {
  it("says it is loading, then draws the charts", async () => {
    serveTimeseriesApi();
    renderWithProviders(<ChartsPage />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(await screen.findByRole("figure", { name: /^Requests/ })).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading" })).not.toBeInTheDocument();
  });

  it("has a heading and three charts, each one drawn", async () => {
    await renderPage();
    expect(screen.getByRole("heading", { level: 1, name: "Charts" })).toBeInTheDocument();
    for (const name of [/^Requests/, /^Cost/, /^Latency/]) {
      expect(screen.getByRole("figure", { name })).toBeInTheDocument();
    }
    expect(document.querySelectorAll("figure .recharts-wrapper")).toHaveLength(3);
  });
});

describe("what the charts say", () => {
  it("adds the requests up in the caption", async () => {
    await renderPage(makePoints(3)); // 10 + 11 + 12
    expect(screen.getByText("33 requests, accepted by the cascade or sent to a person.")).toBeInTheDocument();
  });

  it("adds the cost up in the caption", async () => {
    await renderPage(makePoints(3)); // 3 x $0.0001
    expect(screen.getByText("$0.0003 in total, added up over the period.")).toBeInTheDocument();
  });

  it("explains that a gap in the latency means there were no requests", async () => {
    await renderPage();
    expect(screen.getByText(/A gap means there were no requests in that period/)).toBeInTheDocument();
  });

  it("says the times are in UTC, above the charts and in the table", async () => {
    await renderPage();
    expect(screen.getByText("One bar or point per hour. Times are in UTC.")).toBeInTheDocument();
    expect(screen.getByText("Requests, cost and latency per period. Times are in UTC.")).toBeInTheDocument();
  });

  it("names the size of the buckets", async () => {
    await renderPage();
    expect(screen.getByText(/One bar or point per hour/)).toBeInTheDocument();
  });
});

describe("the time range", () => {
  it("starts with the last 24 hours, in hourly buckets", async () => {
    const { api } = await renderPage();
    expect(screen.getByRole("radio", { name: "Last 24 hours" })).toBeChecked();
    expect(api.reads[0]?.searchParams.get("bucket")).toBe("hour");
    expect(minutesAgo(api.reads[0]?.searchParams.get("since"))).toBeGreaterThan(24 * 60 - 1);
  });

  it("switches to daily buckets for 7 days", async () => {
    const { api } = await renderPage();
    api.points = makePoints(7, "day");
    await userEvent.click(screen.getByRole("radio", { name: "Last 7 days" }));
    await waitFor(() => expect(api.reads).toHaveLength(2));
    expect(api.reads[1]?.searchParams.get("bucket")).toBe("day");
    expect(await screen.findByText(/One bar or point per day/)).toBeInTheDocument();
  });

  it("asks for 30 days of daily buckets", async () => {
    const { api } = await renderPage();
    api.points = makePoints(30, "day");
    await userEvent.click(screen.getByRole("radio", { name: "Last 30 days" }));
    await waitFor(() => expect(api.reads).toHaveLength(2));
    expect(minutesAgo(api.reads[1]?.searchParams.get("since"))).toBeGreaterThan(30 * 24 * 60 - 1);
    expect(await screen.findAllByRole("row")).toHaveLength(31);
  });

  it("keeps the old charts, dimmed, while the new range loads", async () => {
    await renderPage();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("*/stats/timeseries", async () => {
        await gate;
        return HttpResponse.json({ bucket: "day", since: "x", until: "y", points: makePoints(7, "day") });
      }),
    );

    await userEvent.click(screen.getByRole("radio", { name: "Last 7 days" }));

    const grid = screen.getByRole("figure", { name: /^Requests/ }).parentElement;
    await waitFor(() => expect(grid).toHaveAttribute("aria-busy", "true"));
    expect(screen.getByText(/One bar or point per hour/)).toBeInTheDocument(); // still the old data
    release();
    await waitFor(() => expect(grid).toHaveAttribute("aria-busy", "false"));
    expect(screen.getByText(/One bar or point per day/)).toBeInTheDocument();
  });

  it("is one labelled group of radio buttons", async () => {
    await renderPage();
    expect(screen.getByRole("group", { name: "Time window" })).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });
});

describe("the data table", () => {
  it("is folded away behind a summary", async () => {
    await renderPage();
    expect(screen.getByText("Show the data as a table")).toBeInTheDocument();
  });

  it("has a row for every period", async () => {
    await renderPage(makePoints(5));
    expect(screen.getAllByRole("row")).toHaveLength(6); // header + 5
  });
});

describe("a period without requests", () => {
  const quiet = [emptyPoint("2026-10-05T00:00:00Z"), emptyPoint("2026-10-05T01:00:00Z")];

  it("says so, instead of charts of zeros", async () => {
    serveTimeseriesApi(quiet);
    renderWithProviders(<ChartsPage />);
    expect(await screen.findByText("No requests in this period.")).toBeInTheDocument();
    expect(screen.queryByRole("figure")).not.toBeInTheDocument();
    expect(screen.queryByText("Show the data as a table")).not.toBeInTheDocument();
  });

  it("still lets the person pick another range", async () => {
    const api = serveTimeseriesApi(quiet);
    renderWithProviders(<ChartsPage />);
    await screen.findByText("No requests in this period.");
    api.points = makePoints(7, "day");
    await userEvent.click(screen.getByRole("radio", { name: "Last 7 days" }));
    expect(await screen.findByRole("figure", { name: /^Requests/ })).toBeInTheDocument();
  });

  it("handles an answer without any bucket", async () => {
    serveTimeseriesApi([]);
    renderWithProviders(<ChartsPage />);
    expect(await screen.findByText("No requests in this period.")).toBeInTheDocument();
  });
});

describe("when loading fails", () => {
  it("offers to try again", async () => {
    server.use(http.get("*/stats/timeseries", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    renderWithProviders(<ChartsPage />);
    expect(await screen.findByText("The charts could not be loaded.")).toBeInTheDocument();
    expect(screen.queryByRole("figure")).not.toBeInTheDocument();

    serveTimeseriesApi();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("figure", { name: /^Requests/ })).toBeInTheDocument();
  });

  it("keeps the charts and warns when a refresh fails", async () => {
    const { client } = await renderPage();
    server.use(http.get("*/stats/timeseries", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));

    await client.invalidateQueries({ queryKey: ["timeseries"] });

    expect(await screen.findByText(/could not be refreshed/)).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: /^Requests/ })).toBeInTheDocument();
  });
});
