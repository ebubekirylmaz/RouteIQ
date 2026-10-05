import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../test/server";
import { LABELS, failDecisions, items, reviewItem, serveReviewApi } from "../test/reviewServer";
import { renderWithProviders } from "../test/utils";
import { ReviewQueuePage } from "./ReviewQueuePage";

const row = (text: string) => screen.getByRole("listitem", { name: text });
const choose = (text: string, label: string) =>
  userEvent.click(within(row(text)).getByRole("button", { name: new RegExp(`^${label}`) }));
const notifications = () => screen.getByRole("status", { name: "Notifications" });

async function renderPage(initial = items(3)) {
  const api = serveReviewApi(initial);
  const view = renderWithProviders(<ReviewQueuePage />);
  if (initial.length > 0) await screen.findByRole("listitem", { name: initial[0]?.text });
  return { api, ...view };
}

describe("loading", () => {
  it("says it is loading, then shows the requests", async () => {
    serveReviewApi(items(2));
    renderWithProviders(<ReviewQueuePage />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(await screen.findAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByRole("status", { name: "Loading" })).not.toBeInTheDocument();
  });

  it("shows how many requests are waiting", async () => {
    await renderPage(items(3));
    expect(screen.getByText("3 waiting")).toBeInTheDocument();
  });

  it("says so when the queue is empty", async () => {
    serveReviewApi([]);
    renderWithProviders(<ReviewQueuePage />);
    expect(await screen.findByText("The review queue is empty.")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});

describe("a request", () => {
  it("shows the text, the model's suggestion with its confidence, and who decided", async () => {
    await renderPage([reviewItem(1, { text: "can you delete my saved card", suggested_label: "freeze_account", confidence: 0.674, tier: "llm" })]);
    const request = row("can you delete my saved card");
    expect(within(request).getByText("freeze_account (67%)")).toBeInTheDocument();
    expect(within(request).getByText("llm")).toBeInTheDocument();
    expect(within(request).getByText("5 min")).toBeInTheDocument();
  });

  it("offers every label in the order of the config", async () => {
    await renderPage(items(1));
    const names = within(screen.getByRole("group")).getAllByRole("button").map((button) => button.textContent?.replace("suggested", ""));
    expect(names).toEqual(LABELS.map((label) => label.name));
  });

  it("marks the suggestion, and only the suggestion", async () => {
    await renderPage([reviewItem(1, { suggested_label: "report_fraud" })]);
    const request = row("request 1");
    expect(within(request).getAllByText("suggested")).toHaveLength(1);
    expect(within(request).getByRole("button", { name: /^report_fraud/ })).toHaveTextContent("suggested");
    expect(within(request).getByRole("button", { name: /^damaged_card/ })).not.toHaveTextContent("suggested");
  });

  it("explains a label with its description", async () => {
    await renderPage(items(1));
    expect(within(row("request 1")).getByRole("button", { name: /^damaged_card/ })).toHaveAttribute(
      "title",
      "the card is physically damaged.",
    );
  });

  it("copes with a request the model had no suggestion for", async () => {
    await renderPage([reviewItem(1, { suggested_label: null, confidence: null, tier: null })]);
    const request = row("request 1");
    expect(within(request).getByText("No suggestion")).toBeInTheDocument();
    expect(within(request).queryByText("suggested")).not.toBeInTheDocument();
    expect(within(request).getAllByRole("button")).toHaveLength(LABELS.length);
  });

  it("labels each group of buttons with its request, for screen readers", async () => {
    await renderPage(items(2));
    expect(screen.getByRole("group", { name: "Choose the label for request 1" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Choose the label for request 2" })).toBeInTheDocument();
  });
});

describe("deciding", () => {
  it("never decides for the person: nothing is sent until a label is clicked", async () => {
    const { api } = await renderPage(items(2));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(api.posts).toEqual([]);
  });

  it("sends the chosen label for that request, confirms it, and removes the row", async () => {
    const { api } = await renderPage(items(3));
    await choose("request 2", "report_fraud");

    await waitFor(() => expect(screen.queryByRole("listitem", { name: "request 2" })).not.toBeInTheDocument());
    expect(api.posts).toEqual([{ id: 2, label: "report_fraud" }]);
    expect(notifications()).toHaveTextContent('Request 2 was labeled "report_fraud".');
    expect(screen.getByText("2 waiting")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("lets the person pick a label other than the suggestion", async () => {
    const { api } = await renderPage([reviewItem(1, { suggested_label: "freeze_account" })]);
    await choose("request 1", "out_of_scope");
    await waitFor(() => expect(api.posts).toEqual([{ id: 1, label: "out_of_scope" }]));
  });

  it("locks only its own buttons while the decision is being saved", async () => {
    const { api } = await renderPage(items(2));
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post("*/review/1", async () => {
        await gate;
        api.queue = api.queue.filter((item) => item.id !== 1); // the decision takes effect
        return HttpResponse.json({ id: 1, status: "resolved", final_label: "report_fraud" });
      }),
    );

    await choose("request 1", "report_fraud");

    await waitFor(() => {
      for (const button of within(row("request 1")).getAllByRole("button")) expect(button).toBeDisabled();
    });
    expect(row("request 1")).toHaveAttribute("aria-busy", "true");
    for (const button of within(row("request 2")).getAllByRole("button")) expect(button).toBeEnabled();

    release();
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "request 1" })).not.toBeInTheDocument());
  });

  it("can decide several requests at the same time", async () => {
    const { api } = await renderPage(items(3));
    await Promise.all([choose("request 1", "report_fraud"), choose("request 3", "damaged_card")]);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(1));
    expect(api.posts.map((post) => post.id).sort()).toEqual([1, 3]);
  });

  it("shows only the latest message", async () => {
    await renderPage(items(3));
    await choose("request 1", "report_fraud");
    await waitFor(() => expect(notifications()).toHaveTextContent("Request 1"));
    await choose("request 2", "damaged_card");
    await waitFor(() => expect(notifications()).toHaveTextContent("Request 2"));
    expect(notifications()).not.toHaveTextContent("Request 1");
  });

  it("lets the person dismiss a message", async () => {
    await renderPage(items(2));
    await choose("request 1", "report_fraud");
    await screen.findByText(/was labeled/);
    await userEvent.click(within(notifications()).getByRole("button", { name: "Dismiss" }));
    expect(notifications()).toBeEmptyDOMElement();
  });
});

describe("when a decision fails", () => {
  it("tells the person that somebody else was faster, and removes the request", async () => {
    const { api } = await renderPage(items(2));
    failDecisions(409, "request is not pending review");
    api.queue = api.queue.filter((item) => item.id !== 1); // the other person's decision

    await choose("request 1", "report_fraud");

    expect(await screen.findByText(/Someone else already handled this request/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "request 1" })).not.toBeInTheDocument());
    expect(notifications().querySelector("[data-kind]")).toHaveAttribute("data-kind", "info");
  });

  it("tells the person that the request is gone on a 404", async () => {
    const { api } = await renderPage(items(2));
    failDecisions(404, "request not found");
    api.queue = api.queue.filter((item) => item.id !== 1);

    await choose("request 1", "report_fraud");

    expect(await screen.findByText(/no longer exists/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "request 1" })).not.toBeInTheDocument());
  });

  it("keeps the request and reports an error when the label is refused", async () => {
    await renderPage(items(2));
    failDecisions(422, "unknown label");

    await choose("request 1", "report_fraud");

    expect(await screen.findByText(/not accepted any more/)).toBeInTheDocument();
    expect(notifications().querySelector("[data-kind]")).toHaveAttribute("data-kind", "error");
    expect(screen.getByRole("listitem", { name: "request 1" })).toBeInTheDocument();
    await waitFor(() => expect(within(row("request 1")).getAllByRole("button")[0]).toBeEnabled());
  });

  it("keeps the request, unlocks its buttons and asks to try again on a server error", async () => {
    await renderPage(items(2));
    failDecisions(500, "boom");

    await choose("request 1", "report_fraud");

    expect(await screen.findByText(/could not be saved/)).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "request 1" })).toBeInTheDocument();
    await waitFor(() => {
      for (const button of within(row("request 1")).getAllByRole("button")) expect(button).toBeEnabled();
    });
  });

  it("never shows the raw API message", async () => {
    await renderPage(items(1));
    failDecisions(500, "Traceback (most recent call last)");
    await choose("request 1", "report_fraud");
    await screen.findByText(/could not be saved/);
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
  });

  it("can decide again after a failure", async () => {
    const { api } = await renderPage(items(1));
    failDecisions(500, "boom");
    await choose("request 1", "report_fraud");
    await screen.findByText(/could not be saved/);

    serveReviewApi(api.queue); // the server is back
    await waitFor(() => expect(within(row("request 1")).getAllByRole("button")[0]).toBeEnabled());
    await choose("request 1", "report_fraud");

    await waitFor(() => expect(screen.getByText("The review queue is empty.")).toBeInTheDocument());
  });
});

describe("when loading fails", () => {
  it("offers to try again when the queue cannot be loaded", async () => {
    server.use(http.get("*/review", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    server.use(http.get("*/config", () => HttpResponse.json({ domain: "demo", labels: LABELS, tiers: [] })));
    renderWithProviders(<ReviewQueuePage />);

    expect(await screen.findByText("The review queue could not be loaded.")).toBeInTheDocument();

    serveReviewApi(items(2));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByText("The review queue could not be loaded.")).not.toBeInTheDocument();
  });

  it("offers to try again when the labels cannot be loaded", async () => {
    server.use(http.get("*/config", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    server.use(http.get("*/review", () => HttpResponse.json(items(1), { headers: { "X-Total-Count": "1" } })));
    renderWithProviders(<ReviewQueuePage />);

    expect(await screen.findByText("The labels could not be loaded.")).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();

    serveReviewApi(items(1));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("listitem", { name: "request 1" })).toBeInTheDocument();
  });

  it("keeps the list and warns when a refresh fails", async () => {
    const { client } = await renderPage(items(2));
    server.use(http.get("*/review", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));

    await client.invalidateQueries({ queryKey: ["review"] });

    expect(await screen.findByText(/could not be refreshed/)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("paging", () => {
  it("shows the first page and moves forward and back", async () => {
    await renderPage(items(45));
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    expect(screen.getByText("1-20 of 45")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("21-40 of 45")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "request 21" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("41-45 of 45")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(await screen.findByText("21-40 of 45")).toBeInTheDocument();
  });

  it("keeps the previous page, dimmed, while the next one loads", async () => {
    const api = await renderPage(items(45));
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("*/review", async ({ request }) => {
        await gate;
        const url = new URL(request.url);
        const offset = Number(url.searchParams.get("offset"));
        return HttpResponse.json(api.api.queue.slice(offset, offset + 20), { headers: { "X-Total-Count": "45" } });
      }),
    );

    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => expect(screen.getByRole("list")).toHaveAttribute("aria-busy", "true"));
    expect(screen.getByRole("listitem", { name: "request 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    release();
    await screen.findByRole("listitem", { name: "request 21" });
    expect(screen.getByRole("list")).toHaveAttribute("aria-busy", "false");
  });

  it("steps back a page when the last request of the last page is decided", async () => {
    await renderPage(items(21));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("listitem", { name: "request 21" });
    expect(screen.getAllByRole("listitem")).toHaveLength(1);

    await choose("request 21", "report_fraud");

    expect(await screen.findByText("1-20 of 20")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    expect(screen.queryByText("0 of 20")).not.toBeInTheDocument();
  });

  it("shows the empty queue after the very last request is decided", async () => {
    await renderPage(items(1));
    await choose("request 1", "report_fraud");
    expect(await screen.findByText("The review queue is empty.")).toBeInTheDocument();
    expect(notifications()).toHaveTextContent('Request 1 was labeled "report_fraud".');
  });
});
