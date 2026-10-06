import { ApiError } from "../api/client";
import type { RouteResult } from "../api/endpoints";
import { formatConfidence } from "./format";

/** The longest text the API accepts. A test compares it with the schema. */
export const MAX_TEXT_LENGTH = 5000;

/** What gets sent: without the spaces around it. Empty means there is nothing to send. */
export const normalizeText = (text: string): string => text.trim();

export const canSubmit = (text: string): boolean => normalizeText(text).length > 0;

export type RouteView = {
  /** What happened, in a few words. */
  headline: string;
  /** The model's label, or "none" when no tier produced one. */
  label: string;
  confidence: string;
  /** Where a person comes in, or null when nobody needs to. */
  followUp: "review" | null;
  /** True when a tier failed while this text was routed. */
  degraded: boolean;
};

/** The result in words. A request nobody could answer has no label, and no confidence to show. */
export function describeRoute(result: RouteResult): RouteView {
  const answered = result.label !== null;
  const base = {
    label: result.label ?? "none",
    confidence: answered ? formatConfidence(result.confidence) : "n/a",
    degraded: result.degraded,
  };
  if (result.action === "accepted") {
    return { ...base, headline: `Accepted by ${result.tier ?? "the cascade"}`, followUp: null };
  }
  return {
    ...base,
    headline: answered ? "Sent to a person" : "Sent to a person: no tier could answer",
    followUp: "review",
  };
}

/**
 * What to tell somebody whose text could not be routed. The API's own message is never shown.
 * `maxLength` is the limit of this service: the public demo accepts shorter texts.
 */
export function describeRouteError(error: unknown, maxLength: number = MAX_TEXT_LENGTH): string {
  if (error instanceof ApiError && (error.status === 422 || error.status === 413)) {
    return `The text must have between 1 and ${maxLength.toLocaleString("en-US")} characters.`;
  }
  if (error instanceof ApiError && error.status === 429) {
    return "The demo limits how many texts can be sent. Please wait a little and try again.";
  }
  return "The text could not be routed. Try again, and if it keeps failing, check that the API is running.";
}
