import { useState } from "react";

import { DeliveryCard } from "../components/DeliveryCard";
import { Notice, type NoticeKind } from "../components/Notice";
import { OutcomeTable } from "../components/OutcomeTable";
import { StatCard } from "../components/StatCard";
import { WindowSelect } from "../components/WindowSelect";
import { useConfig } from "../hooks/useConfig";
import { useRetryDeliveries } from "../hooks/useRetryDeliveries";
import { useStats } from "../hooks/useStats";
import { REVIEWER_AGREEMENT_CAVEAT, REVIEWER_AGREEMENT_HELP } from "../lib/copy";
import {
  formatConfidence,
  formatCost,
  formatCostPer1k,
  formatCount,
  formatLatency,
  formatShare,
} from "../lib/format";
import { describeRetryError, describeRetryResult } from "../lib/retry";
import { STATS_WINDOWS, type StatsWindow } from "../lib/windows";
import styles from "./OverviewPage.module.css";

type Message = { kind: NoticeKind; text: string };

/** D2: totals for a time window. Counts, money and delays, and what happened to the deliveries. */
export function OverviewPage() {
  const [window, setWindow] = useState<StatsWindow>("24h");
  const [message, setMessage] = useState<Message | null>(null);
  const stats = useStats(window);
  const config = useConfig();
  const retry = useRetryDeliveries((outcome) =>
    setMessage(
      outcome instanceof Error
        ? { kind: "error", text: describeRetryError(outcome) }
        : { kind: outcome.failed > 0 ? "info" : "success", text: describeRetryResult(outcome) },
    ),
  );

  const data = stats.data;

  return (
    <section>
      <header className={styles.header}>
        <h1>Overview</h1>
        <WindowSelect value={window} options={STATS_WINDOWS} onChange={setWindow} />
      </header>

      <div role="status" aria-label="Notifications" className={styles.notices}>
        {message && <Notice kind={message.kind} message={message.text} onDismiss={() => setMessage(null)} />}
      </div>

      {stats.isPending ? (
        <p role="status" aria-label="Loading">
          Loading the numbers…
        </p>
      ) : !data ? (
        <div className={styles.problem} role="alert">
          <span>The numbers could not be loaded.</span>
          <button type="button" onClick={() => void stats.refetch()}>
            Try again
          </button>
        </div>
      ) : (
        <>
          {stats.isRefetchError && (
            <div className={styles.problem} role="alert">
              The numbers could not be refreshed. They show the last version that was loaded.
            </div>
          )}
          <div className={styles.grid} aria-busy={stats.isPlaceholderData}>
            <StatCard
              title="Requests"
              value={formatCount(data.requests)}
              hint={window === "all" ? "since the first request" : "in this window"}
            />
            <StatCard
              title="Sent to a person"
              value={formatShare(data.human_review, data.requests)}
              hint={`${formatCount(data.human_review)} of ${formatCount(data.requests)} requests. ${formatCount(data.review.pending)} waiting for review now.`}
            />
            <StatCard
              title="Cost"
              value={formatCost(data.cost_usd)}
              hint={
                data.requests > 0
                  ? `${formatCostPer1k(data.cost_usd, data.requests)} per 1,000 requests`
                  : "No requests yet"
              }
            />
            <StatCard
              title="Latency, p95"
              value={formatLatency(data.latency_ms.p95)}
              hint={`average ${formatLatency(data.latency_ms.avg)}`}
            />
            <StatCard
              title="Reviewer agreement"
              value={data.reviewer_agreement.rate === null ? "No reviews yet" : formatConfidence(data.reviewer_agreement.rate)}
              hint={
                <>
                  {data.reviewer_agreement.resolved > 0 &&
                    `${formatCount(data.reviewer_agreement.agreed)} of ${formatCount(data.reviewer_agreement.resolved)} reviewed requests kept the suggestion. `}
                  {REVIEWER_AGREEMENT_CAVEAT}
                </>
              }
              details={REVIEWER_AGREEMENT_HELP}
            />
            <StatCard
              title="Requests where a tier failed"
              value={formatCount(data.degraded)}
              hint={data.degraded > 0 ? "The cascade fell back to what it had. See the logs for the cause." : "No tier failed."}
              tone={data.degraded > 0 ? "warning" : "normal"}
            />
          </div>

          <div className={styles.wide}>
            <OutcomeTable stats={data} />
            <DeliveryCard
              delivery={data.delivery}
              targetType={config.data?.target_type}
              retrying={retry.isPending}
              onRetry={() => {
                setMessage(null);
                retry.mutate();
              }}
            />
          </div>
        </>
      )}
    </section>
  );
}
