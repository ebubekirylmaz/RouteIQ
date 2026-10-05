import { useEffect, useState, type FormEvent } from "react";

import { MAX_SEARCH_LENGTH, hasActiveFilters, type HistoryFilters } from "../lib/history";
import styles from "./HistoryFilterBar.module.css";

type Props = {
  filters: HistoryFilters;
  /** Names of the tiers in the config. Without them there is nothing to choose, so the choice is left out. */
  tiers: string[];
  onChange: (filters: HistoryFilters) => void;
};

/** Sets or removes one key. An empty choice means "any", which is the key being absent. */
function setFilter<K extends keyof HistoryFilters>(filters: HistoryFilters, key: K, value: HistoryFilters[K] | ""): HistoryFilters {
  const next = { ...filters };
  if (value === "" || value === undefined) delete next[key];
  else next[key] = value as HistoryFilters[K];
  return next;
}

export function HistoryFilterBar({ filters, tiers, onChange }: Props) {
  // The text is only applied on Enter or Search, so typing does not ask the API for every letter.
  const [draft, setDraft] = useState(filters.q ?? "");
  useEffect(() => setDraft(filters.q ?? ""), [filters.q]);

  // A tier from a link that the config does not know is still shown, so the filter is not invisible.
  const tierOptions = filters.tier && !tiers.includes(filters.tier) ? [...tiers, filters.tier] : tiers;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onChange(setFilter(filters, "q", draft.trim()));
  };

  return (
    <form className={styles.bar} onSubmit={submit} role="search" aria-label="Filter the history">
      <label className={`${styles.field} ${styles.search}`}>
        <span>Search text</span>
        <input
          type="search"
          value={draft}
          maxLength={MAX_SEARCH_LENGTH}
          placeholder="Part of a request"
          onChange={(event) => setDraft(event.target.value)}
        />
      </label>

      <label className={styles.field}>
        <span>Outcome</span>
        <select
          value={filters.action ?? ""}
          onChange={(event) => onChange(setFilter(filters, "action", event.target.value as HistoryFilters["action"] | ""))}
        >
          <option value="">Any</option>
          <option value="accepted">Accepted by the cascade</option>
          <option value="human_review">Sent to a person</option>
        </select>
      </label>

      <label className={styles.field}>
        <span>Review</span>
        <select
          value={filters.review_status ?? ""}
          onChange={(event) => onChange(setFilter(filters, "review_status", event.target.value as HistoryFilters["review_status"] | ""))}
        >
          <option value="">Any</option>
          <option value="pending">Waiting for a person</option>
          <option value="resolved">Decided by a person</option>
        </select>
      </label>

      <label className={styles.field}>
        <span>Delivery</span>
        <select
          value={filters.delivery_status ?? ""}
          onChange={(event) => onChange(setFilter(filters, "delivery_status", event.target.value as HistoryFilters["delivery_status"] | ""))}
        >
          <option value="">Any</option>
          <option value="sent">Sent</option>
          <option value="failed">Failed</option>
          <option value="pending">Pending</option>
        </select>
      </label>

      {tierOptions.length > 0 && (
        <label className={styles.field}>
          <span>Tier</span>
          <select value={filters.tier ?? ""} onChange={(event) => onChange(setFilter(filters, "tier", event.target.value))}>
            <option value="">Any</option>
            {tierOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className={styles.check}>
        <input
          type="checkbox"
          checked={filters.degraded === true}
          onChange={(event) => onChange(setFilter(filters, "degraded", event.target.checked ? true : ""))}
        />
        <span>Only where a tier failed</span>
      </label>

      <div className={styles.actions}>
        <button type="submit">Search</button>
        <button type="button" disabled={!hasActiveFilters(filters) && draft === ""} onClick={() => onChange({})}>
          Clear filters
        </button>
      </div>
    </form>
  );
}
