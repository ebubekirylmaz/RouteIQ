import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { getTimeseries } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { paramsFor, type ChartRange } from "../lib/chartRanges";

export const TIMESERIES_POLL_MS = 60_000;

/**
 * Per-bucket numbers for a range. As with the totals, the window is worked out when the request
 * is made, so the key stays the same and the chart keeps moving forward with each refresh.
 */
export function useTimeseries(range: ChartRange) {
  return useQuery({
    queryKey: queryKeys.timeseries(range),
    queryFn: ({ signal }) => getTimeseries(paramsFor(range), signal),
    refetchInterval: TIMESERIES_POLL_MS,
    placeholderData: keepPreviousData,
  });
}
