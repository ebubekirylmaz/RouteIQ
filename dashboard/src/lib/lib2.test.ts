import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import spec from "../../openapi.json";
import { REVIEWER_AGREEMENT_CAVEAT, REVIEWER_AGREEMENT_HELP } from "./copy";
import { formatCost, formatCostPer1k, formatCount, formatLatency, formatLatencyTick, formatShare } from "./format";
import { describeRetryError, describeRetryResult } from "./retry";
import { STATS_WINDOWS, sinceFor } from "./windows";

describe("formatCost", () => {
  it.each([
    [0, "$0.00"],
    [0.00216, "$0.0022"],
    [0.0118, "$0.0118"],
    [0.5, "$0.5000"],
    [1, "$1.00"],
    [12.345, "$12.35"],
    [1234.5, "$1234.50"],
  ])("shows %s as %s", (value, expected) => {
    expect(formatCost(value)).toBe(expected);
  });

  it("never lets a tiny amount read as free", () => {
    expect(formatCost(0.00000042)).toBe("<$0.0001");
    expect(formatCost(0.0001)).toBe("$0.0001");
  });

  it.each([null, undefined, Number.NaN])("says n/a for %s", (value) => {
    expect(formatCost(value)).toBe("n/a");
  });
});

describe("formatCostPer1k", () => {
  it("scales to a thousand requests", () => {
    expect(formatCostPer1k(0.00216, 200)).toBe("$0.0108");
    expect(formatCostPer1k(2.5, 1000)).toBe("$2.50");
  });

  it("is n/a without requests, instead of dividing by zero", () => {
    expect(formatCostPer1k(0, 0)).toBe("n/a");
    expect(formatCostPer1k(1, -1)).toBe("n/a");
  });
});

describe("formatLatency", () => {
  it.each([
    [0.2, "<1 ms"],
    [1, "1 ms"],
    [332.5, "333 ms"],
    [999.4, "999 ms"],
    [1000, "1.0 s"],
    [1101, "1.1 s"],
    [2429.6, "2.4 s"],
    [75000, "75.0 s"],
  ])("shows %s ms as %s", (value, expected) => {
    expect(formatLatency(value)).toBe(expected);
  });

  it.each([null, undefined, Number.NaN])("says n/a for %s", (value) => {
    expect(formatLatency(value)).toBe("n/a");
  });
});

describe("formatShare", () => {
  it("shows one decimal", () => {
    expect(formatShare(2, 200)).toBe("1.0%");
    expect(formatShare(1, 3)).toBe("33.3%");
    expect(formatShare(200, 200)).toBe("100.0%");
    expect(formatShare(0, 200)).toBe("0.0%");
  });

  it("is n/a when there is nothing to divide", () => {
    expect(formatShare(0, 0)).toBe("n/a");
  });
});

describe("formatCount", () => {
  it("adds thousands separators", () => {
    expect(formatCount(0)).toBe("0");
    expect(formatCount(999)).toBe("999");
    expect(formatCount(12345)).toBe("12,345");
    expect(formatCount(1234567)).toBe("1,234,567");
  });
});

describe("time windows", () => {
  const now = Date.parse("2026-10-05T12:00:00Z");

  it("offers 24 hours, 7 days and all time", () => {
    expect(STATS_WINDOWS.map((item) => item.key)).toEqual(["24h", "7d", "all"]);
  });

  it("starts a day or a week before now", () => {
    expect(sinceFor("24h", now)).toBe("2026-10-04T12:00:00.000Z");
    expect(sinceFor("7d", now)).toBe("2026-09-28T12:00:00.000Z");
  });

  it("has no start for all time", () => {
    expect(sinceFor("all", now)).toBeUndefined();
  });

  it("uses the current time when none is given", () => {
    const since = Date.parse(sinceFor("24h") ?? "");
    expect(Math.abs(Date.now() - since - 24 * 3_600_000)).toBeLessThan(2000);
  });
});

describe("describeRetryResult", () => {
  it("says how many deliveries were sent and how many failed again", () => {
    expect(describeRetryResult({ retried: 5, sent: 3, failed: 2 })).toBe("Retried 5 deliveries: 3 sent, 2 failed.");
  });

  it("uses the singular for one", () => {
    expect(describeRetryResult({ retried: 1, sent: 1, failed: 0 })).toBe("Retried 1 delivery: 1 sent, 0 failed.");
  });

  it("says so when there was nothing to resend", () => {
    expect(describeRetryResult({ retried: 0, sent: 0, failed: 0 })).toBe("Nothing needed to be resent.");
  });
});

describe("describeRetryError", () => {
  it("explains a missing target", () => {
    expect(describeRetryError(new ApiError(409, "no delivery target configured"))).toBe(
      "No delivery target is configured.",
    );
  });

  it.each([new ApiError(500, "boom"), new TypeError("Failed to fetch"), null])(
    "asks to try again for %s",
    (error) => {
      expect(describeRetryError(error)).toMatch(/try again/);
    },
  );

  it("never shows the raw API message", () => {
    expect(describeRetryError(new ApiError(500, "Traceback (most recent call last)"))).not.toMatch(/Traceback/);
  });
});

describe("reviewer agreement wording", () => {
  const schemaText = (spec as { components: { schemas: { ReviewerAgreement: { properties: { rate: { description: string } } } } } })
    .components.schemas.ReviewerAgreement.properties.rate.description;

  it("is the API's own description, word for word", () => {
    expect(REVIEWER_AGREEMENT_HELP).toBe(schemaText);
  });

  it("says plainly that it is not accuracy, next to the number", () => {
    expect(REVIEWER_AGREEMENT_CAVEAT).toMatch(/not the model's accuracy/i);
    expect(REVIEWER_AGREEMENT_HELP).toMatch(/NOT the model's overall accuracy/);
  });
});

describe("formatLatencyTick", () => {
  it("reads the origin of the axis as 0", () => {
    expect(formatLatencyTick(0)).toBe("0");
  });

  it("reads everything else like a latency", () => {
    expect(formatLatencyTick(250)).toBe("250 ms");
    expect(formatLatencyTick(1000)).toBe("1.0 s");
    expect(formatLatencyTick(0.5)).toBe("<1 ms");
  });
});
