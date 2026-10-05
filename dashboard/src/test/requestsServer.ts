import { HttpResponse, http } from "msw";

import type { ConfigView, RequestItem } from "../api/endpoints";
import { LABELS } from "./reviewServer";
import { server } from "./server";

export function requestItem(id: number, overrides: Partial<RequestItem> = {}): RequestItem {
  return {
    id,
    created_at: new Date(Date.parse("2026-10-05T14:00:00Z") + id * 1000).toISOString(),
    text: `request ${id}`,
    label: "report_fraud",
    confidence: 0.95,
    tier: "baseline",
    action: "accepted",
    cost_usd: 0,
    latency_ms: 2,
    degraded: false,
    review_status: null,
    final_label: null,
    resolved_at: null,
    delivery_status: "sent",
    delivery_error: null,
    delivered_at: new Date(Date.parse("2026-10-05T14:00:01Z") + id * 1000).toISOString(),
    ...overrides,
  };
}

export const requestItems = (count: number, from = 1) =>
  Array.from({ length: count }, (_, i) => requestItem(from + i));

export type FakeRequestsApi = {
  /** The history as the fake API holds it, in any order: the fake sorts it. */
  rows: RequestItem[];
  /** URL of every GET /requests. */
  reads: URL[];
};

/**
 * A fake of GET /requests that filters like the real one: action, tier, review_status,
 * delivery_status, degraded, q (case-insensitive substring), order, limit, offset and
 * X-Total-Count.
 */
export function serveRequestsApi(initial: RequestItem[] = []): FakeRequestsApi {
  const api: FakeRequestsApi = { rows: [...initial], reads: [] };
  server.use(
    http.get("*/requests", ({ request }) => {
      const url = new URL(request.url);
      api.reads.push(url);
      const get = (name: string) => url.searchParams.get(name);
      const q = get("q")?.toLowerCase();

      const matching = api.rows
        .filter((row) => !get("action") || row.action === get("action"))
        .filter((row) => !get("tier") || row.tier === get("tier"))
        .filter((row) => !get("review_status") || row.review_status === get("review_status"))
        .filter((row) => !get("delivery_status") || row.delivery_status === get("delivery_status"))
        .filter((row) => get("degraded") === null || row.degraded === (get("degraded") === "true"))
        .filter((row) => !q || row.text.toLowerCase().includes(q))
        .sort((a, b) => (get("order") === "oldest" ? a.id - b.id : b.id - a.id));

      const limit = Number(get("limit") ?? 50);
      const offset = Number(get("offset") ?? 0);
      return HttpResponse.json(matching.slice(offset, offset + limit), {
        headers: { "X-Total-Count": String(matching.length) },
      });
    }),
  );
  return api;
}

/** GET /config with tiers, which the history needs for its tier filter. */
export function serveConfigWithTiers(tierNames: string[] = ["baseline", "llm"]) {
  const tiers: ConfigView["tiers"] = tierNames.map((name) => ({
    name, model: null, model_id: null, accept_threshold: 0.7,
  }));
  server.use(
    http.get("*/config", () =>
      HttpResponse.json({ domain: "demo", task: "support", labels: LABELS, tiers, target_type: null }),
    ),
  );
}
