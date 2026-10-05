import { useMutation, useQueryClient } from "@tanstack/react-query";

import { retryDeliveries, type RetryResult } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";

/**
 * Sends failed deliveries (and ones stuck in pending) again, up to 100 at a time. The totals are
 * refreshed afterwards whatever the outcome, so the counts on screen match what happened.
 */
export function useRetryDeliveries(onDone?: (result: RetryResult | Error) => void) {
  const client = useQueryClient();
  return useMutation<RetryResult, Error, void>({
    mutationFn: () => retryDeliveries(),
    onSuccess: (result) => onDone?.(result),
    onError: (error) => onDone?.(error),
    onSettled: () => client.invalidateQueries({ queryKey: queryKeys.stats }),
  });
}
