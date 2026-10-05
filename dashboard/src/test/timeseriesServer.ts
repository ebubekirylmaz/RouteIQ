import { HttpResponse, http } from "msw";

import type { Timeseries } from "../api/endpoints";
import { server } from "./server";

type Point = Timeseries["points"][number];

/** `count` consecutive buckets starting at `start`, every one with some requests unless overridden. */
export function makePoints(count: number, bucket: "hour" | "day" = "hour", start = "2026-10-05T00:00:00Z"): Point[] {
  const step = bucket === "hour" ? 3_600_000 : 86_400_000;
  return Array.from({ length: count }, (_, i) => ({
    start: new Date(Date.parse(start) + i * step).toISOString(),
    requests: 10 + i,
    accepted: 9 + i,
    human_review: 1,
    cost_usd: 0.0001,
    avg_latency_ms: 300 + i * 10,
  }));
}

export const emptyPoint = (start: string): Point => ({
  start, requests: 0, accepted: 0, human_review: 0, cost_usd: 0, avg_latency_ms: 0,
});

export type FakeTimeseriesApi = {
  /** What GET /stats/timeseries answers with. Change it to simulate a different day. */
  points: Point[];
  /** URL of every GET /stats/timeseries. */
  reads: URL[];
};

export function serveTimeseriesApi(points: Point[] = makePoints(24)): FakeTimeseriesApi {
  const api: FakeTimeseriesApi = { points, reads: [] };
  server.use(
    http.get("*/stats/timeseries", ({ request }) => {
      const url = new URL(request.url);
      api.reads.push(url);
      const bucket = (url.searchParams.get("bucket") ?? "hour") as "hour" | "day";
      return HttpResponse.json({
        bucket,
        since: url.searchParams.get("since") ?? "2026-10-04T00:00:00Z",
        until: url.searchParams.get("until") ?? "2026-10-05T00:00:00Z",
        points: api.points,
      });
    }),
  );
  return api;
}
