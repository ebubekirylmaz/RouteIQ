import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { getStats } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { sinceFor, type StatsWindow } from "../lib/windows";

export const STATS_POLL_MS = 30_000;

/**
 * Totals for a time window. While another window loads, the previous numbers stay on screen.
 *
 * `since` is worked out when the request is made, not when the component renders: a key that
 * contained the current time would change on every render and the query would never settle.
 * It also means a "last 24 hours" window keeps rolling forward with each refresh.
 */
export function useStats(window: StatsWindow) {
  return useQuery({
    queryKey: queryKeys.statsWindow(window),
    queryFn: ({ signal }) => getStats(sinceFor(window), signal),
    refetchInterval: STATS_POLL_MS,
    placeholderData: keepPreviousData,
  });
}
