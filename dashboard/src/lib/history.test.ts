import { describe, expect, it } from "vitest";

import { formatTimestamp, truncate } from "./format";
import {
  HISTORY_PAGE_SIZE,
  buildHistoryParams,
  hasActiveFilters,
  parseHistoryParams,
  toRequestFilters,
} from "./history";
import { describeConfidence, describeDelivery, describeLabel, describeOutcome } from "./requestView";

const parse = (query: string) => parseHistoryParams(new URLSearchParams(query));

describe("parseHistoryParams", () => {
  it("has no filters and the first page for a bare address", () => {
    expect(parse("")).toEqual({ filters: {}, page: 1 });
  });

  it("reads every filter", () => {
    expect(parse("action=human_review&review=pending&delivery=failed&degraded=1&tier=llm&q=wallet&page=3")).toEqual({
      filters: {
        action: "human_review", review_status: "pending", delivery_status: "failed",
        degraded: true, tier: "llm", q: "wallet",
      },
      page: 3,
    });
  });

  it.each([
    "action=maybe", "review=done", "delivery=lost", "degraded=0", "degraded=true", "degraded=", "tier=", "q=", "q=%20%20",
  ])("drops an invalid or empty value (%s)", (query) => {
    expect(parse(query).filters).toEqual({});
  });

  it.each(["page=0", "page=-2", "page=abc", "page=1.5", "page=", "page=NaN"])("treats %s as the first page", (query) => {
    expect(parse(query).page).toBe(1);
  });

  it("trims the search text and caps its length", () => {
    expect(parse("q=%20%20wallet%20%20").filters.q).toBe("wallet");
    expect(parse(`q=${"x".repeat(300)}`).filters.q).toHaveLength(200);
  });

  it("drops a tier that is too long", () => {
    expect(parse(`tier=${"x".repeat(51)}`).filters.tier).toBeUndefined();
  });

  it("ignores parameters it does not know", () => {
    expect(parse("utm_source=mail&foo=bar")).toEqual({ filters: {}, page: 1 });
  });

  it("is not fooled by a repeated parameter: the first one wins", () => {
    expect(parse("action=accepted&action=human_review").filters.action).toBe("accepted");
  });
});

describe("buildHistoryParams", () => {
  it("is empty for no filters on the first page", () => {
    expect(buildHistoryParams({}).toString()).toBe("");
    expect(buildHistoryParams({}, 1).toString()).toBe("");
  });

  it("writes the filters under the short names", () => {
    const params = buildHistoryParams({ action: "accepted", review_status: "resolved", delivery_status: "sent", degraded: true, tier: "llm", q: "a b" }, 2);
    expect(Object.fromEntries(params)).toEqual({
      action: "accepted", review: "resolved", delivery: "sent", degraded: "1", tier: "llm", q: "a b", page: "2",
    });
  });

  it("leaves out the page when it is the first", () => {
    expect(buildHistoryParams({ q: "x" }, 1).has("page")).toBe(false);
  });

  it("round-trips through the parser", () => {
    const filters = { action: "human_review", delivery_status: "failed", degraded: true, q: "50% & more" } as const;
    expect(parseHistoryParams(buildHistoryParams(filters, 4))).toEqual({ filters, page: 4 });
  });

  it("encodes a search text with special characters", () => {
    expect(buildHistoryParams({ q: "50% & more" }).toString()).toContain("q=50%25+%26+more");
  });
});

describe("hasActiveFilters", () => {
  it("is false without filters", () => {
    expect(hasActiveFilters({})).toBe(false);
    expect(hasActiveFilters({ q: undefined })).toBe(false);
  });

  it("is true with any filter", () => {
    expect(hasActiveFilters({ degraded: true })).toBe(true);
    expect(hasActiveFilters({ q: "x" })).toBe(true);
  });
});

describe("toRequestFilters", () => {
  it("asks for the first page, newest first", () => {
    expect(toRequestFilters({})).toEqual({ limit: HISTORY_PAGE_SIZE, offset: 0, order: "newest" });
  });

  it("turns a page number into an offset", () => {
    expect(toRequestFilters({}, 3).offset).toBe(2 * HISTORY_PAGE_SIZE);
  });

  it("keeps the filters", () => {
    expect(toRequestFilters({ action: "accepted", q: "x", degraded: true }, 1)).toMatchObject({
      action: "accepted", q: "x", degraded: true,
    });
  });
});

const item = (overrides: Record<string, unknown> = {}) =>
  ({
    id: 1, created_at: "2026-10-05T14:02:07Z", text: "hello", label: "report_fraud", confidence: 0.9, tier: "baseline",
    action: "accepted", cost_usd: 0, latency_ms: 1, degraded: false, review_status: null, final_label: null,
    resolved_at: null, delivery_status: null, delivery_error: null, delivered_at: null, ...overrides,
  }) as Parameters<typeof describeOutcome>[0];

describe("describeOutcome", () => {
  it("names the tier that accepted a request", () => {
    expect(describeOutcome(item({ tier: "llm" }))).toBe("Accepted by llm");
  });

  it("tells the three states of a request sent to a person apart", () => {
    expect(describeOutcome(item({ action: "human_review", review_status: "pending" }))).toBe("Waiting for a person");
    expect(describeOutcome(item({ action: "human_review", review_status: "resolved", final_label: "a" }))).toBe("Decided by a person");
    expect(describeOutcome(item({ action: "human_review", review_status: null }))).toBe("Sent to a person");
  });

  it("copes with an accepted request without a tier", () => {
    expect(describeOutcome(item({ tier: null }))).toBe("Accepted by the cascade");
  });
});

describe("describeLabel", () => {
  it("shows the label of an accepted request without a note", () => {
    expect(describeLabel(item())).toEqual({ label: "report_fraud", note: null });
  });

  it("calls the model's label a suggestion while a person has not decided", () => {
    expect(describeLabel(item({ action: "human_review", review_status: "pending" }))).toEqual({
      label: "report_fraud", note: "suggestion",
    });
  });

  it("says there was no suggestion when the model had none", () => {
    expect(describeLabel(item({ action: "human_review", review_status: "pending", label: null }))).toEqual({
      label: "no suggestion", note: null,
    });
  });

  it("shows the person's label, and says when it differs from the model's", () => {
    expect(describeLabel(item({ action: "human_review", review_status: "resolved", final_label: "out_of_scope", label: "report_fraud" }))).toEqual({
      label: "out_of_scope", note: "model suggested report_fraud",
    });
  });

  it("says when the person kept the model's label", () => {
    expect(describeLabel(item({ action: "human_review", review_status: "resolved", final_label: "report_fraud" }))).toEqual({
      label: "report_fraud", note: "kept the model's label",
    });
  });

  it("copes with a person deciding where the model had nothing to offer", () => {
    expect(describeLabel(item({ action: "human_review", review_status: "resolved", final_label: "a", label: null })).note).toBe(
      "model suggested nothing",
    );
  });
});

describe("describeDelivery", () => {
  it.each([
    ["sent", "Sent", "ok"],
    ["failed", "Failed", "bad"],
    ["pending", "Pending", "neutral"],
  ])("reads %s as %s", (status, text, tone) => {
    expect(describeDelivery(item({ delivery_status: status }))).toEqual({ text, tone });
  });

  it("says a request waiting for a person has not been sent yet", () => {
    expect(describeDelivery(item({ action: "human_review", review_status: "pending" })).text).toBe("Not sent yet");
  });

  it("says plainly when a request was not sent", () => {
    expect(describeDelivery(item()).text).toBe("Not sent");
  });
});

describe("describeConfidence", () => {
  it("shows the confidence as a whole percentage", () => {
    expect(describeConfidence(item({ confidence: 0.936 }))).toBe("93%");
  });

  it("says n/a, not 0%, when no tier produced a label", () => {
    expect(describeConfidence(item({ label: null, confidence: 0 }))).toBe("n/a");
  });

  it("says n/a when the confidence is missing", () => {
    expect(describeConfidence(item({ confidence: null }))).toBe("n/a");
  });
});

describe("formatTimestamp", () => {
  it("reads a time in UTC", () => {
    expect(formatTimestamp("2026-10-05T14:02:07Z")).toBe("Oct 5, 14:02:07 UTC");
  });

  it("reads another offset in UTC", () => {
    expect(formatTimestamp("2026-10-05T17:02:07+03:00")).toBe("Oct 5, 14:02:07 UTC");
  });

  it("shows midnight as 00:00:00, not 24:00:00", () => {
    expect(formatTimestamp("2026-10-05T00:00:00Z")).toBe("Oct 5, 00:00:00 UTC");
  });

  it.each([null, undefined, "", "not a date"])("says n/a for %s", (value) => {
    expect(formatTimestamp(value)).toBe("n/a");
  });
});

describe("truncate", () => {
  it("leaves a short text alone", () => {
    expect(truncate("short", 20)).toBe("short");
    expect(truncate("exactly ten", 11)).toBe("exactly ten");
  });

  it("cuts on a word boundary and marks the cut", () => {
    expect(truncate("alpha beta gamma delta epsilon", 20)).toBe("alpha beta gamma…");
  });

  it("keeps the last whole word when the cut falls right after it", () => {
    expect(truncate("the quick brown fox jumps", 15)).toBe("the quick brown…");
  });

  it("cuts in the middle of a very long word when there is no boundary", () => {
    expect(truncate("x".repeat(50), 10)).toBe(`${"x".repeat(10)}…`);
  });

  it("never returns more than max characters plus the mark", () => {
    expect(truncate("word ".repeat(40), 30).length).toBeLessThanOrEqual(31);
  });
});
