/**
 * One place for the cache keys. `["review"]` is a prefix: invalidating it refreshes every page
 * of the review queue, whatever its limit and offset.
 */
export const queryKeys = {
  config: ["config"] as const,
  review: ["review"] as const,
  stats: ["stats"] as const,
  statsWindow: (window: string) => ["stats", window] as const,
  timeseriesAll: ["timeseries"] as const,
  timeseries: (range: string) => ["timeseries", range] as const,
  requests: ["requests"] as const,
  requestsPage: (request: object) => ["requests", request] as const,
  reviewPage: (limit: number, offset: number) => ["review", { limit, offset }] as const,
};
