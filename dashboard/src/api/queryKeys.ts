/**
 * One place for the cache keys. `["review"]` is a prefix: invalidating it refreshes every page
 * of the review queue, whatever its limit and offset.
 */
export const queryKeys = {
  config: ["config"] as const,
  review: ["review"] as const,
  stats: ["stats"] as const,
  statsWindow: (window: string) => ["stats", window] as const,
  timeseries: (range: string) => ["timeseries", range] as const,
  reviewPage: (limit: number, offset: number) => ["review", { limit, offset }] as const,
};
