import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "../api/queryKeys";
import { getConfig } from "../api/endpoints";

/** Labels, descriptions and thresholds. They only change when the API restarts with a new config. */
export function useConfig() {
  return useQuery({
    queryKey: queryKeys.config,
    queryFn: ({ signal }) => getConfig(signal),
    staleTime: 5 * 60_000,
  });
}
