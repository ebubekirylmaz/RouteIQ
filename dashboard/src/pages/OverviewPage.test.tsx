import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { REVIEWER_AGREEMENT_CAVEAT, REVIEWER_AGREEMENT_HELP } from "../lib/copy";
import { server } from "../test/server";
import { serveStatsApi, statsFixture } from "../test/statsServer";
import { renderWithProviders } from "../test/utils";
import { OverviewPage } from "./OverviewPage";

const card = (name: string) => screen.getByRole("article", { name });
const notifications = () => screen.getByRole("status", { name: "Notifications" });

async function renderPage(options: Parameters<typeof serveStatsApi>[0] = {}) {
  const api = serveStatsApi(options);
  const view = renderWithProviders(<OverviewPage />);
  await screen.findByRole("article", { name: "Requests" });
  return { api, ...view };
}

const hoursBefore = (url: URL | undefined) => (Date.now() - Date.parse(url?.searchParams.get("since") ?? "")) / 3_600_000;

describe("loading", () => {
  it("says it is loading, then shows the numbers", async () => {
    serveStatsApi();
    renderWithProviders(<OverviewPage />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(await screen.findByRole("article", { name: "Requests" })).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading" })).not.toBeInTheDocument();
  });

  it("has a heading and one heading per card", async () => {
    await renderPage();
    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThanOrEqual(8);
  });
});

describe("the numbers", () => {
  it("shows the requests", async () => {
    await renderPage();
    expect(within(card("Requests")).getByText("200")).toBeInTheDocument();
    expect(within(card("Requests")).getByText("in this window")).toBeInTheDocument();
  });

  it("shows how many went to a person, and how many wait now", async () => {
    await renderPage();
    const person = card("Sent to a person");
    expect(within(person).getByText("1.0%")).toBeInTheDocument();
    expect(within(person).getByText("2 of 200 requests. 1 waiting for review now.")).toBeInTheDocument();
  });

  it("shows the cost, and what 1,000 requests cost", async () => {
    await renderPage();
    expect(within(card("Cost")).getByText("$0.0022")).toBeInTheDocument();
    expect(within(card("Cost")).getByText("$0.0108 per 1,000 requests")).toBeInTheDocument();
  });

  it("shows the slow end of the latency first, and the average beside it", async () => {
    await renderPage();
    expect(within(card("Latency, p95")).getByText("1.1 s")).toBeInTheDocument();
    expect(within(card("Latency, p95")).getByText("average 333 ms")).toBeInTheDocument();
  });

  it("shows how many requests had a failing tier", async () => {
    await renderPage();
    expect(within(card("Requests where a tier failed")).getByText("0")).toBeInTheDocument();
    expect(within(card("Requests where a tier failed")).getByText("No tier failed.")).toBeInTheDocument();
  });

  it("warns when a tier failed", async () => {
    await renderPage({ stats: statsFixture({ degraded: 3 }) });
    const failed = card("Requests where a tier failed");
    expect(within(failed).getByText("3")).toBeInTheDocument();
    expect(within(failed).getByText(/fell back to what it had/)).toBeInTheDocument();
    expect(failed.className).toMatch(/warning/);
  });

  it("separates thousands", async () => {
    await renderPage({ stats: statsFixture({ requests: 12345 }) });
    expect(within(card("Requests")).getByText("12,345")).toBeInTheDocument();
  });

  it("lists how the requests ended and what happened to the deliveries", async () => {
    await renderPage();
    expect(screen.getByRole("table")).toHaveTextContent("Accepted by baseline");
    expect(screen.getByRole("region", { name: "Deliveries to the target system" })).toBeInTheDocument();
  });

  it("copes with a window without any request", async () => {
    await renderPage({
      stats: statsFixture({
        requests: 0, accepted_by_tier: {}, human_review: 0, cost_usd: 0,
        latency_ms: { avg: 0, p95: 0 }, review: { pending: 0, resolved: 0 },
        reviewer_agreement: { resolved: 0, agreed: 0, rate: null },
        delivery: { pending: 0, sent: 0, failed: 0, retryable: 0 },
      }),
    });
    expect(within(card("Requests")).getByText("0")).toBeInTheDocument();
    expect(within(card("Sent to a person")).getByText("n/a")).toBeInTheDocument();
    expect(within(card("Cost")).getByText("$0.00")).toBeInTheDocument();
    expect(within(card("Cost")).getByText("No requests yet")).toBeInTheDocument();
    expect(screen.getByText("No requests in this window.")).toBeInTheDocument();
    expect(screen.queryByText(/NaN|Infinity/)).not.toBeInTheDocument();
  });
});

describe("reviewer agreement", () => {
  it("shows the share, and how it was made up", async () => {
    await renderPage({ stats: statsFixture({ reviewer_agreement: { resolved: 4, agreed: 3, rate: 0.75 } }) });
    const agreement = card("Reviewer agreement");
    expect(within(agreement).getByText("75%")).toBeInTheDocument();
    expect(within(agreement).getByText(/3 of 4 reviewed requests kept the suggestion/)).toBeInTheDocument();
  });

  it("says there are no reviews yet instead of a number", async () => {
    await renderPage({ stats: statsFixture({ reviewer_agreement: { resolved: 0, agreed: 0, rate: null } }) });
    const agreement = card("Reviewer agreement");
    expect(within(agreement).getByText("No reviews yet")).toBeInTheDocument();
    expect(within(agreement).queryByText(/kept the suggestion/)).not.toBeInTheDocument();
    expect(within(agreement).queryByText(/NaN|null/)).not.toBeInTheDocument();
  });

  it("says right beside the number that it is not the model's accuracy", async () => {
    await renderPage();
    expect(within(card("Reviewer agreement")).getByText(new RegExp(REVIEWER_AGREEMENT_CAVEAT))).toBeVisible();
  });

  it("explains it in the API's own words, one click away", async () => {
    await renderPage();
    const agreement = card("Reviewer agreement");
    expect(within(agreement).getByText("What does this mean?")).toBeInTheDocument();
    expect(within(agreement).getByText(REVIEWER_AGREEMENT_HELP)).toBeInTheDocument();
  });

  it("never calls it accuracy", async () => {
    await renderPage();
    expect(screen.queryByText(/^accuracy$/i)).not.toBeInTheDocument();
    expect(card("Reviewer agreement")).not.toHaveTextContent(/^Accuracy/);
  });
});

describe("the time window", () => {
  it("starts with the last 24 hours", async () => {
    const { api } = await renderPage();
    expect(screen.getByRole("radio", { name: "Last 24 hours" })).toBeChecked();
    expect(hoursBefore(api.reads[0])).toBeGreaterThan(23.9);
    expect(hoursBefore(api.reads[0])).toBeLessThan(24.1);
  });

  it("asks for the last 7 days when chosen", async () => {
    const { api } = await renderPage();
    await userEvent.click(screen.getByRole("radio", { name: "Last 7 days" }));
    await waitFor(() => expect(api.reads).toHaveLength(2));
    expect(hoursBefore(api.reads[1])).toBeGreaterThan(167.9);
    expect(hoursBefore(api.reads[1])).toBeLessThan(168.1);
    expect(screen.getByRole("radio", { name: "Last 7 days" })).toBeChecked();
  });

  it("asks for everything, with no start time, for all time", async () => {
    const { api } = await renderPage();
    await userEvent.click(screen.getByRole("radio", { name: "All time" }));
    await waitFor(() => expect(api.reads).toHaveLength(2));
    expect(api.reads[1]?.searchParams.has("since")).toBe(false);
    expect(within(card("Requests")).getByText("since the first request")).toBeInTheDocument();
  });

  it("shows the new numbers for the new window", async () => {
    const { api } = await renderPage();
    api.stats = statsFixture({ requests: 5000 });
    await userEvent.click(screen.getByRole("radio", { name: "All time" }));
    expect(await within(card("Requests")).findByText("5,000")).toBeInTheDocument();
  });

  it("keeps the old numbers, dimmed, while the new ones load", async () => {
    await renderPage();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("*/stats", async () => {
        await gate;
        return HttpResponse.json(statsFixture({ requests: 777 }));
      }),
    );

    await userEvent.click(screen.getByRole("radio", { name: "Last 7 days" }));

    await waitFor(() => expect(card("Requests").parentElement).toHaveAttribute("aria-busy", "true"));
    expect(within(card("Requests")).getByText("200")).toBeInTheDocument();
    release();
    expect(await within(card("Requests")).findByText("777")).toBeInTheDocument();
    expect(card("Requests").parentElement).toHaveAttribute("aria-busy", "false");
  });
});

describe("resending deliveries", () => {
  const withRetryable = (retryable = 3) =>
    statsFixture({ delivery: { pending: 0, sent: 100, failed: retryable, retryable } });
  const resend = () => userEvent.click(screen.getByRole("button", { name: "Resend failed deliveries" }));

  it("resends, confirms, and refreshes the numbers", async () => {
    const { api } = await renderPage({ stats: withRetryable() });
    const before = api.reads.length;
    api.retryResult = { retried: 3, sent: 3, failed: 0 };
    api.stats = statsFixture();

    await resend();

    expect(await screen.findByText("Retried 3 deliveries: 3 sent, 0 failed.")).toBeInTheDocument();
    expect(api.retries()).toBe(1);
    await waitFor(() => expect(api.reads.length).toBeGreaterThan(before));
    await waitFor(() => expect(screen.getByRole("button", { name: "Resend failed deliveries" })).toBeDisabled());
  });

  it("is news, not an error, when some deliveries failed again", async () => {
    const { api } = await renderPage({ stats: withRetryable() });
    api.retryResult = { retried: 3, sent: 1, failed: 2 };
    await resend();
    await screen.findByText("Retried 3 deliveries: 1 sent, 2 failed.");
    expect(notifications().querySelector("[data-kind]")).toHaveAttribute("data-kind", "info");
  });

  it("says so when there turned out to be nothing to resend", async () => {
    const { api } = await renderPage({ stats: withRetryable() });
    api.retryResult = { retried: 0, sent: 0, failed: 0 };
    await resend();
    expect(await screen.findByText("Nothing needed to be resent.")).toBeInTheDocument();
  });

  it("locks the button while resending", async () => {
    await renderPage({ stats: withRetryable() });
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post("*/deliveries/retry", async () => {
        await gate;
        return HttpResponse.json({ retried: 3, sent: 3, failed: 0 });
      }),
    );

    await resend();

    expect(await screen.findByRole("button", { name: "Resending…" })).toBeDisabled();
    release();
    await screen.findByText(/Retried 3 deliveries/);
  });

  it("reports a failure and lets the person try again", async () => {
    await renderPage({ stats: withRetryable() });
    server.use(http.post("*/deliveries/retry", () => HttpResponse.json({ detail: "Traceback" }, { status: 500 })));

    await resend();

    expect(await screen.findByText(/could not be resent/)).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
    expect(notifications().querySelector("[data-kind]")).toHaveAttribute("data-kind", "error");
    await waitFor(() => expect(screen.getByRole("button", { name: "Resend failed deliveries" })).toBeEnabled());
  });

  it("explains a missing target when the API says so", async () => {
    await renderPage({ stats: withRetryable() });
    server.use(
      http.post("*/deliveries/retry", () => HttpResponse.json({ detail: "no delivery target configured" }, { status: 409 })),
    );
    await resend();
    expect(await screen.findByText("No delivery target is configured.")).toBeInTheDocument();
  });

  it("offers nothing to resend when no target is configured", async () => {
    await renderPage({ targetType: null });
    expect(screen.getByText(/No delivery target is configured, so decisions are not sent anywhere/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resend failed deliveries" })).not.toBeInTheDocument();
  });

  it("has the button off when nothing can be resent", async () => {
    await renderPage();
    expect(screen.getByRole("button", { name: "Resend failed deliveries" })).toBeDisabled();
  });

  it("clears the previous message when a new resend starts, and lets the person dismiss it", async () => {
    const { api } = await renderPage({ stats: withRetryable() });
    api.retryResult = { retried: 3, sent: 3, failed: 0 };
    await resend();
    await screen.findByText(/Retried 3 deliveries/);
    await userEvent.click(within(notifications()).getByRole("button", { name: "Dismiss" }));
    expect(notifications()).toBeEmptyDOMElement();
  });
});

describe("when loading fails", () => {
  it("offers to try again", async () => {
    server.use(http.get("*/stats", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    server.use(http.get("*/config", () => HttpResponse.json({ domain: "demo", labels: [], tiers: [], target_type: null })));
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText("The numbers could not be loaded.")).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();

    serveStatsApi();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Requests" })).toBeInTheDocument();
  });

  it("keeps the numbers and warns when a refresh fails", async () => {
    const { client } = await renderPage();
    server.use(http.get("*/stats", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));

    await client.invalidateQueries({ queryKey: ["stats"] });

    expect(await screen.findByText(/could not be refreshed/)).toBeInTheDocument();
    expect(within(card("Requests")).getByText("200")).toBeInTheDocument();
  });

  it("still shows the numbers when only the config cannot be loaded", async () => {
    serveStatsApi();
    server.use(http.get("*/config", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    renderWithProviders(<OverviewPage />);
    expect(await screen.findByRole("article", { name: "Requests" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Deliveries to the target system" })).toBeInTheDocument();
  });
});
