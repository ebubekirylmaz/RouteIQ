import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { queryKeys } from "../api/queryKeys";
import { server } from "../test/server";
import { createWrapper, makeQueryClient } from "../test/utils";
import { useConfig } from "./useConfig";
import { useResolveReview } from "./useResolveReview";
import { useReviewQueue } from "./useReviewQueue";

const item = (id: number) => ({
  id,
  created_at: "2026-10-05T10:00:00Z",
  text: `request ${id}`,
  suggested_label: "freeze_account",
  confidence: 0.67,
  tier: "llm",
});

/** Serves a queue of `total` items and records every request's URL. */
function serveQueue(total: number) {
  const urls: URL[] = [];
  server.use(
    http.get("*/review", ({ request }) => {
      const url = new URL(request.url);
      urls.push(url);
      const limit = Number(url.searchParams.get("limit"));
      const offset = Number(url.searchParams.get("offset"));
      const ids = Array.from({ length: total }, (_, i) => i + 1).slice(offset, offset + limit);
      return HttpResponse.json(ids.map(item), { headers: { "X-Total-Count": String(total) } });
    }),
  );
  return urls;
}

describe("useConfig", () => {
  it("loads the config once and shares it", async () => {
    let calls = 0;
    server.use(
      http.get("*/config", () => {
        calls += 1;
        return HttpResponse.json({ domain: "demo", labels: [{ name: "a", description: "first" }], tiers: [] });
      }),
    );
    const client = makeQueryClient();
    const wrapper = createWrapper(client);

    const first = renderHook(() => useConfig(), { wrapper });
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true));
    const second = renderHook(() => useConfig(), { wrapper });

    expect(second.result.current.data?.labels[0]?.name).toBe("a");
    expect(calls).toBe(1);
  });

  it("is kept fresh for minutes, because the config rarely changes", () => {
    const client = makeQueryClient();
    server.use(http.get("*/config", () => HttpResponse.json({ domain: "demo" })));
    renderHook(() => useConfig(), { wrapper: createWrapper(client) });
    const query = client.getQueryCache().find({ queryKey: queryKeys.config });
    expect(query?.observers[0]?.options.staleTime).toBe(5 * 60_000);
  });

  it("reports a failure", async () => {
    server.use(http.get("*/config", () => HttpResponse.json({ detail: "nope" }, { status: 500 })));
    const { result } = renderHook(() => useConfig(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useReviewQueue", () => {
  it("loads the first page with the total", async () => {
    const urls = serveQueue(45);
    const { result } = renderHook(() => useReviewQueue(0, 20), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(20);
    expect(result.current.data?.total).toBe(45);
    expect(urls[0]?.searchParams.get("limit")).toBe("20");
    expect(urls[0]?.searchParams.get("offset")).toBe("0");
  });

  it("turns a page number into an offset", async () => {
    const urls = serveQueue(45);
    const { result } = renderHook(() => useReviewQueue(2, 20), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(urls[0]?.searchParams.get("offset")).toBe("40");
    expect(result.current.data?.items.map((i) => i.id)).toEqual([41, 42, 43, 44, 45]);
  });

  it("keeps showing the previous page while the next one loads", async () => {
    serveQueue(45);
    const { result, rerender } = renderHook(({ page }) => useReviewQueue(page, 20), {
      wrapper: createWrapper(),
      initialProps: { page: 0 },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    rerender({ page: 1 });

    expect(result.current.isPlaceholderData).toBe(true);
    expect(result.current.data?.items[0]?.id).toBe(1);
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(false));
    expect(result.current.data?.items[0]?.id).toBe(21);
  });

  it("polls while the tab is visible", () => {
    const client = makeQueryClient();
    serveQueue(1);
    renderHook(() => useReviewQueue(0, 20), { wrapper: createWrapper(client) });
    const query = client.getQueryCache().find({ queryKey: queryKeys.reviewPage(20, 0) });
    expect(query?.observers[0]?.options.refetchInterval).toBe(10_000);
  });

  it("returns an empty page for an empty queue", async () => {
    serveQueue(0);
    const { result } = renderHook(() => useReviewQueue(0, 20), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ items: [], total: 0 });
  });

  it("reports a failure without retrying a client error", async () => {
    let calls = 0;
    server.use(
      http.get("*/review", () => {
        calls += 1;
        return HttpResponse.json({ detail: "bad" }, { status: 422 });
      }),
    );
    const { result } = renderHook(() => useReviewQueue(0, 20), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(calls).toBe(1);
  });
});

describe("useResolveReview", () => {
  function setup(total = 3) {
    const urls = serveQueue(total);
    const posted: { id: string; label: unknown }[] = [];
    server.use(
      http.post("*/review/:id", async ({ request, params }) => {
        posted.push({ id: String(params.id), label: ((await request.json()) as { label: string }).label });
        return HttpResponse.json({ id: Number(params.id), status: "resolved", final_label: "a" });
      }),
    );
    const client = makeQueryClient();
    const wrapper = createWrapper(client);
    const queue = renderHook(() => useReviewQueue(0, 20), { wrapper });
    const resolve = renderHook(() => useResolveReview(), { wrapper });
    return { urls, posted, client, queue, resolve };
  }

  it("posts the decision", async () => {
    const { posted, queue, resolve } = setup();
    await waitFor(() => expect(queue.result.current.isSuccess).toBe(true));

    await act(() => resolve.result.current.mutateAsync({ id: 2, label: "out_of_scope" }));

    expect(posted).toEqual([{ id: "2", label: "out_of_scope" }]);
  });

  it("refreshes the queue after a success", async () => {
    const { urls, queue, resolve } = setup();
    await waitFor(() => expect(queue.result.current.isSuccess).toBe(true));
    const before = urls.length;

    await act(() => resolve.result.current.mutateAsync({ id: 1, label: "a" }));

    await waitFor(() => expect(urls.length).toBeGreaterThan(before));
  });

  it("refreshes every page of the queue, whatever its size and offset", async () => {
    const { client, queue, resolve } = setup(45);
    await waitFor(() => expect(queue.result.current.isSuccess).toBe(true));
    const other = renderHook(() => useReviewQueue(1, 10), { wrapper: createWrapper(client) });
    await waitFor(() => expect(other.result.current.isSuccess).toBe(true));
    let invalidated = 0;
    client.getQueryCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "invalidate") invalidated += 1;
    });

    await act(() => resolve.result.current.mutateAsync({ id: 1, label: "a" }));

    expect(invalidated).toBe(2);
  });

  it("does not reload the config", async () => {
    const { client, queue, resolve } = setup();
    let configCalls = 0;
    server.use(
      http.get("*/config", () => {
        configCalls += 1;
        return HttpResponse.json({ domain: "demo" });
      }),
    );
    const config = renderHook(() => useConfig(), { wrapper: createWrapper(client) });
    await waitFor(() => expect(config.result.current.isSuccess).toBe(true));
    await waitFor(() => expect(queue.result.current.isSuccess).toBe(true));

    await act(() => resolve.result.current.mutateAsync({ id: 1, label: "a" }));

    expect(configCalls).toBe(1);
  });

  it("fails with a 409 when somebody else was faster, and still refreshes the queue", async () => {
    const { urls, queue, resolve } = setup();
    await waitFor(() => expect(queue.result.current.isSuccess).toBe(true));
    server.use(
      http.post("*/review/:id", () => HttpResponse.json({ detail: "request is not pending review" }, { status: 409 })),
    );
    const before = urls.length;

    await act(async () => {
      await expect(resolve.result.current.mutateAsync({ id: 1, label: "a" })).rejects.toMatchObject({ status: 409 });
    });

    await waitFor(() => expect(urls.length).toBeGreaterThan(before));
    expect(resolve.result.current.isError).toBe(true);
  });

  it("never sends a decision twice, even when the server fails", async () => {
    const { queue, resolve } = setup();
    await waitFor(() => expect(queue.result.current.isSuccess).toBe(true));
    let calls = 0;
    server.use(
      http.post("*/review/:id", () => {
        calls += 1;
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );

    await act(async () => {
      await expect(resolve.result.current.mutateAsync({ id: 1, label: "a" })).rejects.toMatchObject({ status: 500 });
    });

    expect(calls).toBe(1);
  });

  it("exposes the pending state and the variables, so a row can disable its own buttons", async () => {
    const { queue, resolve } = setup();
    await waitFor(() => expect(queue.result.current.isSuccess).toBe(true));
    let release: () => void = () => {};
    const gate = new Promise<void>((resolveGate) => {
      release = resolveGate;
    });
    server.use(
      http.post("*/review/:id", async ({ params }) => {
        await gate;
        return HttpResponse.json({ id: Number(params.id), status: "resolved", final_label: "a" });
      }),
    );

    let promise: Promise<unknown> = Promise.resolve();
    act(() => {
      promise = resolve.result.current.mutateAsync({ id: 3, label: "a" });
    });

    await waitFor(() => expect(resolve.result.current.isPending).toBe(true));
    expect(resolve.result.current.variables).toEqual({ id: 3, label: "a" });

    release();
    await act(async () => {
      await promise;
    });
    await waitFor(() => expect(resolve.result.current.isPending).toBe(false));
  });

  it("stays pending until the queue has been refreshed, so a row does not flicker back to life", async () => {
    const { queue, resolve } = setup();
    await waitFor(() => expect(queue.result.current.isSuccess).toBe(true));

    let releaseRefetch: () => void = () => {};
    const refetchGate = new Promise<void>((resolveGate) => {
      releaseRefetch = resolveGate;
    });
    server.use(
      http.get("*/review", async () => {
        await refetchGate;
        return HttpResponse.json([], { headers: { "X-Total-Count": "0" } });
      }),
    );

    let promise: Promise<unknown> = Promise.resolve();
    act(() => {
      promise = resolve.result.current.mutateAsync({ id: 1, label: "a" });
    });

    // the POST has answered, the refresh is still running
    await waitFor(() => expect(queue.result.current.isFetching).toBe(true));
    expect(resolve.result.current.isPending).toBe(true);

    releaseRefetch();
    await act(async () => {
      await promise;
    });
    await waitFor(() => expect(resolve.result.current.isPending).toBe(false));
    expect(queue.result.current.data?.items).toEqual([]);
  });
});
