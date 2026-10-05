import { apiGet, apiPost, queryString, totalCount, type Schemas } from "./client";

export type ConfigView = Schemas["ConfigResponse"];
export type ReviewItem = Schemas["ReviewItem"];
export type RequestItem = Schemas["RequestItem"];
export type Stats = Schemas["StatsResponse"];
export type Timeseries = Schemas["TimeseriesResponse"];
export type RetryResult = Schemas["RetryResult"];
export type ReviewResolved = Schemas["ReviewResolved"];

/** A page of rows plus the total number of matching rows. */
export type Page<T> = { items: T[]; total: number };

export const getConfig = (signal?: AbortSignal) =>
  apiGet<ConfigView>("/config", signal).then((result) => result.data);

/** Requests waiting for a person, oldest first. */
export async function listReview(limit = 50, offset = 0, signal?: AbortSignal): Promise<Page<ReviewItem>> {
  const { data, headers } = await apiGet<ReviewItem[]>(
    `/review${queryString({ limit, offset })}`,
    signal,
  );
  return { items: data, total: totalCount(headers) };
}

/**
 * Records the person's decision. Rejects with ApiError: 404 unknown request,
 * 409 already resolved (someone else was faster), 422 label not in the config.
 */
export const resolveReview = (id: number, label: string) =>
  apiPost<ReviewResolved>(`/review/${id}`, { label }).then((result) => result.data);

export type RequestFilters = {
  action?: "accepted" | "human_review";
  tier?: string;
  review_status?: "pending" | "resolved";
  delivery_status?: "pending" | "sent" | "failed";
  degraded?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
  order?: "newest" | "oldest";
};

export async function listRequests(
  filters: RequestFilters = {},
  signal?: AbortSignal,
): Promise<Page<RequestItem>> {
  const { data, headers } = await apiGet<RequestItem[]>(`/requests${queryString(filters)}`, signal);
  return { items: data, total: totalCount(headers) };
}

/** `since` is an ISO 8601 time, e.g. `new Date(Date.now() - 864e5).toISOString()`. */
export const getStats = (since?: string, signal?: AbortSignal) =>
  apiGet<Stats>(`/stats${queryString({ since })}`, signal).then((result) => result.data);

export type TimeseriesParams = { bucket?: "hour" | "day"; since?: string; until?: string };

export const getTimeseries = (params: TimeseriesParams = {}, signal?: AbortSignal) =>
  apiGet<Timeseries>(`/stats/timeseries${queryString(params)}`, signal).then(
    (result) => result.data,
  );

/** Resends failed deliveries and ones stuck in pending. */
export const retryDeliveries = (limit = 100) =>
  apiPost<RetryResult>(`/deliveries/retry${queryString({ limit })}`).then((result) => result.data);
