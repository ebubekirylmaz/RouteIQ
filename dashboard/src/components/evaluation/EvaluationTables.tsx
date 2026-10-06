import type { Evaluation } from "../../api/endpoints";
import { formatCost, formatLatency } from "../../lib/format";
import { SMALL_BIN, binRange, describeGroup, formatAccuracy, formatInterval, pointsPerMistake } from "../../lib/evaluation";
import styles from "./EvaluationTables.module.css";

/** The exact numbers behind the chart, and the ones the chart does not show. */
export function SetupsTable({ report }: { report: Evaluation }) {
  return (
    <section className={styles.section} aria-labelledby="setups-title">
      <h2 id="setups-title">The four setups</h2>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Setup</th>
              <th scope="col">Accuracy</th>
              <th scope="col">95% interval</th>
              <th scope="col">Macro-F1</th>
              <th scope="col">Cost per 1,000 requests</th>
              <th scope="col">Median latency</th>
              <th scope="col">95th percentile latency</th>
            </tr>
          </thead>
          <tbody>
            {report.setups.map((setup) => (
              <tr key={setup.name}>
                <th scope="row">
                  {setup.name}
                  <small className={setup.assumes_reviewer_always_right ? styles.assumption : undefined}>{setup.description}</small>
                </th>
                <td>{formatAccuracy(setup.accuracy)}</td>
                <td>{formatInterval(setup.accuracy_low, setup.accuracy_high)}</td>
                <td>{setup.macro_f1.toFixed(3)}</td>
                <td>{formatCost(setup.cost_per_1k_usd)}</td>
                <td>{formatLatency(setup.p50_ms)}</td>
                <td>{formatLatency(setup.p95_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.note}>
        The interval shows how far the accuracy could move on other examples of the same kind. With {report.n} examples one more
        mistake changes an accuracy by {pointsPerMistake(report.n)} points, so differences smaller than the intervals can be noise.
      </p>
    </section>
  );
}

/** What the cascade did with the examples, using the thresholds of the configuration. */
export function CascadeTable({ report }: { report: Evaluation }) {
  const thresholds = report.tiers.map((tier) => `${tier.name} ${tier.accept_threshold}`).join(", ");
  return (
    <section className={styles.section} aria-labelledby="cascade-title">
      <h2 id="cascade-title">How the cascade handled the examples</h2>
      <p className={styles.lead}>With the thresholds of the configuration: {thresholds}.</p>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Outcome</th>
              <th scope="col">Examples</th>
              <th scope="col">Share</th>
              <th scope="col">Right label</th>
            </tr>
          </thead>
          <tbody>
            {report.cascade.groups.map((group) => {
              const line = describeGroup(group, report.n);
              return (
                <tr key={`${group.kind}-${group.tier ?? ""}`}>
                  <th scope="row">{line.outcome}</th>
                  <td>{line.count}</td>
                  <td>{line.share}</td>
                  <td>
                    {line.right}
                    {line.note && <span className={styles.small}> ({line.note})</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className={styles.note}>{report.cascade.escalated} examples needed more than one tier.</p>
    </section>
  );
}

/** Whether a tier's confidence means what it says. */
export function CalibrationSection({ report }: { report: Evaluation }) {
  return (
    <section className={styles.section} aria-labelledby="calibration-title">
      <h2 id="calibration-title">Calibration</h2>
      <p className={styles.lead}>
        When a tier says it is 90% sure, is it right about 90% of the time? The expected calibration error (ECE) is the average gap
        between what a tier claims and how often it was right: 0 is perfect.
      </p>
      {report.calibration.map((tier) => (
        <div key={tier.tier}>
          <h3>
            {tier.tier}: ECE {tier.ece.toFixed(3)}
          </h3>
          <div className={styles.scroll}>
            <table className={styles.table}>
              <caption className={styles.srOnly}>{`Calibration of the ${tier.tier} tier`}</caption>
              <thead>
                <tr>
                  <th scope="col">Confidence</th>
                  <th scope="col">Examples</th>
                  <th scope="col">Mean confidence</th>
                  <th scope="col">Right</th>
                </tr>
              </thead>
              <tbody>
                {tier.bins.map((bin) => (
                  <tr key={`${bin.lower}-${bin.upper}`}>
                    <th scope="row">{binRange(bin)}</th>
                    <td>{bin.n}</td>
                    <td>{formatAccuracy(bin.mean_confidence)}</td>
                    <td>{formatAccuracy(bin.accuracy)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      <p className={styles.note}>A range with fewer than {SMALL_BIN} examples says little: one mistake moves its figure a lot.</p>
    </section>
  );
}
