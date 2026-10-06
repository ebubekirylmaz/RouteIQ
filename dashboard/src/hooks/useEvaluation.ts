import { useQuery } from "@tanstack/react-query";

import { getEvaluation } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";

/**
 * The offline evaluation. It is computed from recorded predictions that do not change while the
 * service runs, so it is not polled, and a 404 (nothing recorded for this configuration) is an
 * answer and not a failure to retry.
 */
export function useEvaluation() {
  return useQuery({
    queryKey: queryKeys.evaluation,
    queryFn: ({ signal }) => getEvaluation(signal),
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
  });
}
