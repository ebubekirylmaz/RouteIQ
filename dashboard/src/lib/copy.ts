/**
 * The API's own description of the reviewer agreement. A test compares it with the schema in
 * openapi.json, so the screen cannot drift from what the API says the number means.
 */
export const REVIEWER_AGREEMENT_HELP =
  "Share of human-reviewed requests where the reviewer kept the model's suggestion. " +
  "Only requests the model was unsure about are reviewed, so this is NOT the model's overall accuracy.";

/** Shown next to the number itself, because it is the sentence most likely to be missed. */
export const REVIEWER_AGREEMENT_CAVEAT =
  "Not the model's accuracy: only requests it was unsure about are reviewed.";
