import { useMutation, useQueryClient } from "@tanstack/react-query";

import { resolveReview, type ReviewResolved } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";

export type ResolveVariables = { id: number; label: string };

/**
 * Records a person's decision. The queue is refreshed whatever the outcome: after a success the
 * request is gone, and after a 409 or 404 somebody else already changed it. Use
 * `describeResolveError` to explain a failure.
 */
export function useResolveReview() {
  const client = useQueryClient();
  return useMutation<ReviewResolved, Error, ResolveVariables>({
    mutationFn: ({ id, label }) => resolveReview(id, label),
    onSettled: () => client.invalidateQueries({ queryKey: queryKeys.review }),
  });
}
