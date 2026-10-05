import { describeRange, pageCount } from "../lib/paging";
import styles from "./Pager.module.css";

type Props = {
  page: number;
  pageSize: number;
  /** Number of rows on the current page. */
  shown: number;
  total: number;
  disabled?: boolean;
  onPageChange: (page: number) => void;
};

export function Pager({ page, pageSize, shown, total, disabled = false, onPageChange }: Props) {
  const last = pageCount(total, pageSize) - 1;
  return (
    <nav className={styles.pager} aria-label="Pages of the review queue">
      <button type="button" disabled={disabled || page <= 0} onClick={() => onPageChange(page - 1)}>
        Previous
      </button>
      <span>{describeRange(page, pageSize, shown, total)}</span>
      <button type="button" disabled={disabled || page >= last} onClick={() => onPageChange(page + 1)}>
        Next
      </button>
    </nav>
  );
}
