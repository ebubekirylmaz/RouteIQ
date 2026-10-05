import { HttpResponse, http } from "msw";

import type { ConfigView, ReviewItem } from "../api/endpoints";
import { server } from "./server";

export const LABELS: ConfigView["labels"] = [
  { name: "report_lost_card", description: "the customer lost their card or cannot find it." },
  { name: "damaged_card", description: "the card is physically damaged." },
  { name: "card_declined", description: null },
  { name: "report_fraud", description: "unauthorized or suspicious charges on the account." },
  { name: "freeze_account", description: "the customer wants the account blocked or locked." },
  { name: "out_of_scope", description: "anything else." },
];

export function reviewItem(id: number, overrides: Partial<ReviewItem> = {}): ReviewItem {
  return {
    id,
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    text: `request ${id}`,
    suggested_label: "freeze_account",
    confidence: 0.67,
    tier: "llm",
    ...overrides,
  };
}

export const items = (count: number, from = 1) => Array.from({ length: count }, (_, i) => reviewItem(from + i));

export type FakeApi = {
  /** The queue as the fake API holds it. Change it to simulate other people's work. */
  queue: ReviewItem[];
  /** Every decision posted so far. */
  posts: { id: number; label: string }[];
  /** URL of every GET /review. */
  reads: URL[];
  /** Number of GET /config calls. */
  configReads: () => number;
};

/**
 * A small fake of the review part of the API: GET /config, GET /review (limit, offset,
 * X-Total-Count) and POST /review/{id}, which removes the request like the real API does.
 */
export function serveReviewApi(initial: ReviewItem[] = [], labels = LABELS): FakeApi {
  const api: FakeApi = { queue: [...initial], posts: [], reads: [], configReads: () => configCalls };
  let configCalls = 0;

  server.use(
    http.get("*/config", () => {
      configCalls += 1;
      return HttpResponse.json({ domain: "demo", task: "support", labels, tiers: [], target_type: null });
    }),
    http.get("*/review", ({ request }) => {
      const url = new URL(request.url);
      api.reads.push(url);
      const limit = Number(url.searchParams.get("limit") ?? 50);
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return HttpResponse.json(api.queue.slice(offset, offset + limit), {
        headers: { "X-Total-Count": String(api.queue.length) },
      });
    }),
    http.post("*/review/:id", async ({ request, params }) => {
      const id = Number(params.id);
      const { label } = (await request.json()) as { label: string };
      api.posts.push({ id, label });
      api.queue = api.queue.filter((item) => item.id !== id);
      return HttpResponse.json({ id, status: "resolved", final_label: label });
    }),
  );
  return api;
}

/** Makes POST /review/{id} answer with an error instead. */
export function failDecisions(status: number, detail: string) {
  server.use(http.post("*/review/:id", () => HttpResponse.json({ detail }, { status })));
}
