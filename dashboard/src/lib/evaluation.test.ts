import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { evaluationReport } from "../test/evaluationServer";
import {
  accuracyRows, binRange, describeGroup, formatAccuracy, formatInterval, isNotAvailable, pointsPerMistake,
} from "./evaluation";

describe("formatAccuracy", () => {
  it.each([
    [0.9833, "98.3%"],
    [1, "100.0%"],
    [0, "0.0%"],
    [0.917, "91.7%"],
    [0.5, "50.0%"],
  ])("shows %s as %s", (value, text) => {
    expect(formatAccuracy(value)).toBe(text);
  });
});

describe("formatInterval", () => {
  it("names both ends", () => {
    expect(formatInterval(0.962, 0.993)).toBe("96.2% to 99.3%");
  });
});

describe("pointsPerMistake", () => {
  it.each([[300, "0.3"], [100, "1.0"], [10, "10.0"]])("is %s examples -> %s points", (n, text) => {
    expect(pointsPerMistake(n)).toBe(text);
  });

  it("does not divide by zero", () => {
    expect(pointsPerMistake(0)).toBe("n/a");
  });
});

describe("accuracyRows", () => {
  const rows = accuracyRows(evaluationReport().setups);

  it("has a row for every setup, in order", () => {
    expect(rows.map((row) => row.name)).toEqual([
      "Baseline only", "LLM only", "Cascade (baseline then LLM)", "Cascade + human review",
    ]);
  });

  it("uses percent as the unit, like the axis", () => {
    expect(rows[1]?.accuracy).toBeCloseTo(98.33);
  });

  it("gives the error bar the distance down and up to the interval", () => {
    const [down, up] = rows[1]?.error ?? [0, 0];
    expect(down).toBeCloseTo((0.9833 - 0.962) * 100);
    expect(up).toBeCloseTo((0.993 - 0.9833) * 100);
    expect(rows.every((row) => row.error[0] >= 0 && row.error[1] >= 0)).toBe(true);
  });

  it("marks only the setup that assumes a perfect reviewer", () => {
    expect(rows.map((row) => row.assumesReviewer)).toEqual([false, false, false, true]);
  });

  it("writes the figure and its interval for the tooltip", () => {
    expect(rows[1]?.label).toBe("98.3% (96.2% to 99.3%)");
  });
});

describe("describeGroup", () => {
  const groups = evaluationReport().cascade.groups;

  it("names the tier that accepted the examples and how many were right", () => {
    expect(describeGroup(groups[1]!, 300)).toEqual({
      outcome: "Accepted by llm", count: 155, share: "51.7%", right: "153 of 155", note: null,
    });
  });

  it("says that for people the figure is the model's suggestion", () => {
    expect(describeGroup(groups[2]!, 300)).toEqual({
      outcome: "Sent to a person", count: 6, share: "2.0%", right: "3 of 6", note: "the model's suggestion",
    });
  });

  it("says n/a for a group nobody was in", () => {
    expect(describeGroup({ kind: "accepted", tier: "llm", count: 0, correct: 0 }, 300).right).toBe("n/a");
  });

  it("copes with an accepted group without a tier", () => {
    expect(describeGroup({ kind: "accepted", tier: null, count: 1, correct: 1 }, 10).outcome).toBe("Accepted by the cascade");
  });
});

describe("binRange", () => {
  it.each([
    [{ lower: 0, upper: 0.5 }, "0% to 50%"],
    [{ lower: 0.7, upper: 0.9 }, "70% to 90%"],
    [{ lower: 0.99, upper: 1 }, "99% to 100%"],
  ])("reads %j as %s", (bin, text) => {
    expect(binRange({ ...bin, n: 1, mean_confidence: 0, accuracy: 0 })).toBe(text);
  });
});

describe("isNotAvailable", () => {
  it("is true only for a 404 from the API", () => {
    expect(isNotAvailable(new ApiError(404, "no evaluation"))).toBe(true);
    expect(isNotAvailable(new ApiError(500, "boom"))).toBe(false);
    expect(isNotAvailable(new TypeError("Failed to fetch"))).toBe(false);
    expect(isNotAvailable(null)).toBe(false);
  });
});
