import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { queryKeys } from "../api/queryKeys";
import { server } from "../test/server";
import { serveStatsApi, statsFixture } from "../test/statsServer";
import { createWrapper, makeQueryClient } from "../test/utils";
import { useRetryDeliveries } from "./useRetryDeliveries";
import { STATS_POLL_MS, useStats } from "./useStats";

describe("useStats", () => {
  it("asks for the last 24 hours with a start time", async () => {
    const api = serveStatsApi();
    const { result } = renderHook(() => useStats("24h"), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const since = Date.parse(api.reads[0]?.searchParams.get("since") ?? "");
    expect(Math.abs(Date.now() - since - 24 * 3_600_000)).toBeLessThan(5000);
    expect(result.current.data?.requests).toBe(200);
  });

  it("asks for the last 7 days", async () => {
    const api = serveStatsApi();
    const { result } = renderHook(() => useStats("7d"), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const since = Date.parse(api.reads[0]?.searchParams.get("since") ?? "");
    expect(Math.abs(Date.now() - since - 7 * 24 * 3_600_000)).toBeLessThan(5000);
  });

  it("sends no start time for all time", async () => {
    const api = serveStatsApi();
    const { result } = renderHook(() => useStats("all"), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.reads[0]?.searchParams.has("since")).toBe(false);
  });

  it("keeps one cache entry per window, so switching back is instant", async () => {
    const api = serveStatsApi();
    const client = makeQueryClient();
    const { result, rerender } = renderHook(({ window }) => useStats(window), {
      wrapper: createWrapper(client),
      initialProps: { window: "24h" as const } as { window: "24h" | "7d" | "all" },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    rerender({ window: "7d" });
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(false));

    expect(client.getQueryData(queryKeys.statsWindow("24h"))).toBeDefined();
    expect(client.getQueryData(queryKeys.statsWindow("7d"))).toBeDefined();
    expect(api.reads).toHaveLength(2);
  });

  it("keeps the previous numbers while another window loads", async () => {
    const api = serveStatsApi({ stats: statsFixture({ requests: 200 }) });
    const { result, rerender } = renderHook(({ window }) => useStats(window), {
      wrapper: createWrapper(),
      initialProps: { window: "24h" as "24h" | "7d" | "all" },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("*/stats", async () => {
        await gate;
        return HttpResponse.json(statsFixture({ requests: 999 }));
      }),
    );
    rerender({ window: "7d" });

    expect(result.current.isPlaceholderData).toBe(true);
    expect(result.current.data?.requests).toBe(200);
    release();
    await waitFor(() => expect(result.current.data?.requests).toBe(999));
    expect(api.reads.length).toBeGreaterThan(0);
  });

  it("does not change its cache key as time passes", async () => {
    serveStatsApi();
    const client = makeQueryClient();
    const { rerender } = renderHook(() => useStats("24h"), { wrapper: createWrapper(client) });
    rerender();
    rerender();
    expect(client.getQueryCache().getAll()).toHaveLength(1);
  });

  it("refreshes every 30 seconds", () => {
    serveStatsApi();
    const client = makeQueryClient();
    renderHook(() => useStats("24h"), { wrapper: createWrapper(client) });
    const query = client.getQueryCache().find({ queryKey: queryKeys.statsWindow("24h") });
    expect(STATS_POLL_MS).toBe(30_000);
    expect(query?.observers[0]?.options.refetchInterval).toBe(30_000);
  });

  it("reports a failure without retrying a client error", async () => {
    let calls = 0;
    server.use(
      http.get("*/stats", () => {
        calls += 1;
        return HttpResponse.json({ detail: "bad" }, { status: 422 });
      }),
    );
    const { result } = renderHook(() => useStats("24h"), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(calls).toBe(1);
  });
});

describe("useRetryDeliveries", () => {
  it("posts to the retry endpoint and returns what happened", async () => {
    const api = serveStatsApi();
    api.retryResult = { retried: 5, sent: 4, failed: 1 };
    const { result } = renderHook(() => useRetryDeliveries(), { wrapper: createWrapper() });

    let outcome;
    await act(async () => {
      outcome = await result.current.mutateAsync();
    });

    expect(outcome).toEqual({ retried: 5, sent: 4, failed: 1 });
    expect(api.retries()).toBe(1);
  });

  it("refreshes every window of the numbers afterwards", async () => {
    const api = serveStatsApi();
    const client = makeQueryClient();
    const wrapper = createWrapper(client);
    const day = renderHook(() => useStats("24h"), { wrapper });
    const all = renderHook(() => useStats("all"), { wrapper });
    await waitFor(() => expect(day.result.current.isSuccess && all.result.current.isSuccess).toBe(true));
    const before = api.reads.length;
    const retry = renderHook(() => useRetryDeliveries(), { wrapper });

    await act(() => retry.result.current.mutateAsync());

    await waitFor(() => expect(api.reads.length).toBe(before + 2));
  });

  it("reports the result to the callback", async () => {
    serveStatsApi();
    const heard: unknown[] = [];
    const { result } = renderHook(() => useRetryDeliveries((outcome) => heard.push(outcome)), {
      wrapper: createWrapper(),
    });
    await act(() => result.current.mutateAsync());
    expect(heard).toEqual([{ retried: 2, sent: 2, failed: 0 }]);
  });

  it("reports a failure to the callback and still refreshes the numbers", async () => {
    const api = serveStatsApi();
    const client = makeQueryClient();
    const wrapper = createWrapper(client);
    const stats = renderHook(() => useStats("24h"), { wrapper });
    await waitFor(() => expect(stats.result.current.isSuccess).toBe(true));
    const before = api.reads.length;
    server.use(http.post("*/deliveries/retry", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    const heard: unknown[] = [];
    const retry = renderHook(() => useRetryDeliveries((outcome) => heard.push(outcome)), { wrapper });

    await act(async () => {
      await retry.result.current.mutateAsync().catch(() => undefined);
    });

    expect(heard).toHaveLength(1);
    expect(heard[0]).toBeInstanceOf(Error);
    await waitFor(() => expect(api.reads.length).toBeGreaterThan(before));
  });

  it("never repeats a resend on its own", async () => {
    serveStatsApi();
    let calls = 0;
    server.use(
      http.post("*/deliveries/retry", () => {
        calls += 1;
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );
    const { result } = renderHook(() => useRetryDeliveries(), { wrapper: createWrapper() });
    await act(async () => {
      await result.current.mutateAsync().catch(() => undefined);
    });
    expect(calls).toBe(1);
  });
});
