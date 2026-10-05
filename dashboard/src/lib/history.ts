import type { RequestFilters } from "../api/endpoints";

export const HISTORY_PAGE_SIZE = 25;
export const MAX_TIER_LENGTH = 50;
export const MAX_SEARCH_LENGTH = 200;

export type HistoryFilters = {
  action?: "accepted" | "human_review";
  review_status?: "pending" | "resolved";
  delivery_status?: "pending" | "sent" | "failed";
  /** Only "true" is a filter. Not asking is different from asking for requests where nothing failed. */
  degraded?: true;
  tier?: string;
  q?: string;
};

const ACTIONS = ["accepted", "human_review"] as const;
const REVIEW = ["pending", "resolved"] as const;
const DELIVERY = ["pending", "sent", "failed"] as const;

function oneOf<T extends string>(value: string | null, allowed: readonly T[]): T | undefined {
  return allowed.find((item) => item === value);
}

/**
 * Reads the filters and the page from the address. Whatever somebody typed or an old link
 * contains, nothing invalid gets through: a bad value is dropped, a bad page becomes page 1.
 */
export function parseHistoryParams(params: URLSearchParams): { filters: HistoryFilters; page: number } {
  const filters: HistoryFilters = {};

  const action = oneOf(params.get("action"), ACTIONS);
  if (action) filters.action = action;
  const review = oneOf(params.get("review"), REVIEW);
  if (review) filters.review_status = review;
  const delivery = oneOf(params.get("delivery"), DELIVERY);
  if (delivery) filters.delivery_status = delivery;
  if (params.get("degraded") === "1") filters.degraded = true;

  const tier = params.get("tier")?.trim();
  if (tier && tier.length <= MAX_TIER_LENGTH) filters.tier = tier;
  const q = params.get("q")?.trim();
  if (q) filters.q = q.slice(0, MAX_SEARCH_LENGTH);

  const raw = Number(params.get("page"));
  const page = Number.isInteger(raw) && raw >= 1 ? raw : 1;
  return { filters, page };
}

/** The address for a set of filters. Defaults are left out, so the first page of everything is "/history". */
export function buildHistoryParams(filters: HistoryFilters, page = 1): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.action) params.set("action", filters.action);
  if (filters.review_status) params.set("review", filters.review_status);
  if (filters.delivery_status) params.set("delivery", filters.delivery_status);
  if (filters.degraded) params.set("degraded", "1");
  if (filters.tier) params.set("tier", filters.tier);
  if (filters.q) params.set("q", filters.q);
  if (page > 1) params.set("page", String(page));
  return params;
}

export function hasActiveFilters(filters: HistoryFilters): boolean {
  return Object.values(filters).some((value) => value !== undefined && value !== "");
}

/** The request for one page of the history, newest first. Pages start at 1. */
export function toRequestFilters(
  filters: HistoryFilters,
  page = 1,
  pageSize: number = HISTORY_PAGE_SIZE,
): RequestFilters {
  return { ...filters, limit: pageSize, offset: (page - 1) * pageSize, order: "newest" };
}
