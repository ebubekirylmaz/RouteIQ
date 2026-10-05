import type { Timeseries } from "../api/endpoints";
import type { Bucket } from "./chartRanges";

export type ChartPoint = {
  start: string;
  /** Short axis label, in UTC. */
  label: string;
  /** Full time for the tooltip and the table, in UTC. */
  title: string;
  requests: number;
  accepted: number;
  human_review: number;
  cost: number;
  cumulativeCost: number;
  /** null for a bucket without requests: a gap in the line, not a drop to zero. */
  avgLatency: number | null;
};

// The buckets are aligned to UTC, so every time is shown in UTC. Local time would put a day's
// bar on two different calendar days. "h23" keeps midnight as 00:00, not 24:00.
const hourOnly = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const dayOnly = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "short", day: "numeric" });
const dayAndHour = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

export function bucketLabel(iso: string, bucket: Bucket): string {
  const date = new Date(iso);
  return (bucket === "hour" ? hourOnly : dayOnly).format(date);
}

export function bucketTitle(iso: string, bucket: Bucket): string {
  const date = new Date(iso);
  return bucket === "hour" ? `${dayAndHour.format(date)} UTC` : `${dayOnly.format(date)} UTC`;
}

/** Points ready for the charts: labels, a running total of the cost, and gaps where nothing happened. */
export function toChartPoints(points: Timeseries["points"], bucket: Bucket): ChartPoint[] {
  let running = 0;
  return points.map((point) => {
    running += point.cost_usd;
    return {
      start: point.start,
      label: bucketLabel(point.start, bucket),
      title: bucketTitle(point.start, bucket),
      requests: point.requests,
      accepted: point.accepted,
      human_review: point.human_review,
      cost: point.cost_usd,
      cumulativeCost: running,
      avgLatency: point.requests > 0 ? point.avg_latency_ms : null,
    };
  });
}

export function hasRequests(points: Timeseries["points"]): boolean {
  return points.some((point) => point.requests > 0);
}
