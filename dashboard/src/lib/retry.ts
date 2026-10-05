import { ApiError } from "../api/client";
import type { RetryResult } from "../api/endpoints";

/** What happened when failed deliveries were sent again. */
export function describeRetryResult(result: RetryResult): string {
  if (result.retried === 0) return "Nothing needed to be resent.";
  const noun = result.retried === 1 ? "delivery" : "deliveries";
  return `Retried ${result.retried} ${noun}: ${result.sent} sent, ${result.failed} failed.`;
}

export function describeRetryError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return "No delivery target is configured.";
  return "The deliveries could not be resent. Check the connection and try again.";
}
