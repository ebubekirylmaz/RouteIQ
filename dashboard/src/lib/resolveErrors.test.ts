import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { describeResolveError } from "./resolveErrors";

describe("describeResolveError", () => {
  it("explains a conflict as somebody else being faster, and removes the row", () => {
    const problem = describeResolveError(new ApiError(409, "request is not pending review"));
    expect(problem.kind).toBe("conflict");
    expect(problem.removeRow).toBe(true);
    expect(problem.message).toMatch(/someone else/i);
  });

  it("explains a missing request, and removes the row", () => {
    const problem = describeResolveError(new ApiError(404, "request not found"));
    expect(problem).toMatchObject({ kind: "gone", removeRow: true });
  });

  it("keeps the row when the label was refused, so the person can pick another one", () => {
    const problem = describeResolveError(new ApiError(422, "unknown label"));
    expect(problem).toMatchObject({ kind: "invalid", removeRow: false });
    expect(problem.message).toMatch(/reload/i);
  });

  it.each([
    new ApiError(500, "boom"),
    new ApiError(503, "busy"),
    new TypeError("Failed to fetch"),
    "something",
    null,
  ])("keeps the row and asks to try again for %s", (error) => {
    const problem = describeResolveError(error);
    expect(problem).toMatchObject({ kind: "failed", removeRow: false });
    expect(problem.message).toMatch(/try again/i);
  });

  it("never shows the raw API message to the person", () => {
    const text = describeResolveError(new ApiError(409, "request is not pending review")).message;
    expect(text).not.toContain("pending review");
  });
});
