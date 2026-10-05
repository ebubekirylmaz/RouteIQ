export type StatsWindow = "24h" | "7d" | "all";

export const STATS_WINDOWS: { key: StatsWindow; label: string; ms: number | null }[] = [
  { key: "24h", label: "Last 24 hours", ms: 24 * 3_600_000 },
  { key: "7d", label: "Last 7 days", ms: 7 * 24 * 3_600_000 },
  { key: "all", label: "All time", ms: null },
];

/** The `since` value for a window, as an ISO time. "All time" has none. */
export function sinceFor(window: StatsWindow, now: number = Date.now()): string | undefined {
  const found = STATS_WINDOWS.find((item) => item.key === window);
  if (!found || found.ms === null) return undefined;
  return new Date(now - found.ms).toISOString();
}
