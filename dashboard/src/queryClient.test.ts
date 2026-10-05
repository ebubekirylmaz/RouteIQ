import { describe, expect, it } from "vitest";

import { ApiError } from "./api/client";
import { queryClient } from "./queryClient";

function shouldRetry(failureCount: number, error: unknown): boolean {
  const retry = queryClient.getDefaultOptions().queries?.retry;
  if (typeof retry !== "function") throw new Error("retry should be a function");
  return retry(failureCount, error as Error);
}

describe("retry policy", () => {
  it.each([400, 404, 409, 422])("does not retry a %i, asking again will not change it", (status) => {
    expect(shouldRetry(0, new ApiError(status, "no"))).toBe(false);
  });

  it("retries a server error", () => {
    expect(shouldRetry(0, new ApiError(500, "boom"))).toBe(true);
    expect(shouldRetry(1, new ApiError(503, "busy"))).toBe(true);
  });

  it("retries a network failure", () => {
    expect(shouldRetry(0, new TypeError("Failed to fetch"))).toBe(true);
  });

  it("gives up after two retries", () => {
    expect(shouldRetry(2, new ApiError(500, "boom"))).toBe(false);
    expect(shouldRetry(2, new TypeError("Failed to fetch"))).toBe(false);
  });

  it("never retries a mutation, so a decision is not sent twice", () => {
    expect(queryClient.getDefaultOptions().mutations?.retry).toBe(false);
  });
});
