import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { queryKeys } from "../api/queryKeys";
import type { ChartRange } from "../lib/chartRanges";
import { server } from "../test/server";
import { makePoints, serveTimeseriesApi } from "../test/timeseriesServer";
import { createWrapper, makeQueryClient } from "../test/utils";
import { TIMESERIES_POLL_MS, useTimeseries } from "./useTimeseries";

const minutesAgo = (iso: string | null | undefined) => (Date.now() - Date.parse(iso ?? "")) / 60_000;

describe("useTimeseries", () => {
  it("asks for hourly buckets over the last 24 hours", async () => {
    const api = serveTimeseriesApi();
    const { result } = renderHook(() => useTimeseries("24h"), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const url = api.reads[0];
    expect(url?.searchParams.get("bucket")).toBe("hour");
    expect(minutesAgo(url?.searchParams.get("since"))).toBeGreaterThan(24 * 60 - 1);
    expect(minutesAgo(url?.searchParams.get("since"))).toBeLessThan(24 * 60 + 1);
    expect(minutesAgo(url?.searchParams.get("until"))).toBeLessThan(1);
    expect(result.current.data?.points).toHaveLength(24);
  });

  it.each([
    ["7d", 7],
    ["30d", 30],
  ] as const)("asks for daily buckets over the last %s", async (range, days) => {
    const api = serveTimeseriesApi(makePoints(days, "day"));
    const { result } = renderHook(() => useTimeseries(range), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.reads[0]?.searchParams.get("bucket")).toBe("day");
    expect(minutesAgo(api.reads[0]?.searchParams.get("since"))).toBeGreaterThan(days * 24 * 60 - 1);
  });

  it("keeps one cache entry per range", async () => {
    serveTimeseriesApi();
    const client = makeQueryClient();
    const { result, rerender } = renderHook(({ range }) => useTimeseries(range), {
      wrapper: createWrapper(client),
      initialProps: { range: "24h" as ChartRange },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    rerender({ range: "7d" });
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(false));

    expect(client.getQueryData(queryKeys.timeseries("24h"))).toBeDefined();
    expect(client.getQueryData(queryKeys.timeseries("7d"))).toBeDefined();
  });

  it("does not change its cache key as time passes", () => {
    serveTimeseriesApi();
    const client = makeQueryClient();
    const { rerender } = renderHook(() => useTimeseries("24h"), { wrapper: createWrapper(client) });
    rerender();
    rerender();
    expect(client.getQueryCache().getAll()).toHaveLength(1);
  });

  it("keeps the previous range on screen while the next one loads", async () => {
    serveTimeseriesApi(makePoints(24));
    const { result, rerender } = renderHook(({ range }) => useTimeseries(range), {
      wrapper: createWrapper(),
      initialProps: { range: "24h" as ChartRange },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("*/stats/timeseries", async () => {
        await gate;
        return HttpResponse.json({ bucket: "day", since: "x", until: "y", points: makePoints(7, "day") });
      }),
    );
    rerender({ range: "7d" });

    expect(result.current.isPlaceholderData).toBe(true);
    expect(result.current.data?.points).toHaveLength(24);
    release();
    await waitFor(() => expect(result.current.data?.points).toHaveLength(7));
  });

  it("refreshes once a minute", () => {
    serveTimeseriesApi();
    const client = makeQueryClient();
    renderHook(() => useTimeseries("24h"), { wrapper: createWrapper(client) });
    const query = client.getQueryCache().find({ queryKey: queryKeys.timeseries("24h") });
    expect(TIMESERIES_POLL_MS).toBe(60_000);
    expect(query?.observers[0]?.options.refetchInterval).toBe(60_000);
  });

  it("reports a refusal without retrying it", async () => {
    let calls = 0;
    server.use(
      http.get("*/stats/timeseries", () => {
        calls += 1;
        return HttpResponse.json({ detail: "the range covers more than 1000 buckets" }, { status: 422 });
      }),
    );
    const { result } = renderHook(() => useTimeseries("24h"), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(calls).toBe(1);
  });
});
