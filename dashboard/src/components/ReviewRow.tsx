import type { ConfigView, ReviewItem } from "../api/endpoints";
import { useResolveReview, type ResolveOutcome } from "../hooks/useResolveReview";
import { formatConfidence, formatWaiting } from "../lib/format";
import { LabelPicker } from "./LabelPicker";
import styles from "./ReviewRow.module.css";

type Props = {
  item: ReviewItem;
  labels: ConfigView["labels"];
  onOutcome: (outcome: ResolveOutcome) => void;
};

/** One request waiting for a person. It locks its own buttons while its decision is saved. */
export function ReviewRow({ item, labels, onOutcome }: Props) {
  const resolve = useResolveReview(onOutcome);
  const textId = `review-text-${item.id}`;

  return (
    <li className={styles.row} aria-busy={resolve.isPending} aria-labelledby={textId}>
      <p id={textId} className={styles.text}>
        {item.text}
      </p>

      <dl className={styles.meta}>
        <div>
          <dt>Waiting</dt>
          <dd>{formatWaiting(item.created_at)}</dd>
        </div>
        <div>
          <dt>Model suggestion</dt>
          <dd>
            {item.suggested_label ? (
              <>
                {item.suggested_label} ({formatConfidence(item.confidence)})
              </>
            ) : (
              "No suggestion"
            )}
          </dd>
        </div>
        <div>
          <dt>Decided by</dt>
          <dd>{item.tier ?? "no tier"}</dd>
        </div>
      </dl>

      <LabelPicker
        requestId={item.id}
        labels={labels}
        suggested={item.suggested_label}
        disabled={resolve.isPending}
        onChoose={(label) => resolve.mutate({ id: item.id, label })}
      />
    </li>
  );
}
