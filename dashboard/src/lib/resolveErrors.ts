import { ApiError } from "../api/client";

export type ResolveProblem = {
  kind: "conflict" | "gone" | "invalid" | "failed";
  /** Text for the person, not the raw API message. */
  message: string;
  /** The request is no longer waiting, so its row should leave the list. */
  removeRow: boolean;
};

/** What a failed `POST /review/{id}` means for the person doing the review. */
export function describeResolveError(error: unknown): ResolveProblem {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return {
        kind: "conflict",
        message: "Someone else already handled this request. It was removed from your list.",
        removeRow: true,
      };
    }
    if (error.status === 404) {
      return {
        kind: "gone",
        message: "This request no longer exists. It was removed from your list.",
        removeRow: true,
      };
    }
    if (error.status === 422) {
      return {
        kind: "invalid",
        message: "That label is not accepted any more. Reload the page to get the current labels.",
        removeRow: false,
      };
    }
  }
  return {
    kind: "failed",
    message: "The decision could not be saved. Check the connection and try again.",
    removeRow: false,
  };
}
