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

/**
 * Money in US dollars. Requests cost fractions of a cent, so a cent is not a useful unit:
 * below a dollar four decimals are shown, and a tiny non-zero amount never reads as free.
 */
export function formatCost(usd: number | null | undefined): string {
  if (usd === null || usd === undefined || Number.isNaN(usd)) return "n/a";
  if (usd === 0) return "$0.00";
  if (usd < 0.0001) return "<$0.0001";
  if (usd < 1) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

/** What 1,000 requests cost at this rate. The README's results use the same unit. */
export function formatCostPer1k(usd: number, requests: number): string {
  if (requests <= 0) return "n/a";
  return formatCost((usd / requests) * 1000);
}

/** A latency in milliseconds, in seconds from one second up. */
export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "n/a";
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** `part` of `whole` as a percentage with one decimal ("2.0%"), or "n/a" when there is no whole. */
export function formatShare(part: number, whole: number): string {
  if (whole <= 0) return "n/a";
  return `${((part / whole) * 100).toFixed(1)}%`;
}

/** A count with thousands separators, so 12345 reads "12,345". */
export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

/** A latency on an axis: the origin reads "0", not "<1 ms". */
export function formatLatencyTick(ms: number): string {
  return ms === 0 ? "0" : formatLatency(ms);
}

const timestamp = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
});

/** A moment as "Oct 5, 14:02:07 UTC". UTC like the charts, so the screens agree and the text does not depend on the machine. */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "n/a";
  return `${timestamp.format(date)} UTC`;
}

/** Cuts a text to `max` characters on a word boundary where possible, and marks the cut with an ellipsis. */
export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).trimEnd()}…`;
}
