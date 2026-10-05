/**
 * A confidence as a whole percentage. It is rounded down, never up: 0.995 reads "99%", so a
 * score is not shown as more certain than it is. The small epsilon keeps 0.29 from reading
 * "28%" because of floating point (0.29 * 100 is 28.999999999999996).
 */
export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${Math.floor(value * 100 + 1e-9)}%`;
}

/** How long ago a time was, in the largest fitting unit: "just now", "5 min", "3 h", "2 d". */
export function formatWaiting(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const seconds = Math.max(0, Math.floor((now - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  return `${Math.floor(hours / 24)} d`;
}
