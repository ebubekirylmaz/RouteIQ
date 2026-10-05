/** Number of pages for a total, at least 1 so an empty list still has a first page. */
export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

/**
 * Keeps a page number inside the list. After the last row of the last page is resolved, the
 * page is empty but earlier pages remain: step back instead of showing an empty page.
 */
export function clampPage(page: number, total: number, pageSize: number): number {
  return Math.min(Math.max(0, page), pageCount(total, pageSize) - 1);
}

/** "21-40 of 87", or "0 of 0" for an empty list. `shown` is the number of rows on the page. */
export function describeRange(page: number, pageSize: number, shown: number, total: number): string {
  if (total === 0 || shown === 0) return `0 of ${total}`;
  const from = page * pageSize + 1;
  return `${from}-${from + shown - 1} of ${total}`;
}
