import type { Stats } from "../api/endpoints";
import { formatCount, formatShare } from "../lib/format";
import styles from "./OutcomeTable.module.css";

/** How the requests of the window ended: accepted by which tier, or sent to a person. */
export function OutcomeTable({ stats }: { stats: Stats }) {
  const accepted = Object.entries(stats.accepted_by_tier).sort(([a], [b]) => a.localeCompare(b));
  const rows = [
    ...accepted.map(([tier, count]) => ({ label: `Accepted by ${tier}`, count })),
    { label: "Sent to a person", count: stats.human_review },
  ];

  return (
    <section className={styles.section} aria-labelledby="outcomes-title">
      <h2 id="outcomes-title" className={styles.title}>
        How requests ended
      </h2>
      {stats.requests === 0 ? (
        <p className={styles.empty}>No requests in this window.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Outcome</th>
              <th scope="col">Requests</th>
              <th scope="col">Share</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                <td>{formatCount(row.count)}</td>
                <td>{formatShare(row.count, stats.requests)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
