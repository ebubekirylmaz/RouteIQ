import { ApiError } from "../api/client";
import type { Evaluation, EvaluationSetup } from "../api/endpoints";
import { formatShare } from "./format";

type Group = Evaluation["cascade"]["groups"][number];
type Bin = Evaluation["calibration"][number]["bins"][number];

/** A share between 0 and 1 as a percentage with one decimal: 0.9833 reads "98.3%". */
export function formatAccuracy(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** The 95% interval of an accuracy, for the table and the tooltip. */
export function formatInterval(low: number, high: number): string {
  return `${formatAccuracy(low)} to ${formatAccuracy(high)}`;
}

/** What one more mistake does to an accuracy, in points: the size of the smallest possible difference. */
export function pointsPerMistake(n: number): string {
  return n > 0 ? (100 / n).toFixed(1) : "n/a";
}

export type AccuracyRow = {
  name: string;
  /** Percent, 0 to 100: the unit of the axis. */
  accuracy: number;
  /** How far the interval reaches down and up from the accuracy, for the error bar. */
  error: [number, number];
  assumesReviewer: boolean;
  label: string;
};

export function accuracyRows(setups: EvaluationSetup[]): AccuracyRow[] {
  return setups.map((setup) => ({
    name: setup.name,
    accuracy: setup.accuracy * 100,
    error: [(setup.accuracy - setup.accuracy_low) * 100, (setup.accuracy_high - setup.accuracy) * 100],
    assumesReviewer: setup.assumes_reviewer_always_right,
    label: `${formatAccuracy(setup.accuracy)} (${formatInterval(setup.accuracy_low, setup.accuracy_high)})`,
  }));
}

/** The line for one group of examples in the table of what the cascade did. */
export function describeGroup(group: Group, n: number) {
  const accepted = group.kind === "accepted";
  return {
    outcome: accepted ? `Accepted by ${group.tier ?? "the cascade"}` : "Sent to a person",
    count: group.count,
    share: formatShare(group.count, n),
    right: group.count === 0 ? "n/a" : `${group.correct} of ${group.count}`,
    note: accepted ? null : "the model's suggestion",
  };
}

/** A confidence range as percentages: 0.7 to 0.9 reads "70% to 90%". */
export function binRange(bin: Bin): string {
  const percent = (value: number) => `${Math.round(value * 100)}%`;
  return `${percent(bin.lower)} to ${percent(bin.upper)}`;
}

/** Few examples in a range say little about it. */
export const SMALL_BIN = 10;

/** The API answers 404 when nothing was recorded for the configuration. That is an answer, not a failure. */
export const isNotAvailable = (error: unknown): boolean => error instanceof ApiError && error.status === 404;
