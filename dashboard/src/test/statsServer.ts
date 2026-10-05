import { HttpResponse, http } from "msw";

import type { RetryResult, Stats } from "../api/endpoints";
import { server } from "./server";

export function statsFixture(overrides: Partial<Stats> = {}): Stats {
  return {
    requests: 200,
    accepted_by_tier: { baseline: 96, llm: 102 },
    human_review: 2,
    review: { pending: 1, resolved: 1 },
    reviewer_agreement: { resolved: 1, agreed: 1, rate: 1 },
    degraded: 0,
    cost_usd: 0.00216,
    latency_ms: { avg: 332.5, p95: 1101 },
    delivery: { pending: 0, sent: 198, failed: 0, retryable: 0 },
    ...overrides,
  };
}

export type FakeStatsApi = {
  /** The totals the fake API answers with. Change them to simulate a different day. */
  stats: Stats;
  /** URL of every GET /stats. */
  reads: URL[];
  /** What POST /deliveries/retry answers. */
  retryResult: RetryResult;
  /** Number of POST /deliveries/retry calls. */
  retries: () => number;
};

/** A small fake of the numbers part of the API: GET /config, GET /stats and POST /deliveries/retry. */
export function serveStatsApi({
  stats = statsFixture(),
  targetType = "mock_erp",
}: { stats?: Stats; targetType?: string | null } = {}): FakeStatsApi {
  let retryCalls = 0;
  const api: FakeStatsApi = {
    stats,
    reads: [],
    retryResult: { retried: 2, sent: 2, failed: 0 },
    retries: () => retryCalls,
  };
  server.use(
    http.get("*/config", () =>
      HttpResponse.json({ domain: "demo", task: null, labels: [], tiers: [], target_type: targetType }),
    ),
    http.get("*/stats", ({ request }) => {
      api.reads.push(new URL(request.url));
      return HttpResponse.json(api.stats);
    }),
    http.post("*/deliveries/retry", () => {
      retryCalls += 1;
      return HttpResponse.json(api.retryResult);
    }),
  );
  return api;
}
