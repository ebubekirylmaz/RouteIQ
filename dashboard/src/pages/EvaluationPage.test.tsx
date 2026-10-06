import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { evaluationReport, failEvaluation, serveEvaluationApi } from "../test/evaluationServer";
import { server } from "../test/server";
import { renderWithProviders } from "../test/utils";
import { EvaluationPage } from "./EvaluationPage";

async function show(report = evaluationReport()) {
  const api = serveEvaluationApi(report);
  renderWithProviders(<EvaluationPage />, { route: "/evaluation" });
  await screen.findByRole("figure", { name: /^Accuracy/ });
  return api;
}

const row = (table: HTMLElement, name: string | RegExp) =>
  within(table).getByRole("rowheader", { name }).closest("tr") as HTMLElement;

describe("loading", () => {
  it("says it is loading, then shows the evaluation", async () => {
    serveEvaluationApi();
    renderWithProviders(<EvaluationPage />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(await screen.findByRole("figure", { name: /^Accuracy/ })).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading" })).not.toBeInTheDocument();
  });

  it("asks the API once, and does not poll", async () => {
    const api = await show();
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(api.reads).toBe(1);
  });
});

describe("what it says about itself", () => {
  it("says the numbers were measured offline on labeled examples and are not live traffic", async () => {
    await show();
    expect(screen.getByRole("heading", { level: 1, name: "Evaluation" })).toBeInTheDocument();
    const sub = screen.getByText(/Measured offline/);
    expect(sub).toHaveTextContent("test split of “clinc150”");
    expect(sub).toHaveTextContent("300 examples with known labels");
    expect(sub).toHaveTextContent("not live traffic");
  });

  it("warns that synthetic examples say nothing about real data", async () => {
    await show(evaluationReport({ data_source: "synthetic" }));
    expect(screen.getByRole("note")).toHaveTextContent(/synthetic.*nothing about real data/);
  });

  it.each([["public"], [null], ["private"]])("has no synthetic warning for data_source %s", async (source) => {
    await show(evaluationReport({ data_source: source as never }));
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });
});

describe("the accuracy chart", () => {
  it("draws one bar for every setup, each with an interval", async () => {
    await show();
    const figure = screen.getByRole("figure", { name: /^Accuracy/ });
    expect(figure.querySelectorAll(".recharts-bar-rectangle")).toHaveLength(4);
    expect(figure.querySelectorAll(".recharts-errorBar").length).toBeGreaterThanOrEqual(4);
  });

  it("starts its axis at zero", async () => {
    await show();
    const ticks = Array.from(document.querySelectorAll(".recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-value")).map((t) => t.textContent);
    expect(ticks[0]).toBe("0%");
    expect(ticks.at(-1)).toBe("100%");
  });

  it("says what the bars are and that the orange one assumes a perfect reviewer", async () => {
    await show();
    const caption = screen.getByRole("figure", { name: /^Accuracy/ });
    expect(caption).toHaveTextContent("95% interval");
    expect(caption).toHaveTextContent("The orange bar assumes every person is right");
  });
});

describe("the table of the four setups", () => {
  it("lists every setup with the figures of the README", async () => {
    await show();
    const table = screen.getByRole("region", { name: "The four setups" });
    const llm = row(table, /^LLM only/);
    expect(llm).toHaveTextContent("98.3%");
    expect(llm).toHaveTextContent("96.2% to 99.3%");
    expect(llm).toHaveTextContent("0.976");
    expect(llm).toHaveTextContent("$0.0118");
    expect(llm).toHaveTextContent("600 ms");
    expect(llm).toHaveTextContent("2.2 s");
    const cascade = row(table, /^Cascade \(baseline then LLM\)/);
    expect(cascade).toHaveTextContent("$0.0064");
    expect(cascade).toHaveTextContent("559 ms");
    expect(row(table, /^Baseline only/)).toHaveTextContent("$0.00");
  });

  it("says plainly, in the row and in the colour of its text, that the human review figure assumes the people are always right", async () => {
    await show();
    const table = screen.getByRole("region", { name: "The four setups" });
    const human = row(table, /^Cascade \+ human review/);
    expect(human).toHaveTextContent("assumes the person is always right");
    expect(row(table, /^LLM only/)).not.toHaveTextContent("always right");
    expect(within(human).getByText(/assumes the person is always right/).className).toMatch(/assumption/);
    expect(within(row(table, /^LLM only/)).getByText(/answered by the LLM/).className).not.toMatch(/assumption/);
  });

  it("explains how big a difference has to be before it means something", async () => {
    await show();
    const note = screen.getByText(/one more\s+mistake changes/);
    expect(note).toHaveTextContent("With 300 examples");
    expect(note).toHaveTextContent("0.3 points");
    expect(note).toHaveTextContent("can be noise");
  });
});

describe("what the cascade did", () => {
  it("names the thresholds and lists who handled how many examples", async () => {
    await show();
    const section = screen.getByRole("region", { name: "How the cascade handled the examples" });
    expect(section).toHaveTextContent("baseline 0.7, llm 0.9");
    expect(row(section, "Accepted by baseline")).toHaveTextContent("139");
    expect(row(section, "Accepted by baseline")).toHaveTextContent("139 of 139");
    expect(row(section, "Accepted by llm")).toHaveTextContent("153 of 155");
    expect(row(section, "Sent to a person")).toHaveTextContent("3 of 6 (the model's suggestion)");
    expect(row(section, "Sent to a person")).toHaveTextContent("2.0%");
    expect(section).toHaveTextContent("161 examples needed more than one tier");
  });
});

describe("calibration", () => {
  it("explains what it means in plain words", async () => {
    await show();
    const section = screen.getByRole("region", { name: "Calibration" });
    expect(section).toHaveTextContent(/When a tier says it is 90% sure, is it right about 90% of the time/);
  });

  it("gives every tier its ECE and its table of confidence ranges", async () => {
    await show();
    expect(screen.getByRole("heading", { name: "baseline: ECE 0.269" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "llm: ECE 0.012" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Calibration of the baseline tier" });
    const bin = row(table, "50% to 70%");
    expect(bin).toHaveTextContent("87");
    expect(bin).toHaveTextContent("61.0%");
    expect(bin).toHaveTextContent("99.0%");
  });

  it("warns that a range with few examples says little", async () => {
    await show();
    expect(screen.getByText(/fewer than 10 examples says little/)).toBeInTheDocument();
  });
});

describe("when there is nothing to show", () => {
  it("says so, without alarm, when the API has no evaluation for this configuration", async () => {
    failEvaluation(404, "no recorded predictions for the domain 'x'");
    renderWithProviders(<EvaluationPage />);
    expect(await screen.findByText(/No evaluation is available for this configuration/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("figure")).not.toBeInTheDocument();
  });

  it("offers to try again after a failure, never shows the raw message, and recovers", async () => {
    failEvaluation(500, "Traceback (most recent call last)");
    renderWithProviders(<EvaluationPage />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The evaluation could not be loaded.");
    expect(alert).not.toHaveTextContent("Traceback");

    serveEvaluationApi();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("figure", { name: /^Accuracy/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("copes with the API being unreachable", async () => {
    server.use(http.get("*/evaluation", () => HttpResponse.error()));
    renderWithProviders(<EvaluationPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
  });
});
