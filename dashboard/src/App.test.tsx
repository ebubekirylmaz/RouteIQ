import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { App } from "./App";
import { serveEvaluationApi } from "./test/evaluationServer";
import { serveRequestsApi } from "./test/requestsServer";
import { serveReviewApi } from "./test/reviewServer";
import { server } from "./test/server";
import { serveStatsApi } from "./test/statsServer";
import { serveTimeseriesApi } from "./test/timeseriesServer";
import { renderWithProviders } from "./test/utils";

// The screens load their data, so the routes need an API to talk to.
beforeEach(() => {
  serveReviewApi([]);
  serveRequestsApi();
  serveEvaluationApi();
  serveStatsApi();
  serveTimeseriesApi();
});

const heading = (name: string) => screen.getByRole("heading", { level: 1, name });

describe("routing", () => {
  it("sends the root to the review queue", () => {
    renderWithProviders(<App />, { route: "/" });
    expect(heading("Review queue")).toBeInTheDocument();
  });

  it.each([
    ["/review", "Review queue"],
    ["/overview", "Overview"],
    ["/charts", "Charts"],
    ["/evaluation", "Evaluation"],
    ["/history", "History"],
    ["/try", "Try it"],
  ])("shows %s", async (route, title) => {
    renderWithProviders(<App />, { route });
    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeInTheDocument();
  });

  it("shows a not-found page with a way back", async () => {
    renderWithProviders(<App />, { route: "/nowhere" });
    expect(heading("Page not found")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Back to the review queue" }));
    expect(heading("Review queue")).toBeInTheDocument();
  });
});

describe("navigation", () => {
  it("has a link for every screen", () => {
    renderWithProviders(<App />, { route: "/review" });
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toHaveTextContent("Review queue");
    for (const name of ["Review queue", "Overview", "Charts", "Evaluation", "History", "Try it"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("moves between screens without a reload", async () => {
    renderWithProviders(<App />, { route: "/review" });
    await userEvent.click(screen.getByRole("link", { name: "Charts" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Charts" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "History" }));
    expect(heading("History")).toBeInTheDocument();
  });

  it("marks the current screen", () => {
    renderWithProviders(<App />, { route: "/overview" });
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Charts" })).not.toHaveAttribute("aria-current");
  });
});

describe("layout", () => {
  it("warns that the API has no authentication", () => {
    renderWithProviders(<App />, { route: "/review" });
    expect(screen.getByText(/no authentication/i)).toBeInTheDocument();
  });

  it("shows the name of the product", () => {
    renderWithProviders(<App />, { route: "/review" });
    expect(screen.getByText("RouteIQ")).toBeInTheDocument();
  });
});

describe("the note about synthetic data", () => {
  const note = () => screen.queryByRole("note");

  it("says so on every screen when the config uses synthetic data", async () => {
    serveReviewApi([], undefined, { domain: "ev_after_sales", data_source: "synthetic" });
    renderWithProviders(<App />, { route: "/overview" });

    expect(await screen.findByRole("note")).toHaveTextContent(/Synthetic data/);
    expect(note()).toHaveTextContent("ev_after_sales");
    expect(note()).toHaveTextContent(/says nothing about real data/);

    await userEvent.click(screen.getByRole("link", { name: "History" }));
    expect(await screen.findByRole("heading", { level: 1, name: "History" })).toBeInTheDocument();
    expect(note()).toBeInTheDocument();
  });

  it.each([["public"], [null], ["private"]])("is not shown for data_source %s", async (source) => {
    serveReviewApi([], undefined, { data_source: source as never });
    renderWithProviders(<App />, { route: "/overview" });
    await screen.findByRole("heading", { level: 1, name: "Overview" });
    await waitFor(() => expect(note()).not.toBeInTheDocument());
    // give the config request time to answer
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(note()).not.toBeInTheDocument();
  });

  it("is not shown, and nothing breaks, when the config cannot be loaded", async () => {
    server.use(http.get("*/config", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    renderWithProviders(<App />, { route: "/overview" });
    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(note()).not.toBeInTheDocument();
  });
});
