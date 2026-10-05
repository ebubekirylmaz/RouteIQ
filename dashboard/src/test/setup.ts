import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { cloneElement, type ReactElement } from "react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

import { server } from "./server";

// The browser resolves "/review" against the page. Node's fetch needs an absolute URL, so the
// tests resolve it against the jsdom origin, the same thing the browser does.
const nodeFetch = globalThis.fetch;
globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
  nodeFetch(
    typeof input === "string" && input.startsWith("/") ? new URL(input, window.location.origin) : input,
    init,
  );

// jsdom has no layout engine and no ResizeObserver. Recharts measures its container with one.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub;

// ResponsiveContainer measures its parent, and jsdom has no layout, so it would draw nothing.
// The tests give the chart a fixed size instead. In a browser the real container is used.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children, height }: { children: ReactElement<{ width?: number; height?: number }>; height?: number | string }) =>
      cloneElement(children, { width: 640, height: typeof height === "number" ? height : 260 }),
  };
});

// A request nobody expected is a bug in the test or in the code: fail loudly.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
