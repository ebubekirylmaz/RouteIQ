import { useMutation, useQueryClient } from "@tanstack/react-query";

import { resolveReview, type ReviewResolved } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";

export type ResolveVariables = { id: number; label: string };

export type ResolveOutcome =
  | { ok: true; id: number; label: string }
  | { ok: false; id: number; label: string; error: unknown };

/**
 * Records a person's decision. The queue is refreshed whatever the outcome: after a success the
 * request is gone, and after a 409 or 404 somebody else already changed it.
 *
 * `onOutcome` hears about the result even when the row that started the request has already left
 * the list by then (the refresh removes it before the request is formally done), which is why
 * it is passed here and not to `mutate`: callbacks given to `mutate` are dropped on unmount.
 * Use `describeResolveError` to explain a failure.
 */
export function useResolveReview(onOutcome?: (outcome: ResolveOutcome) => void) {
  const client = useQueryClient();
  return useMutation<ReviewResolved, Error, ResolveVariables>({
    mutationFn: ({ id, label }) => resolveReview(id, label),
    onSuccess: (_result, variables) => onOutcome?.({ ok: true, ...variables }),
    onError: (error, variables) => onOutcome?.({ ok: false, ...variables, error }),
    // Returning the promise keeps the mutation pending until the queue is fresh again, so the
    // buttons of a row stay locked until the row is gone.
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.review }),
        client.invalidateQueries({ queryKey: queryKeys.requests }),
      ]),
  });
}
