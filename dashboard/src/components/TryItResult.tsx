import { Link } from "react-router-dom";

import type { RouteResult } from "../api/endpoints";
import { formatCost, formatLatency, truncate } from "../lib/format";
import { describeRoute } from "../lib/tryIt";
import styles from "./TryItResult.module.css";

const TEXT_PREVIEW = 80;

type Props = { text: string; result: RouteResult };

/** What the cascade did with one text, and where to find the stored request. */
export function TryItResult({ text, result }: Props) {
  const view = describeRoute(result);

  return (
    <section className={styles.card} aria-labelledby="try-result-title">
      <p className={styles.about}>Result for “{truncate(text, TEXT_PREVIEW)}”</p>
      <h2 id="try-result-title" className={styles.headline}>
        {view.headline}
      </h2>

      <dl className={styles.facts}>
        <dt>Label</dt>
        <dd>{view.label}</dd>
        <dt>Confidence</dt>
        <dd>{view.confidence}</dd>
        <dt>Tier</dt>
        <dd>{result.tier ?? "none"}</dd>
        <dt>Cost</dt>
        <dd>{formatCost(result.cost_usd)}</dd>
        <dt>Latency</dt>
        <dd>{formatLatency(result.latency_ms)}</dd>
        <dt>Request</dt>
        <dd>#{result.request_id}</dd>
      </dl>

      {view.degraded && <p className={styles.warn}>A tier failed while this text was routed.</p>}

      <p className={styles.links}>
        {view.followUp === "review" && (
          <>
            <span>It now waits for a person. </span>
            <Link to="/review">Open the review queue</Link>
            <span> · </span>
          </>
        )}
        <Link to="/history">See it in the history</Link>
      </p>
    </section>
  );
}
