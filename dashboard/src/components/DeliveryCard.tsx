import type { Stats } from "../api/endpoints";
import { formatCount } from "../lib/format";
import styles from "./DeliveryCard.module.css";

type Props = {
  delivery: Stats["delivery"];
  /** Type of the configured target, null when decisions are not sent anywhere, undefined while unknown. */
  targetType: string | null | undefined;
  retrying: boolean;
  onRetry: () => void;
};

/** What happened to the decisions sent on to the target system, and a way to resend the stuck ones. */
export function DeliveryCard({ delivery, targetType, retrying, onRetry }: Props) {
  return (
    <section className={styles.card} aria-labelledby="delivery-title">
      <h2 id="delivery-title" className={styles.title}>
        Deliveries to the target system
      </h2>

      {targetType === null ? (
        <p className={styles.none}>No delivery target is configured, so decisions are not sent anywhere.</p>
      ) : (
        <>
          <dl className={styles.counts}>
            <div>
              <dt>Sent</dt>
              <dd>{formatCount(delivery.sent)}</dd>
            </div>
            <div>
              <dt>Failed</dt>
              <dd className={delivery.failed > 0 ? styles.bad : undefined}>{formatCount(delivery.failed)}</dd>
            </div>
            <div>
              <dt>Pending</dt>
              <dd>{formatCount(delivery.pending)}</dd>
            </div>
            <div>
              <dt>Can be resent</dt>
              <dd>{formatCount(delivery.retryable)}</dd>
            </div>
          </dl>
          <p className={styles.hint}>
            {targetType ? `Target: ${targetType}. ` : ""}Failed deliveries, and ones that stayed pending for more than
            five minutes, can be resent, up to 100 at a time. The button resends every such delivery, not only
            the ones in the selected window.
          </p>
          <button
            type="button"
            className={styles.retry}
            disabled={retrying || delivery.retryable === 0}
            onClick={onRetry}
          >
            {retrying ? "Resending…" : "Resend failed deliveries"}
          </button>
        </>
      )}
    </section>
  );
}
