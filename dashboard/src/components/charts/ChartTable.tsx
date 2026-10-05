import type { ChartPoint } from "../../lib/chartData";
import { formatCost, formatCount, formatLatency } from "../../lib/format";
import styles from "./ChartTable.module.css";

/** The numbers behind the charts. Screen readers cannot read a drawing, and many people want exact values. */
export function ChartTable({ data }: { data: ChartPoint[] }) {
  return (
    <details className={styles.details}>
      <summary>Show the data as a table</summary>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <caption className={styles.caption}>Requests, cost and latency per period. Times are in UTC.</caption>
          <thead>
            <tr>
              <th scope="col">Period</th>
              <th scope="col">Requests</th>
              <th scope="col">Accepted</th>
              <th scope="col">Sent to a person</th>
              <th scope="col">Cost</th>
              <th scope="col">Cost so far</th>
              <th scope="col">Average latency</th>
            </tr>
          </thead>
          <tbody>
            {data.map((point) => (
              <tr key={point.start}>
                <th scope="row">{point.title}</th>
                <td>{formatCount(point.requests)}</td>
                <td>{formatCount(point.accepted)}</td>
                <td>{formatCount(point.human_review)}</td>
                <td>{formatCost(point.cost)}</td>
                <td>{formatCost(point.cumulativeCost)}</td>
                <td>{point.avgLatency === null ? "no requests" : formatLatency(point.avgLatency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
