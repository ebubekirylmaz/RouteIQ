import { useMutation, useQueryClient } from "@tanstack/react-query";

import { routeText, type RouteResult } from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";

export type RouteVariables = { text: string };

/**
 * Routes a text. Every screen that shows requests is refreshed afterwards, whatever the outcome:
 * when the answer got lost on the way, the text may still have been stored.
 *
 * `onResult` gets the answer even when the screen has been left by then. It is passed here, and
 * not to `mutate`, because callbacks given to `mutate` are dropped on unmount. The request is
 * never retried: a second try would be a second paid, stored request.
 */
export function useRouteText(onResult?: (text: string, result: RouteResult) => void) {
  const client = useQueryClient();
  return useMutation<RouteResult, Error, RouteVariables>({
    mutationFn: ({ text }) => routeText(text),
    onSuccess: (result, { text }) => onResult?.(text, result),
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.requests }),
        client.invalidateQueries({ queryKey: queryKeys.review }),
        client.invalidateQueries({ queryKey: queryKeys.stats }),
        client.invalidateQueries({ queryKey: queryKeys.timeseriesAll }),
      ]),
  });
}
