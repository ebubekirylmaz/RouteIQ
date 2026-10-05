import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { listReview } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";

export const REVIEW_POLL_MS = 10_000;
export const DEFAULT_PAGE_SIZE = 20;

/**
 * One page of the review queue, oldest first. `page` starts at 0.
 *
 * The queue is refreshed while the tab is visible, so a request that other people resolve
 * disappears without a reload. While the next page loads, the previous one stays on screen.
 */
export function useReviewQueue(page: number, pageSize: number = DEFAULT_PAGE_SIZE) {
  const offset = page * pageSize;
  return useQuery({
    queryKey: queryKeys.reviewPage(pageSize, offset),
    queryFn: ({ signal }) => listReview(pageSize, offset, signal),
    refetchInterval: REVIEW_POLL_MS,
    placeholderData: keepPreviousData,
  });
}
