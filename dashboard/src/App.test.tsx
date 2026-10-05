import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { App } from "./App";
import { serveReviewApi } from "./test/reviewServer";
import { renderWithProviders } from "./test/utils";

// The review queue screen loads its data, so the routes need a (here empty) API to talk to.
beforeEach(() => {
  serveReviewApi([]);
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
    ["/history", "History"],
  ])("shows %s", (route, title) => {
    renderWithProviders(<App />, { route });
    expect(heading(title)).toBeInTheDocument();
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
    for (const name of ["Review queue", "Overview", "Charts", "History"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("moves between screens without a reload", async () => {
    renderWithProviders(<App />, { route: "/review" });
    await userEvent.click(screen.getByRole("link", { name: "Charts" }));
    expect(heading("Charts")).toBeInTheDocument();
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
