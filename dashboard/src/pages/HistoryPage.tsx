import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { HistoryFilterBar } from "../components/HistoryFilterBar";
import { HistoryTable } from "../components/HistoryTable";
import { Pager } from "../components/Pager";
import { useConfig } from "../hooks/useConfig";
import { useRequests } from "../hooks/useRequests";
import { formatCount, formatTimestamp } from "../lib/format";
import {
  HISTORY_PAGE_SIZE,
  buildHistoryParams,
  hasActiveFilters,
  parseHistoryParams,
  type HistoryFilters,
} from "../lib/history";
import { clampPage } from "../lib/paging";
import styles from "./HistoryPage.module.css";

/**
 * D4: every request, newest first, with filters, text search and paging. The filters and the
 * page live in the address, so a view can be bookmarked, shared and reached with Back.
 */
export function HistoryPage() {
  const [params, setParams] = useSearchParams();
  const { filters, page } = parseHistoryParams(params);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const requests = useRequests(filters, page);
  const config = useConfig();
  const tiers = config.data?.tiers.map((tier) => tier.name) ?? [];

  const total = requests.data?.total ?? 0;
  const lastPage = clampPage(page - 1, total, HISTORY_PAGE_SIZE) + 1;
  // A link to a page past the end (the list shrank, or the number was typed) shows the last page
  // instead. `replace` so Back does not return to the page that does not exist.
  useEffect(() => {
    if (requests.data && !requests.isPlaceholderData && lastPage !== page) {
      setParams(buildHistoryParams(parseHistoryParams(params).filters, lastPage), { replace: true });
    }
  }, [requests.data, requests.isPlaceholderData, lastPage, page, params, setParams]);

  const goTo = (next: HistoryFilters, nextPage = 1) => {
    setExpandedId(null);
    setParams(buildHistoryParams(next, nextPage));
  };

  const filtered = hasActiveFilters(filters);

  return (
    <section>
      <header className={styles.header}>
        <div>
          <h1>History</h1>
          <p className={styles.sub}>
            Every request, newest first. Times are in UTC. The list does not update by itself.
          </p>
        </div>
        <div className={styles.refresh}>
          {requests.data && <span>Updated {formatTimestamp(new Date(requests.dataUpdatedAt).toISOString())}</span>}
          <button type="button" disabled={requests.isFetching} onClick={() => void requests.refetch()}>
            {requests.isFetching ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      <HistoryFilterBar filters={filters} tiers={tiers} onChange={(next) => goTo(next)} />

      {requests.isPending ? (
        <p role="status" aria-label="Loading">
          Loading the history…
        </p>
      ) : !requests.data ? (
        <div className={styles.problem} role="alert">
          <span>The history could not be loaded.</span>
          <button type="button" onClick={() => void requests.refetch()}>
            Try again
          </button>
        </div>
      ) : (
        <>
          {requests.isRefetchError && (
            <div className={styles.problem} role="alert">
              The history could not be refreshed. It shows the last version that was loaded.
            </div>
          )}

          <p className={styles.count} role="status">
            {formatCount(total)} {total === 1 ? "request" : "requests"}
            {filtered ? " match these filters" : ""}
          </p>

          {requests.data.items.length === 0 ? (
            <p className={styles.empty}>{filtered ? "No requests match these filters." : "No requests yet."}</p>
          ) : (
            <>
              <div aria-busy={requests.isPlaceholderData} className={requests.isPlaceholderData ? styles.busy : undefined}>
                <HistoryTable
                  items={requests.data.items}
                  expandedId={expandedId}
                  onToggle={(id) => setExpandedId((current) => (current === id ? null : id))}
                />
              </div>
              <Pager
                label="Pages of the history"
                page={page - 1}
                pageSize={HISTORY_PAGE_SIZE}
                shown={requests.data.items.length}
                total={total}
                disabled={requests.isPlaceholderData}
                onPageChange={(zeroBased) => goTo(filters, zeroBased + 1)}
              />
            </>
          )}
        </>
      )}
    </section>
  );
}
