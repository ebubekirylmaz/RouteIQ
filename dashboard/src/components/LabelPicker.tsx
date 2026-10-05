import type { ConfigView } from "../api/endpoints";
import styles from "./LabelPicker.module.css";

type Label = ConfigView["labels"][number];

type Props = {
  requestId: number;
  labels: Label[];
  /** The model's suggestion. It is highlighted, never chosen for the person. */
  suggested: string | null;
  disabled?: boolean;
  onChoose: (label: string) => void;
};

/**
 * One button per label, in the order of the config so the positions never move. The suggestion
 * is marked but not pre-selected: a decision is always a deliberate click, which keeps the
 * recorded decisions meaningful as feedback on the model.
 */
export function LabelPicker({ requestId, labels, suggested, disabled = false, onChoose }: Props) {
  return (
    <div role="group" aria-label={`Choose the label for request ${requestId}`} className={styles.group}>
      {labels.map((label) => {
        const isSuggested = label.name === suggested;
        return (
          <button
            key={label.name}
            type="button"
            className={isSuggested ? `${styles.button} ${styles.suggested}` : styles.button}
            title={label.description ?? undefined}
            disabled={disabled}
            onClick={() => onChoose(label.name)}
          >
            {label.name}
            {isSuggested && <span className={styles.badge}>suggested</span>}
          </button>
        );
      })}
    </div>
  );
}
