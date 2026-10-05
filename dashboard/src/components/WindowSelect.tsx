import { STATS_WINDOWS, type StatsWindow } from "../lib/windows";
import styles from "./WindowSelect.module.css";

type Props = {
  value: StatsWindow;
  onChange: (window: StatsWindow) => void;
};

/** Which stretch of time the numbers cover. Radio buttons: one choice, arrow keys move it. */
export function WindowSelect({ value, onChange }: Props) {
  return (
    <fieldset className={styles.group}>
      <legend className={styles.legend}>Time window</legend>
      {STATS_WINDOWS.map((item) => (
        <label key={item.key} className={item.key === value ? `${styles.option} ${styles.selected}` : styles.option}>
          <input
            type="radio"
            name="stats-window"
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
