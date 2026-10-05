import type { TimeseriesParams } from "../api/endpoints";

export type ChartRange = "24h" | "7d" | "30d";
export type Bucket = "hour" | "day";

/** Each range has the bucket size that reads well: 24 hourly bars, 7 or 30 daily ones. */
export const CHART_RANGES: { key: ChartRange; label: string; bucket: Bucket; ms: number }[] = [
  { key: "24h", label: "Last 24 hours", bucket: "hour", ms: 24 * 3_600_000 },
  { key: "7d", label: "Last 7 days", bucket: "day", ms: 7 * 24 * 3_600_000 },
  { key: "30d", label: "Last 30 days", bucket: "day", ms: 30 * 24 * 3_600_000 },
];

export function bucketOf(range: ChartRange): Bucket {
  return CHART_RANGES.find((item) => item.key === range)?.bucket ?? "hour";
}

/** The request parameters for a range. The API aligns `since` to the start of its bucket. */
export function paramsFor(range: ChartRange, now: number = Date.now()): TimeseriesParams {
  const found = CHART_RANGES.find((item) => item.key === range) ?? CHART_RANGES[0];
  return {
    bucket: found?.bucket,
    since: new Date(now - (found?.ms ?? 0)).toISOString(),
    until: new Date(now).toISOString(),
  };
}
