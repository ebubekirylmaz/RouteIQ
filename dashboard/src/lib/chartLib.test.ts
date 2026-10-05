import { describe, expect, it } from "vitest";

import { bucketLabel, bucketTitle, hasRequests, toChartPoints } from "./chartData";
import { CHART_RANGES, bucketOf, paramsFor } from "./chartRanges";

const point = (start: string, requests: number, cost = 0, latency = 0) => ({
  start,
  requests,
  accepted: requests,
  human_review: 0,
  cost_usd: cost,
  avg_latency_ms: latency,
});

describe("chart ranges", () => {
  it("offers 24 hours, 7 days and 30 days", () => {
    expect(CHART_RANGES.map((item) => item.key)).toEqual(["24h", "7d", "30d"]);
  });

  it("picks the bucket size that reads well", () => {
    expect(bucketOf("24h")).toBe("hour");
    expect(bucketOf("7d")).toBe("day");
    expect(bucketOf("30d")).toBe("day");
  });

  it("asks for a window that ends now", () => {
    const now = Date.parse("2026-10-05T12:00:00Z");
    expect(paramsFor("24h", now)).toEqual({
      bucket: "hour",
      since: "2026-10-04T12:00:00.000Z",
      until: "2026-10-05T12:00:00.000Z",
    });
    expect(paramsFor("30d", now)).toEqual({
      bucket: "day",
      since: "2026-09-05T12:00:00.000Z",
      until: "2026-10-05T12:00:00.000Z",
    });
  });

  it("stays within the API's limit of 1,000 buckets", () => {
    for (const range of CHART_RANGES) {
      const step = range.bucket === "hour" ? 3_600_000 : 86_400_000;
      expect(range.ms / step + 1).toBeLessThanOrEqual(1000);
    }
  });
});

describe("bucket labels", () => {
  it("shows an hour as hours and minutes, in UTC", () => {
    expect(bucketLabel("2026-10-05T14:00:00Z", "hour")).toBe("14:00");
    expect(bucketLabel("2026-10-05T09:00:00Z", "hour")).toBe("09:00");
  });

  it("shows midnight as 00:00, not 24:00", () => {
    expect(bucketLabel("2026-10-05T00:00:00Z", "hour")).toBe("00:00");
  });

  it("shows a day as month and day", () => {
    expect(bucketLabel("2026-10-05T00:00:00Z", "day")).toBe("Oct 5");
    expect(bucketLabel("2026-01-31T00:00:00Z", "day")).toBe("Jan 31");
  });

  it("reads the time in UTC whatever the offset it was written with", () => {
    expect(bucketLabel("2026-10-05T17:00:00+03:00", "hour")).toBe("14:00");
    expect(bucketLabel("2026-10-05T23:00:00-02:00", "day")).toBe("Oct 6");
  });

  it("gives the full time for a tooltip", () => {
    expect(bucketTitle("2026-10-05T14:00:00Z", "hour")).toBe("Oct 5, 14:00 UTC");
    expect(bucketTitle("2026-10-05T00:00:00Z", "day")).toBe("Oct 5 UTC");
  });
});

describe("toChartPoints", () => {
  const points = [
    point("2026-10-05T10:00:00Z", 5, 0.001, 200),
    point("2026-10-05T11:00:00Z", 0),
    point("2026-10-05T12:00:00Z", 3, 0.002, 400),
  ];

  it("keeps the counts and adds labels", () => {
    const [first] = toChartPoints(points, "hour");
    expect(first).toMatchObject({ label: "10:00", title: "Oct 5, 10:00 UTC", requests: 5, accepted: 5, human_review: 0 });
  });

  it("adds the cost up as it goes", () => {
    expect(toChartPoints(points, "hour").map((p) => p.cumulativeCost)).toEqual([0.001, 0.001, 0.003]);
  });

  it("leaves a gap in the latency where there were no requests", () => {
    expect(toChartPoints(points, "hour").map((p) => p.avgLatency)).toEqual([200, null, 400]);
  });

  it("never turns an empty bucket into a latency of zero", () => {
    expect(toChartPoints([point("2026-10-05T11:00:00Z", 0, 0, 0)], "hour")[0]?.avgLatency).toBeNull();
  });

  it("copes with no points", () => {
    expect(toChartPoints([], "day")).toEqual([]);
  });

  it("uses the bucket for the labels", () => {
    expect(toChartPoints(points, "day")[0]?.label).toBe("Oct 5");
  });
});

describe("hasRequests", () => {
  it("is true as soon as one bucket has a request", () => {
    expect(hasRequests([point("a", 0), point("b", 1)])).toBe(true);
  });

  it("is false for buckets without requests, and for none at all", () => {
    expect(hasRequests([point("a", 0), point("b", 0)])).toBe(false);
    expect(hasRequests([])).toBe(false);
  });
});
