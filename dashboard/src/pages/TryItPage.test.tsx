import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { routeResult, serveConfig, serveRouteApi } from "../test/routeServer";
import { server } from "../test/server";
import { renderWithProviders } from "../test/utils";
import { TryItPage } from "./TryItPage";

// The screen asks for the config (for its example texts), so it needs an answer.
beforeEach(() => serveConfig());

const show = () => renderWithProviders(<TryItPage />, { route: "/try" });
const box = () => screen.getByLabelText("Text");
const send = () => screen.getByRole("button", { name: /Route it|Routing/ });
const result = () => screen.getByRole("status", { name: "Result" });

async function route(text: string) {
  await userEvent.clear(box());
  await userEvent.type(box(), text);
  await userEvent.click(send());
}

describe("the form", () => {
  it("says plainly that a text is stored and may cost money", () => {
    show();
    const intro = screen.getByText(/stored like any other request/);
    expect(intro).toHaveTextContent(/history and the statistics/);
    expect(intro).toHaveTextContent(/paid model/);
  });

  it("cannot send an empty text, or one with only spaces", async () => {
    const api = serveRouteApi();
    show();
    expect(send()).toBeDisabled();
    await userEvent.type(box(), "   ");
    expect(send()).toBeDisabled();
    await userEvent.type(box(), "a");
    expect(send()).toBeEnabled();
    expect(api.texts).toHaveLength(0);
  });

  it("counts the characters and stops at the limit of the API", async () => {
    show();
    expect(screen.getByText("0 / 5,000")).toBeInTheDocument();
    expect(box()).toHaveAttribute("maxlength", "5000");
    await userEvent.type(box(), "hello");
    expect(screen.getByText("5 / 5,000")).toBeInTheDocument();
  });

  it("sends the text without the spaces around it", async () => {
    const api = serveRouteApi();
    show();
    await route("  my card got declined \n");
    await screen.findByText("Accepted by baseline");
    expect(api.texts).toEqual(["my card got declined"]);
  });

  it("sends with Ctrl+Enter, and a plain Enter is only a new line", async () => {
    const api = serveRouteApi();
    show();
    await userEvent.type(box(), "first line{Enter}second line");
    expect(api.texts).toHaveLength(0);
    expect(box()).toHaveValue("first line\nsecond line");

    await userEvent.type(box(), "{Control>}{Enter}{/Control}");
    await screen.findByText("Accepted by baseline");
    expect(api.texts).toEqual(["first line\nsecond line"]);
  });

  it("sends with Cmd+Enter too", async () => {
    const api = serveRouteApi();
    show();
    await userEvent.type(box(), "hello{Meta>}{Enter}{/Meta}");
    await screen.findByText("Accepted by baseline");
    expect(api.texts).toEqual(["hello"]);
  });

  it("does not send an empty text with Ctrl+Enter", async () => {
    const api = serveRouteApi();
    show();
    await userEvent.type(box(), "{Control>}{Enter}{/Control}");
    expect(api.texts).toHaveLength(0);
  });

  it("keeps the text after an answer, so it can be changed and sent again", async () => {
    serveRouteApi();
    show();
    await route("hello");
    await screen.findByText("Accepted by baseline");
    expect(box()).toHaveValue("hello");
  });
});

describe("while a text is on its way", () => {
  it("shows that it is working and sends once, even when clicked again", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => (release = resolve));
    let posts = 0;
    server.use(
      http.post("*/route", async () => {
        posts += 1;
        await gate;
        return HttpResponse.json(routeResult());
      }),
    );
    show();
    await userEvent.type(box(), "hello");
    await userEvent.click(send());

    expect(await screen.findByRole("button", { name: "Routing…" })).toBeDisabled();
    expect(box()).toHaveAttribute("readonly");
    await userEvent.type(box(), "{Control>}{Enter}{/Control}");

    release();
    await screen.findByText("Accepted by baseline");
    expect(posts).toBe(1);
    expect(send()).toBeEnabled();
  });
});

describe("the result", () => {
  it("shows what the cascade did with an accepted text", async () => {
    serveRouteApi(() => routeResult({ label: "card_declined", confidence: 0.936, tier: "llm", cost_usd: 0.0021, latency_ms: 1210, request_id: 42 }));
    show();
    await route("my card got declined at the store");

    const card = within(result());
    expect(await card.findByRole("heading", { name: "Accepted by llm" })).toBeInTheDocument();
    expect(card.getByText("Result for “my card got declined at the store”")).toBeInTheDocument();
    const facts = Object.fromEntries(
      card.getAllByRole("term").map((term) => [term.textContent, term.nextElementSibling?.textContent]),
    );
    expect(facts).toEqual({
      Label: "card_declined", Confidence: "93%", Tier: "llm", Cost: "$0.0021", Latency: "1.2 s", Request: "#42",
    });
    expect(card.getByRole("link", { name: "See it in the history" })).toHaveAttribute("href", "/history");
    expect(card.queryByRole("link", { name: "Open the review queue" })).not.toBeInTheDocument();
  });

  it("points a text that waits for a person to the review queue", async () => {
    serveRouteApi(() => routeResult({ action: "human_review", tier: "llm", label: "freeze_account", confidence: 0.61 }));
    show();
    await route("block it maybe");

    const card = within(result());
    expect(await card.findByRole("heading", { name: "Sent to a person" })).toBeInTheDocument();
    expect(card.getByText(/waits for a person/)).toBeInTheDocument();
    expect(card.getByRole("link", { name: "Open the review queue" })).toHaveAttribute("href", "/review");
    expect(card.getByText("freeze_account")).toBeInTheDocument();
  });

  it("says when no tier could answer, without a 0% confidence", async () => {
    serveRouteApi(() => routeResult({ action: "human_review", tier: null, label: null, confidence: 0, degraded: true }));
    show();
    await route("anything");

    const card = within(result());
    expect(await card.findByRole("heading", { name: "Sent to a person: no tier could answer" })).toBeInTheDocument();
    expect(card.getByText("n/a")).toBeInTheDocument();
    expect(card.queryByText("0%")).not.toBeInTheDocument();
    expect(card.getByText("A tier failed while this text was routed.")).toBeInTheDocument();
  });

  it("warns about a failed tier even when the text was accepted", async () => {
    serveRouteApi(() => routeResult({ degraded: true }));
    show();
    await route("hello");
    expect(await screen.findByText("A tier failed while this text was routed.")).toBeInTheDocument();
  });

  it("shortens a long text in the heading of the result", async () => {
    serveRouteApi();
    show();
    await route("word ".repeat(60));
    const about = await screen.findByText(/^Result for /);
    expect(about.textContent?.length).toBeLessThan(110);
    expect(about).toHaveTextContent("…");
  });

  it("shows only the newest result", async () => {
    serveRouteApi((text) => routeResult({ label: text === "first" ? "damaged_card" : "report_fraud", request_id: text === "first" ? 1 : 2 }));
    show();
    await route("first");
    await within(result()).findByText("#1");
    await route("second");
    await within(result()).findByText("#2");
    expect(within(result()).queryByText("#1")).not.toBeInTheDocument();
  });
});

describe("problems", () => {
  it("explains a refused text and keeps it", async () => {
    serveRouteApi(() => HttpResponse.json({ detail: [{ msg: "too long" }] }, { status: 422 }));
    show();
    await route("hello");
    expect(await screen.findByRole("alert")).toHaveTextContent("The text must have between 1 and 5,000 characters.");
    expect(box()).toHaveValue("hello");
  });

  it("asks to try again after a server error, never shows its message, and recovers", async () => {
    const api = serveRouteApi(() => HttpResponse.json({ detail: "Traceback (most recent call last)" }, { status: 500 }));
    show();
    await route("hello");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/try again/i);
    expect(alert).not.toHaveTextContent("Traceback");
    expect(api.texts).toEqual(["hello"]); // one try, not retried by itself

    api.respond = () => routeResult();
    await userEvent.click(send());
    expect(await screen.findByText("Accepted by baseline")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("copes with the API being unreachable", async () => {
    server.use(http.post("*/route", () => HttpResponse.error()));
    show();
    await route("hello");
    expect(await screen.findByRole("alert")).toHaveTextContent(/check that the API is running/);
    expect(send()).toBeEnabled();
  });

  it("clears the problem when the next try starts", async () => {
    const api = serveRouteApi(() => HttpResponse.json({ detail: "boom" }, { status: 500 }));
    show();
    await route("hello");
    await screen.findByRole("alert");
    api.respond = () => routeResult();
    await userEvent.click(send());
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
});

describe("what was tried on this screen", () => {
  it("lists nothing until there is more than the result itself to show", async () => {
    serveRouteApi();
    show();
    await route("first");
    await screen.findByText("Accepted by baseline");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("lists the texts, newest first", async () => {
    serveRouteApi((text) => routeResult({ action: text === "second" ? "human_review" : "accepted", request_id: text === "first" ? 1 : 2 }));
    show();
    await route("first");
    await within(result()).findByText("#1");
    await route("second");
    await within(result()).findByText("#2");

    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("second");
    expect(rows[0]).toHaveTextContent("Sent to a person");
    expect(rows[1]).toHaveTextContent("first");
    expect(rows[1]).toHaveTextContent("Accepted by baseline");
  });

  it("keeps the last ten", async () => {
    serveRouteApi();
    show();
    for (let i = 1; i <= 12; i += 1) {
      await route(`text ${i}`);
      await within(result()).findByText(`#${i}`);
    }
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(10);
    expect(rows[0]).toHaveTextContent("text 12");
    expect(rows[9]).toHaveTextContent("text 3");
  });

  it("says that the list goes away when the screen is left", async () => {
    serveRouteApi();
    show();
    await route("a");
    await within(result()).findByText("#1");
    await route("b");
    await within(result()).findByText("#2");
    expect(screen.getByText(/cleared when you leave/)).toBeInTheDocument();
  });

  it("starts empty when the screen is opened again", async () => {
    serveRouteApi();
    const first = show();
    await route("a");
    await screen.findByText("Accepted by baseline");
    first.unmount();

    show();
    expect(screen.queryByText("Accepted by baseline")).not.toBeInTheDocument();
    expect(box()).toHaveValue("");
  });
});

describe("the examples", () => {
  const EXAMPLES = ["my card got declined at the store", "please freeze my account"];
  const buttons = () => within(screen.getByRole("group", { name: "Example texts" })).getAllByRole("button");

  it("offers the examples of the config as buttons", async () => {
    serveConfig(EXAMPLES);
    show();
    expect(await screen.findByRole("group", { name: "Example texts" })).toBeInTheDocument();
    expect(buttons().map((b) => b.textContent)).toEqual(EXAMPLES);
  });

  it.each([[[]], [undefined]])("shows nothing when the config has no examples (%j)", async (examples) => {
    serveConfig(examples as string[] | undefined);
    show();
    await screen.findByRole("heading", { level: 1, name: "Try it" });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("group", { name: "Example texts" })).not.toBeInTheDocument();
  });

  it("shows nothing, and the screen still works, when the config cannot be loaded", async () => {
    server.use(http.get("*/config", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    const api = serveRouteApi();
    show();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("group", { name: "Example texts" })).not.toBeInTheDocument();
    await route("hello");
    expect(await screen.findByText("Accepted by baseline")).toBeInTheDocument();
    expect(api.texts).toEqual(["hello"]);
  });

  it("puts an example in the box and moves the focus there, without sending it", async () => {
    serveConfig(EXAMPLES);
    const api = serveRouteApi();
    show();
    await userEvent.click((await screen.findByRole("button", { name: EXAMPLES[0] as string })));

    expect(box()).toHaveValue(EXAMPLES[0]);
    expect(box()).toHaveFocus();
    expect(screen.getByText(`${(EXAMPLES[0] as string).length} / 5,000`)).toBeInTheDocument();
    expect(send()).toBeEnabled();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(api.texts).toHaveLength(0);
  });

  it("replaces what was typed", async () => {
    serveConfig(EXAMPLES);
    show();
    await userEvent.type(box(), "something else");
    await userEvent.click(await screen.findByRole("button", { name: EXAMPLES[1] as string }));
    expect(box()).toHaveValue(EXAMPLES[1]);
  });

  it("sends the example when the person decides to", async () => {
    serveConfig(EXAMPLES);
    const api = serveRouteApi();
    show();
    await userEvent.click(await screen.findByRole("button", { name: EXAMPLES[0] as string }));
    await userEvent.click(send());
    await screen.findByText("Accepted by baseline");
    expect(api.texts).toEqual([EXAMPLES[0]]);
  });

  it("can be changed after it was put in the box", async () => {
    serveConfig(EXAMPLES);
    const api = serveRouteApi();
    show();
    await userEvent.click(await screen.findByRole("button", { name: EXAMPLES[0] as string }));
    await userEvent.type(box(), " yesterday");
    await userEvent.click(send());
    await screen.findByText("Accepted by baseline");
    expect(api.texts).toEqual([`${EXAMPLES[0]} yesterday`]);
  });

  it("cannot be used while a text is on its way", async () => {
    serveConfig(EXAMPLES);
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => (release = resolve));
    server.use(
      http.post("*/route", async () => {
        await gate;
        return HttpResponse.json(routeResult());
      }),
    );
    show();
    await screen.findByRole("group", { name: "Example texts" });
    await userEvent.type(box(), "hello");
    await userEvent.click(send());

    await screen.findByRole("button", { name: "Routing…" });
    buttons().forEach((button) => expect(button).toBeDisabled());

    release();
    await screen.findByText("Accepted by baseline");
    buttons().forEach((button) => expect(button).toBeEnabled());
  });
});
