import { useId, type ReactNode } from "react";

import styles from "./ChartCard.module.css";

type Props = {
  title: string;
  /** One line that says what the chart shows, for everyone, and for screen readers. */
  description: string;
  children: ReactNode;
};

/** A chart with a caption. The figure is named by its title, so it can be found as a landmark. */
export function ChartCard({ title, description, children }: Props) {
  const captionId = useId();
  return (
    <figure className={styles.card} aria-labelledby={captionId}>
      <figcaption id={captionId} className={styles.caption}>
        <strong>{title}</strong>
        <span>{description}</span>
      </figcaption>
      {children}
    </figure>
  );
}
