import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../test/server";
import {
  getConfig,
  getStats,
  getTimeseries,
  listRequests,
  listReview,
  resolveReview,
  retryDeliveries,
} from "./endpoints";

/** Records the URL of every request a handler receives. */
function capture(method: "get" | "post", pattern: string, body: unknown, headers: Record<string, string> = {}) {
  const urls: URL[] = [];
  const handler = method === "get" ? http.get : http.post;
  server.use(
    handler(pattern, ({ request }) => {
      urls.push(new URL(request.url));
      return HttpResponse.json(body as Record<string, unknown>, { headers });
    }),
  );
  return urls;
}

describe("getConfig", () => {
  it("returns the config view", async () => {
    capture("get", "*/config", { domain: "demo", labels: [], tiers: [], task: null, target_type: null });
    expect(await getConfig()).toMatchObject({ domain: "demo" });
  });
});

describe("listReview", () => {
  it("asks for the first page and reads the total from the header", async () => {
    const urls = capture("get", "*/review", [{ id: 1 }, { id: 2 }], { "X-Total-Count": "9" });
    const page = await listReview();
    expect(urls[0]?.search).toBe("?limit=50&offset=0");
    expect(page.items).toHaveLength(2);
    expect(page.total).toBe(9);
  });

  it("passes limit and offset", async () => {
    const urls = capture("get", "*/review", [], { "X-Total-Count": "0" });
    await listReview(10, 30);
    expect(urls[0]?.searchParams.get("limit")).toBe("10");
    expect(urls[0]?.searchParams.get("offset")).toBe("30");
  });

  it("returns an empty page for an empty queue", async () => {
    capture("get", "*/review", [], { "X-Total-Count": "0" });
    expect(await listReview()).toEqual({ items: [], total: 0 });
  });
});

describe("resolveReview", () => {
  it("posts the label to the request's own path", async () => {
    let seen: { path: string; body: unknown } | undefined;
    server.use(
      http.post("*/review/:id", async ({ request, params }) => {
        seen = { path: String(params.id), body: await request.json() };
        return HttpResponse.json({ id: 7, status: "resolved", final_label: "out_of_scope" });
      }),
    );
    const result = await resolveReview(7, "out_of_scope");
    expect(seen).toEqual({ path: "7", body: { label: "out_of_scope" } });
    expect(result.final_label).toBe("out_of_scope");
  });

  it.each([
    [404, "request not found"],
    [409, "request is not pending review"],
    [422, "unknown label"],
  ])("rejects with a %i the caller can tell apart", async (status, detail) => {
    server.use(http.post("*/review/:id", () => HttpResponse.json({ detail }, { status })));
    await expect(resolveReview(1, "a")).rejects.toMatchObject({ name: "ApiError", status, detail });
  });
});

describe("listRequests", () => {
  it("sends nothing when no filter is set", async () => {
    const urls = capture("get", "*/requests", [], { "X-Total-Count": "0" });
    await listRequests();
    expect(urls[0]?.search).toBe("");
  });

  it("sends the filters it was given", async () => {
    const urls = capture("get", "*/requests", [], { "X-Total-Count": "0" });
    await listRequests({
      action: "human_review",
      review_status: "pending",
      delivery_status: "failed",
      tier: "llm",
      q: "wallet",
      limit: 25,
      offset: 50,
      order: "oldest",
    });
    const params = urls[0]?.searchParams;
    expect(Object.fromEntries(params ?? [])).toEqual({
      action: "human_review",
      review_status: "pending",
      delivery_status: "failed",
      tier: "llm",
      q: "wallet",
      limit: "25",
      offset: "50",
      order: "oldest",
    });
  });

  it("keeps degraded=false, which is a different question from not asking", async () => {
    const urls = capture("get", "*/requests", [], { "X-Total-Count": "0" });
    await listRequests({ degraded: false });
    expect(urls[0]?.searchParams.get("degraded")).toBe("false");
  });

  it("drops an empty search text", async () => {
    const urls = capture("get", "*/requests", [], { "X-Total-Count": "0" });
    await listRequests({ q: "" });
    expect(urls[0]?.searchParams.has("q")).toBe(false);
  });

  it("returns the rows with the total of all matches", async () => {
    capture("get", "*/requests", [{ id: 3 }], { "X-Total-Count": "120" });
    expect(await listRequests({ limit: 1 })).toEqual({ items: [{ id: 3 }], total: 120 });
  });
});

describe("getStats", () => {
  it("asks for everything by default", async () => {
    const urls = capture("get", "*/stats", { requests: 0 });
    await getStats();
    expect(urls[0]?.search).toBe("");
  });

  it("sends the window start", async () => {
    const urls = capture("get", "*/stats", { requests: 0 });
    await getStats("2026-10-05T00:00:00.000Z");
    expect(urls[0]?.searchParams.get("since")).toBe("2026-10-05T00:00:00.000Z");
  });
});

describe("getTimeseries", () => {
  it("uses the API defaults when called without parameters", async () => {
    const urls = capture("get", "*/stats/timeseries", { bucket: "hour", points: [] });
    await getTimeseries();
    expect(urls[0]?.search).toBe("");
  });

  it("sends bucket and range", async () => {
    const urls = capture("get", "*/stats/timeseries", { bucket: "day", points: [] });
    await getTimeseries({ bucket: "day", since: "2026-09-01T00:00:00Z", until: "2026-10-01T00:00:00Z" });
    expect(Object.fromEntries(urls[0]?.searchParams ?? [])).toEqual({
      bucket: "day",
      since: "2026-09-01T00:00:00Z",
      until: "2026-10-01T00:00:00Z",
    });
  });

  it("surfaces the API's refusal of a range that is too long", async () => {
    server.use(
      http.get("*/stats/timeseries", () =>
        HttpResponse.json({ detail: "the range covers more than 1000 buckets" }, { status: 422 }),
      ),
    );
    await expect(getTimeseries({ since: "2000-01-01T00:00:00Z" })).rejects.toMatchObject({
      status: 422,
      detail: "the range covers more than 1000 buckets",
    });
  });
});

describe("retryDeliveries", () => {
  it("posts with the default limit", async () => {
    const urls = capture("post", "*/deliveries/retry", { retried: 2, sent: 1, failed: 1 });
    const result = await retryDeliveries();
    expect(urls[0]?.searchParams.get("limit")).toBe("100");
    expect(result).toEqual({ retried: 2, sent: 1, failed: 1 });
  });

  it("reports that there is no target configured", async () => {
    server.use(
      http.post("*/deliveries/retry", () => HttpResponse.json({ detail: "no delivery target configured" }, { status: 409 })),
    );
    await expect(retryDeliveries()).rejects.toMatchObject({ status: 409 });
  });
});
