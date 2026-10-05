import type { RequestItem } from "../api/endpoints";
import { formatConfidence } from "./format";

/** How a request ended, in words. */
export function describeOutcome(item: RequestItem): string {
  if (item.action === "accepted") return `Accepted by ${item.tier ?? "the cascade"}`;
  if (item.review_status === "pending") return "Waiting for a person";
  if (item.review_status === "resolved") return "Decided by a person";
  return "Sent to a person";
}

/** The label to show, and one line about where it came from. */
export function describeLabel(item: RequestItem): { label: string; note: string | null } {
  if (item.review_status === "resolved" && item.final_label) {
    const same = item.final_label === item.label;
    return {
      label: item.final_label,
      note: same ? "kept the model's label" : `model suggested ${item.label ?? "nothing"}`,
    };
  }
  if (item.action === "human_review") {
    return { label: item.label ?? "no suggestion", note: item.label ? "suggestion" : null };
  }
  return { label: item.label ?? "none", note: null };
}

export type DeliveryView = { text: string; tone: "ok" | "bad" | "neutral" };

export function describeDelivery(item: RequestItem): DeliveryView {
  switch (item.delivery_status) {
    case "sent":
      return { text: "Sent", tone: "ok" };
    case "failed":
      return { text: "Failed", tone: "bad" };
    case "pending":
      return { text: "Pending", tone: "neutral" };
    default:
      // A request waiting for a person is not sent until the person has decided.
      return { text: item.review_status === "pending" ? "Not sent yet" : "Not sent", tone: "neutral" };
  }
}

/** The model's confidence. A request no tier could answer has none: showing 0% would read as a measured score. */
export function describeConfidence(item: RequestItem): string {
  return item.label === null ? "n/a" : formatConfidence(item.confidence);
}
