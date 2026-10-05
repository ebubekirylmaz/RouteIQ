import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { listRequests } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import { toRequestFilters, type HistoryFilters } from "../lib/history";

/**
 * One page of the history, newest first. `page` starts at 1.
 *
 * It does not refresh by itself, and not when the tab gets focus either: new requests push the
 * rows down, and a list that moves while somebody reads it is hard to use. The screen has a
 * Refresh button instead. Deciding a request or resending deliveries does refresh it.
 */
export function useRequests(filters: HistoryFilters, page: number) {
  const request = toRequestFilters(filters, page);
  return useQuery({
    queryKey: queryKeys.requestsPage(request),
    queryFn: ({ signal }) => listRequests(request, signal),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}
