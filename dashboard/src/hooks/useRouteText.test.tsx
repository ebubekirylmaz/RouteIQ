import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { queryKeys } from "../api/queryKeys";
import { routeResult, serveRouteApi } from "../test/routeServer";
import { server } from "../test/server";
import { createWrapper, makeQueryClient } from "../test/utils";
import { useRouteText } from "./useRouteText";

describe("useRouteText", () => {
  it("sends the text and returns the answer", async () => {
    const api = serveRouteApi(() => routeResult({ label: "report_fraud", request_id: 7 }));
    const { result } = renderHook(() => useRouteText(), { wrapper: createWrapper() });

    let answer: unknown;
    await act(async () => {
      answer = await result.current.mutateAsync({ text: "someone used my card" });
    });

    expect(api.texts).toEqual(["someone used my card"]);
    expect(answer).toMatchObject({ label: "report_fraud", request_id: 7 });
  });

  it("tells the caller the text and the answer", async () => {
    serveRouteApi(() => routeResult({ request_id: 3 }));
    const heard: [string, number][] = [];
    const { result } = renderHook(() => useRouteText((text, answer) => heard.push([text, answer.request_id])), {
      wrapper: createWrapper(),
    });

    await act(() => result.current.mutateAsync({ text: "hello" }));

    expect(heard).toEqual([["hello", 3]]);
  });

  it("refreshes the history, the review queue and the statistics", async () => {
    serveRouteApi();
    const client = makeQueryClient();
    for (const key of [
      queryKeys.requestsPage({ limit: 25 }),
      queryKeys.reviewPage(20, 0),
      queryKeys.statsWindow("24h"),
      queryKeys.timeseries("24h"),
      queryKeys.config,
    ]) {
      client.setQueryData(key, {});
    }
    const { result } = renderHook(() => useRouteText(), { wrapper: createWrapper(client) });

    await act(() => result.current.mutateAsync({ text: "hello" }));

    const stale = (key: readonly unknown[]) => client.getQueryState(key)?.isInvalidated;
    expect(stale(queryKeys.requestsPage({ limit: 25 }))).toBe(true);
    expect(stale(queryKeys.reviewPage(20, 0))).toBe(true);
    expect(stale(queryKeys.statsWindow("24h"))).toBe(true);
    expect(stale(queryKeys.timeseries("24h"))).toBe(true);
    expect(stale(queryKeys.config)).toBe(false);
  });

  it("refreshes them after a failure too: the text may have been stored", async () => {
    serveRouteApi(() => HttpResponse.json({ detail: "boom" }, { status: 500 }));
    const client = makeQueryClient();
    client.setQueryData(queryKeys.requestsPage({ limit: 25 }), {});
    const { result } = renderHook(() => useRouteText(), { wrapper: createWrapper(client) });

    await act(() => result.current.mutateAsync({ text: "hello" }).catch(() => undefined));

    expect(client.getQueryState(queryKeys.requestsPage({ limit: 25 }))?.isInvalidated).toBe(true);
  });

  it("never sends the same text twice on its own, whatever the failure", async () => {
    let posts = 0;
    server.use(
      http.post("*/route", () => {
        posts += 1;
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );
    const { result } = renderHook(() => useRouteText(), { wrapper: createWrapper() });

    await act(() => result.current.mutateAsync({ text: "hello" }).catch(() => undefined));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(posts).toBe(1);
  });

  it("does not tell the caller about a failure as if it were an answer", async () => {
    serveRouteApi(() => HttpResponse.json({ detail: "boom" }, { status: 500 }));
    let heard = 0;
    const { result } = renderHook(() => useRouteText(() => (heard += 1)), { wrapper: createWrapper() });

    await act(() => result.current.mutateAsync({ text: "hello" }).catch(() => undefined));

    expect(heard).toBe(0);
  });
});
