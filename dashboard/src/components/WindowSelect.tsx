import styles from "./WindowSelect.module.css";

export type WindowOption<K extends string> = { key: K; label: string };

type Props<K extends string> = {
  value: K;
  options: readonly WindowOption<K>[];
  onChange: (key: K) => void;
};

/** Which stretch of time the numbers cover. Radio buttons: one choice, arrow keys move it. */
export function WindowSelect<K extends string>({ value, options, onChange }: Props<K>) {
  return (
    <fieldset className={styles.group}>
      <legend className={styles.legend}>Time window</legend>
      {options.map((item) => (
        <label key={item.key} className={item.key === value ? `${styles.option} ${styles.selected}` : styles.option}>
          <input
            type="radio"
            name="time-window"
            value={item.key}
            checked={item.key === value}
            onChange={() => onChange(item.key)}
            className={styles.input}
          />
          {item.label}
        </label>
      ))}
    </fieldset>
  );
}
