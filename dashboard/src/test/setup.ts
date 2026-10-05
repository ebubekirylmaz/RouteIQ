import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

// The browser resolves "/review" against the page. Node's fetch needs an absolute URL, so the
// tests resolve it against the jsdom origin, the same thing the browser does.
const nodeFetch = globalThis.fetch;
globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
  nodeFetch(
    typeof input === "string" && input.startsWith("/") ? new URL(input, window.location.origin) : input,
    init,
  );

// A request nobody expected is a bug in the test or in the code: fail loudly.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
