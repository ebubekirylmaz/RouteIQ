import { describe, expect, it } from "vitest";

import spec from "../../openapi.json";
import { ApiError } from "../api/client";
import { routeResult } from "../test/routeServer";
import { MAX_TEXT_LENGTH, canSubmit, describeRoute, describeRouteError, normalizeText } from "./tryIt";

describe("the text limit", () => {
  it("is the one in the API schema", () => {
    const schema = spec as { components: { schemas: { RouteRequest: { properties: { text: { maxLength: number } } } } } };
    expect(MAX_TEXT_LENGTH).toBe(schema.components.schemas.RouteRequest.properties.text.maxLength);
  });
});

describe("normalizeText and canSubmit", () => {
  it("removes the spaces around a text", () => {
    expect(normalizeText("  my card \n")).toBe("my card");
  });

  it("keeps what is inside the text", () => {
    expect(normalizeText("a  b\nc")).toBe("a  b\nc");
  });

  it.each(["", " ", "\n\t  "])("does not send %j: there is nothing in it", (text) => {
    expect(canSubmit(text)).toBe(false);
  });

  it("sends a text with something in it", () => {
    expect(canSubmit(" a ")).toBe(true);
  });
});

describe("describeRoute", () => {
  it("names the tier that accepted a text", () => {
    expect(describeRoute(routeResult({ tier: "llm", label: "report_fraud", confidence: 0.936 }))).toEqual({
      headline: "Accepted by llm",
      label: "report_fraud",
      confidence: "93%",
      followUp: null,
      degraded: false,
    });
  });

  it("copes with an accepted text without a tier", () => {
    expect(describeRoute(routeResult({ tier: null })).headline).toBe("Accepted by the cascade");
  });

  it("sends a text the cascade was unsure about to a person, with the model's suggestion", () => {
    const view = describeRoute(routeResult({ action: "human_review", tier: "llm", label: "freeze_account", confidence: 0.61 }));
    expect(view.headline).toBe("Sent to a person");
    expect(view.followUp).toBe("review");
    expect(view.label).toBe("freeze_account");
    expect(view.confidence).toBe("61%");
  });

  it("says when no tier could answer, and shows no confidence instead of 0%", () => {
    const view = describeRoute(routeResult({ action: "human_review", tier: null, label: null, confidence: 0, degraded: true }));
    expect(view.headline).toBe("Sent to a person: no tier could answer");
    expect(view.label).toBe("none");
    expect(view.confidence).toBe("n/a");
    expect(view.degraded).toBe(true);
  });

  it("rounds a confidence down, never up", () => {
    expect(describeRoute(routeResult({ confidence: 0.995 })).confidence).toBe("99%");
  });
});

describe("describeRouteError", () => {
  it("explains a text that was refused", () => {
    expect(describeRouteError(new ApiError(422, "invalid request"))).toBe(
      "The text must have between 1 and 5,000 characters.",
    );
  });

  it.each([new ApiError(500, "boom"), new ApiError(404, "nope"), new TypeError("Failed to fetch"), null])(
    "asks to try again for %s",
    (error) => {
      expect(describeRouteError(error)).toMatch(/try again/i);
    },
  );

  it("names the limit of this service, which the demo makes smaller", () => {
    expect(describeRouteError(new ApiError(422, "invalid request"), 500)).toBe("The text must have between 1 and 500 characters.");
    expect(describeRouteError(new ApiError(413, "too big"), 500)).toBe("The text must have between 1 and 500 characters.");
  });

  it("says that a demo which is full has to be tried again later", () => {
    const message = describeRouteError(new ApiError(429, "the demo has reached its daily limit"));
    expect(message).toMatch(/limits how many texts/);
    expect(message).toMatch(/try again/);
    expect(message).not.toMatch(/daily limit of texts/);
  });

  it("never shows the raw API message", () => {
    expect(describeRouteError(new ApiError(500, "Traceback (most recent call last)"))).not.toMatch(/Traceback/);
  });
});
