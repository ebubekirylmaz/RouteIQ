import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../test/server";
import { ApiError, apiGet, apiPost, queryString, totalCount } from "./client";

describe("queryString", () => {
  it("is empty when there is nothing to send", () => {
    expect(queryString({})).toBe("");
    expect(queryString({ a: undefined, b: "" })).toBe("");
  });

  it("leaves out undefined and empty values", () => {
    expect(queryString({ limit: 50, q: "", tier: undefined, offset: 0 })).toBe("?limit=50&offset=0");
  });

  it("keeps false and 0, which are real values", () => {
    expect(queryString({ degraded: false, offset: 0 })).toBe("?degraded=false&offset=0");
  });

  it("encodes special characters", () => {
    const text = queryString({ q: "50% & more", since: "2026-10-05T10:00:00+03:00" });
    expect(text).toContain("q=50%25+%26+more");
    expect(text).toContain("since=2026-10-05T10%3A00%3A00%2B03%3A00");
  });
});

describe("totalCount", () => {
  it("reads X-Total-Count", () => {
    expect(totalCount(new Headers({ "X-Total-Count": "42" }))).toBe(42);
  });

  it("is 0 when the header is missing or not a number", () => {
    expect(totalCount(new Headers())).toBe(0);
    expect(totalCount(new Headers({ "X-Total-Count": "many" }))).toBe(0);
  });
});

describe("apiGet", () => {
  it("returns the parsed body and the headers", async () => {
    server.use(
      http.get("*/config", () => HttpResponse.json({ domain: "demo" }, { headers: { "X-Total-Count": "7" } })),
    );
    const { data, headers } = await apiGet<{ domain: string }>("/config");
    expect(data).toEqual({ domain: "demo" });
    expect(totalCount(headers)).toBe(7);
  });

  it("asks for JSON and sends no body type", async () => {
    let seen: Headers | undefined;
    server.use(
      http.get("*/config", ({ request }) => {
        seen = request.headers;
        return HttpResponse.json({});
      }),
    );
    await apiGet("/config");
    expect(seen?.get("accept")).toBe("application/json");
    expect(seen?.get("content-type")).toBeNull();
  });

  it("rejects with the API's own message on an error status", async () => {
    server.use(http.get("*/review", () => HttpResponse.json({ detail: "request not found" }, { status: 404 })));
    const error = await apiGet("/review").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, detail: "request not found" });
  });

  it("turns a validation error list into a short message", async () => {
    server.use(
      http.get("*/requests", () =>
        HttpResponse.json({ detail: [{ loc: ["query", "limit"], msg: "too big" }] }, { status: 422 }),
      ),
    );
    await expect(apiGet("/requests")).rejects.toMatchObject({ status: 422, detail: "invalid request" });
  });

  it("falls back to the status text when the body is not JSON", async () => {
    server.use(
      http.get("*/stats", () => new HttpResponse("upstream down", { status: 502, statusText: "Bad Gateway" })),
    );
    await expect(apiGet("/stats")).rejects.toMatchObject({ status: 502, detail: "Bad Gateway" });
  });

  it("falls back when a JSON error has no usable detail", async () => {
    server.use(http.get("*/stats", () => HttpResponse.json({ oops: true }, { status: 500, statusText: "Server Error" })));
    await expect(apiGet("/stats")).rejects.toMatchObject({ status: 500, detail: "Server Error" });
  });

  it("lets a network failure through as it is", async () => {
    server.use(http.get("*/health", () => HttpResponse.error()));
    await expect(apiGet("/health")).rejects.toBeInstanceOf(TypeError);
  });

  it("can be cancelled", async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(apiGet("/config", controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("apiPost", () => {
  it("sends the body as JSON", async () => {
    let seenBody: unknown;
    let seenType: string | null = null;
    server.use(
      http.post("*/review/1", async ({ request }) => {
        seenType = request.headers.get("content-type");
        seenBody = await request.json();
        return HttpResponse.json({ id: 1, status: "resolved", final_label: "a" });
      }),
    );
    const { data } = await apiPost<{ status: string }>("/review/1", { label: "a" });
    expect(seenBody).toEqual({ label: "a" });
    expect(seenType).toContain("application/json");
    expect(data.status).toBe("resolved");
  });

  it("sends no body and no content type when there is none", async () => {
    let seenType: string | null = "unset";
    server.use(
      http.post("*/deliveries/retry", ({ request }) => {
        seenType = request.headers.get("content-type");
        return HttpResponse.json({ retried: 0, sent: 0, failed: 0 });
      }),
    );
    await apiPost("/deliveries/retry");
    expect(seenType).toBeNull();
  });

  it("rejects with an ApiError, so the caller can tell a conflict from a failure", async () => {
    server.use(
      http.post("*/review/1", () => HttpResponse.json({ detail: "request is not pending review" }, { status: 409 })),
    );
    await expect(apiPost("/review/1", { label: "a" })).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      detail: "request is not pending review",
    });
  });
});

describe("ApiError", () => {
  it("is an Error with the status and detail in its message", () => {
    const error = new ApiError(409, "request is not pending review");
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe("409: request is not pending review");
  });
});
