import { HttpResponse, http } from "msw";

import type { RouteResult } from "../api/endpoints";
import { server } from "./server";

export const routeResult = (overrides: Partial<RouteResult> = {}): RouteResult => ({
  label: "card_declined",
  confidence: 0.936,
  tier: "baseline",
  action: "accepted",
  cost_usd: 0,
  latency_ms: 4.2,
  degraded: false,
  request_id: 1,
  ...overrides,
});

export type FakeRouteApi = {
  /** The text of every POST /route, as it arrived. */
  texts: string[];
  /** What the next POST answers with. Return a Response to simulate a failure. */
  respond: (text: string) => RouteResult | Response;
};

/** A fake of POST /route. By default every text is accepted, with a new request id each time. */
export function serveRouteApi(respond?: FakeRouteApi["respond"]): FakeRouteApi {
  const api: FakeRouteApi = {
    texts: [],
    respond: respond ?? (() => routeResult({ request_id: api.texts.length })),
  };
  server.use(
    http.post("*/route", async ({ request }) => {
      const { text } = (await request.json()) as { text: string };
      api.texts.push(text);
      const answer = api.respond(text);
      return answer instanceof Response ? answer : HttpResponse.json(answer);
    }),
  );
  return api;
}

/** GET /config with the example sentences of the Try it screen. */
export function serveConfig(examples: string[] = [], overrides: Record<string, unknown> = {}) {
  server.use(
    http.get("*/config", () =>
      HttpResponse.json({
        domain: "demo", task: "support", labels: [], tiers: [], target_type: null, data_source: null,
        demo: false, max_text_length: 5000, examples, ...overrides,
      }),
    ),
  );
}
