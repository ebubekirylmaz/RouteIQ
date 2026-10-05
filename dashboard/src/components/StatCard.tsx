import { useId, type ReactNode } from "react";

import styles from "./StatCard.module.css";

type Props = {
  title: string;
  value: string;
  /** One line under the value: what it is made of or how to read it. */
  hint?: ReactNode;
  /** Longer explanation, folded away so the card stays small. */
  details?: string;
  tone?: "normal" | "warning";
};

/** One number with its name. The card is labelled by its title, so screen readers can jump to it. */
export function StatCard({ title, value, hint, details, tone = "normal" }: Props) {
  const titleId = useId();
  return (
    <article
      className={tone === "warning" ? `${styles.card} ${styles.warning}` : styles.card}
      aria-labelledby={titleId}
    >
      <h2 id={titleId} className={styles.title}>
        {title}
      </h2>
      <p className={styles.value}>{value}</p>
      {hint && <p className={styles.hint}>{hint}</p>}
      {details && (
        <details className={styles.details}>
          <summary>What does this mean?</summary>
          <p>{details}</p>
        </details>
      )}
    </article>
  );
}
