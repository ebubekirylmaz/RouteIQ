import { HttpResponse, http } from "msw";

import type { Evaluation } from "../api/endpoints";
import { server } from "./server";

/** What the API answers for CLINC150 (rounded), so the tests read like the README table. */
export function evaluationReport(overrides: Partial<Evaluation> = {}): Evaluation {
  return {
    domain: "clinc150",
    split: "test",
    n: 300,
    data_source: "public",
    tiers: [
      { name: "baseline", accept_threshold: 0.7 },
      { name: "llm", accept_threshold: 0.9 },
    ],
    setups: [
      {
        name: "Baseline only", description: "Every example is answered by the baseline.",
        accuracy: 0.9167, accuracy_low: 0.88, accuracy_high: 0.943, macro_f1: 0.8987,
        cost_per_1k_usd: 0, p50_ms: 0.2, p95_ms: 0.2, assumes_reviewer_always_right: false,
      },
      {
        name: "LLM only", description: "Every example is answered by the LLM.",
        accuracy: 0.9833, accuracy_low: 0.962, accuracy_high: 0.993, macro_f1: 0.9763,
        cost_per_1k_usd: 0.0118, p50_ms: 599.5, p95_ms: 2169, assumes_reviewer_always_right: false,
      },
      {
        name: "Cascade (baseline then LLM)", description: "The baseline answers when it is at least 0.7 sure; otherwise the LLM answers.",
        accuracy: 0.9833, accuracy_low: 0.962, accuracy_high: 0.993, macro_f1: 0.9763,
        cost_per_1k_usd: 0.0064, p50_ms: 559, p95_ms: 1934, assumes_reviewer_always_right: false,
      },
      {
        name: "Cascade + human review", description: "As the cascade, but a person answers when the LLM is not 0.9 sure. This assumes the person is always right.",
        accuracy: 0.9933, accuracy_low: 0.976, accuracy_high: 0.998, macro_f1: 0.9889,
        cost_per_1k_usd: 0.0064, p50_ms: 559, p95_ms: 1934, assumes_reviewer_always_right: true,
      },
    ],
    cascade: {
      groups: [
        { kind: "accepted", tier: "baseline", count: 139, correct: 139 },
        { kind: "accepted", tier: "llm", count: 155, correct: 153 },
        { kind: "human_review", tier: null, count: 6, correct: 3 },
      ],
      escalated: 161,
    },
    calibration: [
      {
        tier: "baseline", ece: 0.269,
        bins: [
          { lower: 0, upper: 0.5, n: 74, mean_confidence: 0.39, accuracy: 0.68 },
          { lower: 0.5, upper: 0.7, n: 87, mean_confidence: 0.61, accuracy: 0.99 },
          { lower: 0.7, upper: 0.9, n: 124, mean_confidence: 0.79, accuracy: 1 },
          { lower: 0.9, upper: 0.99, n: 15, mean_confidence: 0.92, accuracy: 1 },
        ],
      },
      {
        tier: "llm", ece: 0.0117,
        bins: [
          { lower: 0.5, upper: 0.7, n: 1, mean_confidence: 0.56, accuracy: 0 },
          { lower: 0.99, upper: 1, n: 289, mean_confidence: 1, accuracy: 0.99 },
        ],
      },
    ],
    ...overrides,
  };
}

export type FakeEvaluationApi = { reads: number };

export function serveEvaluationApi(report: Evaluation = evaluationReport()): FakeEvaluationApi {
  const api: FakeEvaluationApi = { reads: 0 };
  server.use(
    http.get("*/evaluation", () => {
      api.reads += 1;
      return HttpResponse.json(report);
    }),
  );
  return api;
}

export function failEvaluation(status: number, detail: string) {
  server.use(http.get("*/evaluation", () => HttpResponse.json({ detail }, { status })));
}
