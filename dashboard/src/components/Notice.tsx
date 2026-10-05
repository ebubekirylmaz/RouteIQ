import styles from "./Notice.module.css";

export type NoticeKind = "success" | "info" | "error";

type Props = {
  kind: NoticeKind;
  message: string;
  onDismiss?: () => void;
};

/** A short message about what just happened. Put it inside a live region so it is announced. */
export function Notice({ kind, message, onDismiss }: Props) {
  return (
    <div className={`${styles.notice} ${styles[kind]}`} data-kind={kind}>
      <span>{message}</span>
      {onDismiss && (
        <button type="button" className={styles.dismiss} onClick={onDismiss}>
          Dismiss
        </button>
      )}
    </div>
  );
}
