import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { server } from "../test/server";
import { requestItem, requestItems, serveConfigWithTiers, serveRequestsApi } from "../test/requestsServer";
import { renderWithProviders } from "../test/utils";
import { HistoryPage } from "./HistoryPage";

function Where() {
  const { pathname, search } = useLocation();
  return <output aria-label="Address">{pathname + search}</output>;
}

const show = (route = "/history") =>
  renderWithProviders(
    <>
      <HistoryPage />
      <Where />
    </>,
    { route },
  );

const address = () => screen.getByLabelText("Address").textContent;
const lastRead = (api: ReturnType<typeof serveRequestsApi>) => api.reads.at(-1)?.searchParams;

beforeEach(() => serveConfigWithTiers());

describe("loading and the list", () => {
  it("shows a loading message, then the requests with a count", async () => {
    serveRequestsApi(requestItems(3));
    show();
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(await screen.findByText("3 requests")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(4); // header + 3
  });

  it("lists the newest request first", async () => {
    serveRequestsApi(requestItems(3));
    show();
    await screen.findByText("3 requests");
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("request 3");
    expect(rows[2]).toHaveTextContent("request 1");
  });

  it("uses the singular for one request", async () => {
    serveRequestsApi(requestItems(1));
    show();
    expect(await screen.findByText("1 request")).toBeInTheDocument();
  });

  it("says plainly when there are no requests yet", async () => {
    serveRequestsApi([]);
    show();
    expect(await screen.findByText("No requests yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("asks for the first page, newest first, 25 at a time", async () => {
    const api = serveRequestsApi(requestItems(3));
    show();
    await screen.findByText("3 requests");
    expect(Object.fromEntries(lastRead(api) ?? [])).toEqual({ limit: "25", offset: "0", order: "newest" });
  });
});

describe("what a row says", () => {
  it("shows an accepted request with its tier, label, confidence, cost and latency", async () => {
    serveRequestsApi([requestItem(1, { tier: "llm", label: "report_fraud", confidence: 0.936, cost_usd: 0.0021, latency_ms: 1210 })]);
    show();
    const row = (await screen.findAllByRole("row"))[1] as HTMLElement;
    expect(row).toHaveTextContent("Accepted by llm");
    expect(row).toHaveTextContent("report_fraud");
    expect(row).toHaveTextContent("93%");
    expect(row).toHaveTextContent("$0.0021");
    expect(row).toHaveTextContent("1.2 s");
    expect(row).toHaveTextContent("Sent");
  });

  it("marks a request where a tier failed", async () => {
    serveRequestsApi([requestItem(1, { degraded: true }), requestItem(2)]);
    show();
    await screen.findByText("2 requests");
    expect(screen.getAllByText("A tier failed")).toHaveLength(1);
  });

  it("shows the person's label next to what the model suggested", async () => {
    serveRequestsApi([
      requestItem(1, {
        action: "human_review", review_status: "resolved", label: "report_fraud", final_label: "out_of_scope",
        delivery_status: "sent",
      }),
    ]);
    show();
    const row = (await screen.findAllByRole("row"))[1] as HTMLElement;
    expect(row).toHaveTextContent("Decided by a person");
    expect(row).toHaveTextContent("out_of_scope");
    expect(row).toHaveTextContent("model suggested report_fraud");
  });

  it("does not claim a request waiting for a person was delivered", async () => {
    serveRequestsApi([
      requestItem(1, { action: "human_review", review_status: "pending", delivery_status: null, delivered_at: null }),
    ]);
    show();
    const row = (await screen.findAllByRole("row"))[1] as HTMLElement;
    expect(row).toHaveTextContent("Waiting for a person");
    expect(row).toHaveTextContent("Not sent yet");
  });

  it("makes a failed delivery stand out", async () => {
    serveRequestsApi([requestItem(1, { delivery_status: "failed", delivery_error: "HTTP 500 from <url>" })]);
    show();
    expect(await screen.findByText("Failed")).toBeInTheDocument();
  });

  it("does not show 0% for a request that no tier could answer", async () => {
    serveRequestsApi([requestItem(1, { label: null, confidence: 0, tier: null, action: "human_review", review_status: "pending", delivery_status: null })]);
    show();
    const row = (await screen.findAllByRole("row"))[1] as HTMLElement;
    expect(row).toHaveTextContent("no suggestion");
    expect(row).not.toHaveTextContent("0%");
    expect(row).toHaveTextContent("n/a");
  });

  it("shortens a long text in the row", async () => {
    serveRequestsApi([requestItem(1, { text: "word ".repeat(60) })]);
    show();
    const button = await screen.findByRole("button", { name: /show details/ });
    expect(button.textContent?.length).toBeLessThan(120);
    expect(button).toHaveTextContent("…");
  });
});

describe("details of a row", () => {
  it("opens to show the whole text and closes again", async () => {
    const text = `${"long ".repeat(40)}end`;
    serveRequestsApi([requestItem(1, { text })]);
    show();
    const toggle = await screen.findByRole("button", { name: /show details/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(text)).toBeInTheDocument();

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(text)).not.toBeInTheDocument();
  });

  it("has one row open at a time", async () => {
    serveRequestsApi(requestItems(2));
    show();
    const [first, second] = await screen.findAllByRole("button", { name: /show details/ });
    await userEvent.click(first as HTMLElement);
    await userEvent.click(second as HTMLElement);
    expect(screen.getAllByRole("button", { expanded: true })).toHaveLength(1);
  });

  it("shows when a person decided, and the masked delivery problem", async () => {
    serveRequestsApi([
      requestItem(1, {
        action: "human_review", review_status: "resolved", final_label: "card_declined", resolved_at: "2026-10-05T15:30:00Z",
        delivery_status: "failed", delivery_error: "HTTP 500 from <url>", delivered_at: null,
      }),
    ]);
    show();
    await userEvent.click(await screen.findByRole("button", { name: /show details/ }));
    expect(screen.getByText("Oct 5, 15:30:00 UTC")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500 from <url>")).toBeInTheDocument();
    const person = screen.getByText("Person's label");
    expect(person.nextElementSibling).toHaveTextContent("card_declined");
  });
});

describe("filters", () => {
  it("filters by outcome and puts the choice in the address", async () => {
    const api = serveRequestsApi([requestItem(1), requestItem(2, { action: "human_review", review_status: "pending", delivery_status: null })]);
    show();
    await screen.findByText("2 requests");

    await userEvent.selectOptions(screen.getByLabelText("Outcome"), "human_review");
    expect(await screen.findByText("1 request match these filters")).toBeInTheDocument();
    expect(address()).toBe("/history?action=human_review");
    expect(lastRead(api)?.get("action")).toBe("human_review");
  });

  it("filters by review, delivery and tier", async () => {
    const api = serveRequestsApi(requestItems(2));
    show();
    await screen.findByText("2 requests");

    await userEvent.selectOptions(screen.getByLabelText("Review"), "resolved");
    await userEvent.selectOptions(screen.getByLabelText("Delivery"), "failed");
    await userEvent.selectOptions(screen.getByLabelText("Tier"), "llm");
    await waitFor(() => expect(lastRead(api)?.get("tier")).toBe("llm"));
    expect(lastRead(api)?.get("review_status")).toBe("resolved");
    expect(lastRead(api)?.get("delivery_status")).toBe("failed");
    expect(address()).toBe("/history?review=resolved&delivery=failed&tier=llm");
  });

  it("offers the tiers of the config", async () => {
    serveRequestsApi([]);
    serveConfigWithTiers(["rules", "llm"]);
    show();
    const tier = await screen.findByLabelText("Tier");
    await waitFor(() => expect(within(tier).getAllByRole("option").map((o) => o.textContent)).toEqual(["Any", "rules", "llm"]));
  });

  it("leaves the tier choice out when the config could not be loaded", async () => {
    serveRequestsApi(requestItems(1));
    server.use(http.get("*/config", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    show();
    await screen.findByText("1 request");
    expect(screen.queryByLabelText("Tier")).not.toBeInTheDocument();
  });

  it("filters to requests where a tier failed", async () => {
    const api = serveRequestsApi([requestItem(1, { degraded: true }), requestItem(2)]);
    show();
    await screen.findByText("2 requests");
    await userEvent.click(screen.getByRole("checkbox", { name: "Only where a tier failed" }));
    expect(await screen.findByText("1 request match these filters")).toBeInTheDocument();
    expect(lastRead(api)?.get("degraded")).toBe("true");
    expect(address()).toBe("/history?degraded=1");
  });

  it("does not search until asked: typing alone asks the API for nothing", async () => {
    const api = serveRequestsApi(requestItems(2));
    show();
    await screen.findByText("2 requests");
    const reads = api.reads.length;
    await userEvent.type(screen.getByLabelText("Search text"), "request 2");
    expect(api.reads).toHaveLength(reads);
  });

  it("searches on Enter", async () => {
    const api = serveRequestsApi([requestItem(1, { text: "lost my wallet" }), requestItem(2, { text: "card declined" })]);
    show();
    await screen.findByText("2 requests");
    await userEvent.type(screen.getByLabelText("Search text"), "WALLET{Enter}");
    expect(await screen.findByText("1 request match these filters")).toBeInTheDocument();
    expect(lastRead(api)?.get("q")).toBe("WALLET");
    expect(address()).toBe("/history?q=WALLET");
  });

  it("searches with the button, and trims the text", async () => {
    const api = serveRequestsApi(requestItems(2));
    show();
    await screen.findByText("2 requests");
    await userEvent.type(screen.getByLabelText("Search text"), "  request  ");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(lastRead(api)?.get("q")).toBe("request"));
  });

  it("says when nothing matches, and clears the filters", async () => {
    serveRequestsApi(requestItems(2));
    show();
    await screen.findByText("2 requests");
    await userEvent.type(screen.getByLabelText("Search text"), "nothing like this{Enter}");
    expect(await screen.findByText("No requests match these filters.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("2 requests")).toBeInTheDocument();
    expect(address()).toBe("/history");
    expect(screen.getByLabelText("Search text")).toHaveValue("");
  });

  it("has nothing to clear when there are no filters", async () => {
    serveRequestsApi(requestItems(1));
    show();
    await screen.findByText("1 request");
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeDisabled();
  });

  it("starts from the filters in the address", async () => {
    const api = serveRequestsApi(requestItems(1));
    show("/history?action=accepted&delivery=failed&degraded=1&q=hi&tier=llm");
    await screen.findByText("No requests match these filters.");
    const read = lastRead(api);
    expect(read?.get("action")).toBe("accepted");
    expect(read?.get("delivery_status")).toBe("failed");
    expect(read?.get("degraded")).toBe("true");
    expect(read?.get("q")).toBe("hi");
    expect(read?.get("tier")).toBe("llm");
    expect(screen.getByLabelText("Outcome")).toHaveValue("accepted");
    expect(screen.getByLabelText("Search text")).toHaveValue("hi");
  });

  it("keeps a tier from the address that the config does not know", async () => {
    serveRequestsApi([]);
    show("/history?tier=old_tier");
    await waitFor(() => expect(screen.getByLabelText("Tier")).toHaveValue("old_tier"));
  });

  it("never sends a value it does not understand to the API", async () => {
    const api = serveRequestsApi(requestItems(1));
    show("/history?action=maybe&delivery=lost&degraded=yes&page=-4&evil=1");
    await screen.findByText("1 request");
    expect(Object.fromEntries(lastRead(api) ?? [])).toEqual({ limit: "25", offset: "0", order: "newest" });
  });
});

describe("paging", () => {
  it("pages through the list and keeps the page in the address", async () => {
    const api = serveRequestsApi(requestItems(60));
    show();
    expect(await screen.findByText("1-25 of 60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("26-50 of 60")).toBeInTheDocument();
    expect(address()).toBe("/history?page=2");
    expect(lastRead(api)?.get("offset")).toBe("25");

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("51-60 of 60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("opens on the page of the address", async () => {
    serveRequestsApi(requestItems(60));
    show("/history?page=3");
    expect(await screen.findByText("51-60 of 60")).toBeInTheDocument();
  });

  it("goes back to the first page when a filter changes", async () => {
    serveRequestsApi(requestItems(60));
    show("/history?page=2");
    await screen.findByText("26-50 of 60");
    await userEvent.selectOptions(screen.getByLabelText("Outcome"), "accepted");
    await screen.findByText("1-25 of 60");
    expect(address()).toBe("/history?action=accepted");
  });

  it("shows the last page instead of an empty one when the address is past the end", async () => {
    serveRequestsApi(requestItems(30));
    show("/history?page=9");
    expect(await screen.findByText("26-30 of 30")).toBeInTheDocument();
    expect(address()).toBe("/history?page=2");
  });

  it("has no pages without rows", async () => {
    serveRequestsApi([]);
    show();
    await screen.findByText("No requests yet.");
    expect(screen.queryByRole("navigation", { name: "Pages of the history" })).not.toBeInTheDocument();
  });

  it("closes an open row when the page changes", async () => {
    serveRequestsApi(requestItems(30));
    show();
    await userEvent.click((await screen.findAllByRole("button", { name: /show details/ }))[0] as HTMLElement);
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("26-30 of 30");
    expect(screen.queryByRole("button", { expanded: true })).not.toBeInTheDocument();
  });
});

describe("refreshing", () => {
  it("does not refresh by itself, but has a Refresh button", async () => {
    const api = serveRequestsApi(requestItems(1));
    show();
    await screen.findByText("1 request");
    expect(screen.getByText(/^Updated .* UTC$/)).toBeInTheDocument();
    const reads = api.reads.length;

    api.rows.push(requestItem(2));
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("2 requests")).toBeInTheDocument();
    expect(api.reads.length).toBe(reads + 1);
  });
});

describe("problems", () => {
  it("offers to try again when the history cannot be loaded", async () => {
    server.use(http.get("*/requests", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("The history could not be loaded.");
    expect(screen.queryByText(/boom/)).not.toBeInTheDocument();

    serveRequestsApi(requestItems(2));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("2 requests")).toBeInTheDocument();
  });

  it("keeps the list and warns when a refresh fails", async () => {
    serveRequestsApi(requestItems(2));
    show();
    await screen.findByText("2 requests");

    server.use(http.get("*/requests", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be refreshed");
    expect(screen.getByText("2 requests")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });
});
