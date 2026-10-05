import { describe, expect, it } from "vitest";

import { formatConfidence, formatWaiting } from "./format";

describe("formatConfidence", () => {
  it.each([
    [0.674, "67%"],
    [0.7, "70%"],
    [0, "0%"],
    [1, "100%"],
    [0.05, "5%"],
  ])("shows %s as %s", (value, expected) => {
    expect(formatConfidence(value)).toBe(expected);
  });

  it("rounds down, so a score is never shown as more certain than it is", () => {
    expect(formatConfidence(0.995)).toBe("99%");
    expect(formatConfidence(0.999)).toBe("99%");
    expect(formatConfidence(0.9999)).toBe("99%");
  });

  it("is not thrown off by floating point", () => {
    expect(0.29 * 100).toBeLessThan(29); // the trap: 28.999999999999996
    expect(formatConfidence(0.29)).toBe("29%");
    expect(formatConfidence(0.57)).toBe("57%");
    expect(formatConfidence(0.58)).toBe("58%");
  });

  it.each([null, undefined, Number.NaN])("says n/a for %s", (value) => {
    expect(formatConfidence(value)).toBe("n/a");
  });
});

describe("formatWaiting", () => {
  const now = Date.parse("2026-10-05T12:00:00Z");
  const ago = (seconds: number) => new Date(now - seconds * 1000).toISOString();

  it.each([
    [0, "just now"],
    [59, "just now"],
    [60, "1 min"],
    [59 * 60 + 59, "59 min"],
    [60 * 60, "1 h"],
    [23 * 3600 + 59 * 60, "23 h"],
    [24 * 3600, "1 d"],
    [10 * 24 * 3600, "10 d"],
  ])("%i seconds ago reads %s", (seconds, expected) => {
    expect(formatWaiting(ago(seconds), now)).toBe(expected);
  });

  it("treats a time in the future (clock skew) as just now", () => {
    expect(formatWaiting(new Date(now + 5000).toISOString(), now)).toBe("just now");
  });

  it("copes with a timestamp that is not a date", () => {
    expect(formatWaiting("not a date", now)).toBe("unknown");
  });

  it("reads a timestamp written with Z or with an offset the same way", () => {
    expect(formatWaiting("2026-10-05T11:55:00Z", now)).toBe("5 min");
    expect(formatWaiting("2026-10-05T14:55:00+03:00", now)).toBe("5 min");
  });

  it("uses the current time when none is given", () => {
    expect(formatWaiting(new Date(Date.now() - 3 * 60_000).toISOString())).toBe("3 min");
  });
});
