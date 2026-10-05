import { Fragment } from "react";

import type { RequestItem } from "../api/endpoints";
import { formatCost, formatLatency, formatTimestamp, truncate } from "../lib/format";
import { describeConfidence, describeDelivery, describeLabel, describeOutcome } from "../lib/requestView";
import styles from "./HistoryTable.module.css";

const TEXT_PREVIEW = 80;
const COLUMNS = 8;

type Props = {
  items: RequestItem[];
  expandedId: number | null;
  onToggle: (id: number) => void;
};

/** One row per request. A row opens to show the whole text and the details that do not fit a column. */
export function HistoryTable({ items, expandedId, onToggle }: Props) {
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <caption className={styles.caption}>Requests, newest first. Times are in UTC.</caption>
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Request</th>
            <th scope="col">Outcome</th>
            <th scope="col">Label</th>
            <th scope="col">Confidence</th>
            <th scope="col">Cost</th>
            <th scope="col">Latency</th>
            <th scope="col">Delivery</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <Row key={item.id} item={item} open={item.id === expandedId} onToggle={onToggle} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({ item, open, onToggle }: { item: RequestItem; open: boolean; onToggle: (id: number) => void }) {
  const label = describeLabel(item);
  const delivery = describeDelivery(item);
  const detailsId = `request-${item.id}-details`;

  return (
    <Fragment>
      <tr className={open ? styles.open : undefined}>
        <td className={styles.nowrap}>{formatTimestamp(item.created_at)}</td>
        <td>
          <button
            type="button"
            className={styles.toggle}
            aria-expanded={open}
            aria-controls={open ? detailsId : undefined}
            onClick={() => onToggle(item.id)}
          >
            <span className={styles.text}>{truncate(item.text, TEXT_PREVIEW)}</span>
            <span className={styles.srOnly}>{open ? " (hide details)" : " (show details)"}</span>
          </button>
        </td>
        <td>
          {describeOutcome(item)}
          {item.degraded && <span className={styles.badge}>A tier failed</span>}
        </td>
        <td>
          {label.label}
          {label.note && <span className={styles.note}>{label.note}</span>}
        </td>
        <td>{describeConfidence(item)}</td>
        <td>{formatCost(item.cost_usd)}</td>
        <td>{formatLatency(item.latency_ms)}</td>
        <td>
          <span className={`${styles.delivery} ${styles[delivery.tone]}`}>{delivery.text}</span>
        </td>
      </tr>
      {open && (
        <tr className={styles.details}>
          <td colSpan={COLUMNS} id={detailsId}>
            <Details item={item} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

function Details({ item }: { item: RequestItem }) {
  return (
    <div>
      <p className={styles.full}>{item.text}</p>
      <dl className={styles.facts}>
        <dt>Request</dt>
        <dd>#{item.id}</dd>
        <dt>Tier</dt>
        <dd>{item.tier ?? "n/a"}</dd>
        <dt>Model's label</dt>
        <dd>{item.label ?? "none"}</dd>
        {item.review_status === "resolved" && (
          <>
            <dt>Person's label</dt>
            <dd>{item.final_label ?? "n/a"}</dd>
            <dt>Decided</dt>
            <dd>{formatTimestamp(item.resolved_at)}</dd>
          </>
        )}
        {item.delivery_status === "sent" && (
          <>
            <dt>Delivered</dt>
            <dd>{formatTimestamp(item.delivered_at)}</dd>
          </>
        )}
        {item.delivery_error && (
          <>
            <dt>Delivery problem</dt>
            <dd>{item.delivery_error}</dd>
          </>
        )}
      </dl>
    </div>
  );
}
