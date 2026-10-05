import { useCallback, useEffect, useState } from "react";

import { Notice, type NoticeKind } from "../components/Notice";
import { Pager } from "../components/Pager";
import { ReviewRow } from "../components/ReviewRow";
import { useConfig } from "../hooks/useConfig";
import type { ResolveOutcome } from "../hooks/useResolveReview";
import { DEFAULT_PAGE_SIZE, useReviewQueue } from "../hooks/useReviewQueue";
import { clampPage } from "../lib/paging";
import { describeResolveError } from "../lib/resolveErrors";
import styles from "./ReviewQueuePage.module.css";

type Message = { kind: NoticeKind; text: string };

/** The line shown after a decision. A request somebody else handled is news, not an error. */
function messageFor(outcome: ResolveOutcome): Message {
  if (outcome.ok) {
    return { kind: "success", text: `Request ${outcome.id} was labeled "${outcome.label}".` };
  }
  const problem = describeResolveError(outcome.error);
  return { kind: problem.removeRow ? "info" : "error", text: problem.message };
}

/** D1: requests the cascade was unsure about, oldest first, with one button per label. */
export function ReviewQueuePage() {
  const [page, setPage] = useState(0);
  const [message, setMessage] = useState<Message | null>(null);
  const queue = useReviewQueue(page, DEFAULT_PAGE_SIZE);
  const config = useConfig();

  // Keep the page inside the list: after the last row of the last page is resolved, go back one.
  const total = queue.data?.total ?? 0;
  const valid = clampPage(page, total, DEFAULT_PAGE_SIZE);
  useEffect(() => {
    if (queue.data && !queue.isPlaceholderData && valid !== page) setPage(valid);
  }, [queue.data, queue.isPlaceholderData, valid, page]);

  const handleOutcome = useCallback((outcome: ResolveOutcome) => setMessage(messageFor(outcome)), []);

  return (
    <section>
      <header className={styles.header}>
        <h1>Review queue</h1>
        {queue.data && <p className={styles.count}>{queue.data.total} waiting</p>}
      </header>
      <p className={styles.intro}>
        Requests the cascade was not sure about, oldest first. Choose the correct label for each one.
        The model's suggestion is marked, but you have to pick the label yourself.
      </p>

      <div role="status" aria-label="Notifications" className={styles.notices}>
        {message && <Notice kind={message.kind} message={message.text} onDismiss={() => setMessage(null)} />}
      </div>

      {queue.isPending || config.isPending ? (
        <p role="status" aria-label="Loading">
          Loading the review queue…
        </p>
      ) : queue.isError && !queue.data ? (
        <Problem text="The review queue could not be loaded." onRetry={() => void queue.refetch()} />
      ) : config.isError || !config.data ? (
        <Problem text="The labels could not be loaded." onRetry={() => void config.refetch()} />
      ) : queue.data && queue.data.total === 0 ? (
        <p className={styles.empty}>The review queue is empty.</p>
      ) : (
        queue.data && (
          <>
            {queue.isRefetchError && (
              <div className={styles.stale} role="alert">
                The list could not be refreshed. It shows the last version that was loaded.
              </div>
            )}
            <ul className={styles.list} aria-busy={queue.isPlaceholderData}>
              {queue.data.items.map((item) => (
                <ReviewRow key={item.id} item={item} labels={config.data.labels} onOutcome={handleOutcome} />
              ))}
            </ul>
            <Pager
              page={page}
              pageSize={DEFAULT_PAGE_SIZE}
              shown={queue.data.items.length}
              total={queue.data.total}
              disabled={queue.isPlaceholderData}
              onPageChange={setPage}
            />
          </>
        )
      )}
    </section>
  );
}

function Problem({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <div className={styles.problem} role="alert">
      <span>{text}</span>
      <button type="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}
