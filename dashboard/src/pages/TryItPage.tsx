import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import type { RouteResult } from "../api/endpoints";
import { TryItResult } from "../components/TryItResult";
import { useConfig } from "../hooks/useConfig";
import { useRouteText } from "../hooks/useRouteText";
import { formatCount, truncate } from "../lib/format";
import { MAX_TEXT_LENGTH, canSubmit, describeRoute, describeRouteError, normalizeText } from "../lib/tryIt";
import styles from "./TryItPage.module.css";

const MAX_ATTEMPTS = 10;
const TEXT_PREVIEW = 60;

type Attempt = { id: number; text: string; result: RouteResult };

/**
 * D5: send a text through the cascade and see what happens, without curl. The text is stored
 * like any other request, so the screen says so. The list of attempts lives in this screen
 * only: it is gone when you leave, the history keeps the requests.
 */
export function TryItPage() {
  const [text, setText] = useState("");
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const box = useRef<HTMLTextAreaElement>(null);
  const config = useConfig().data;
  const examples = config?.examples ?? [];
  // The public demo accepts shorter texts than the API does.
  const maxLength = config?.max_text_length ?? MAX_TEXT_LENGTH;

  const route = useRouteText((sent, result) =>
    setAttempts((previous) => [{ id: result.request_id, text: sent, result }, ...previous].slice(0, MAX_ATTEMPTS)),
  );

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!canSubmit(text) || route.isPending) return;
    route.mutate({ text: normalizeText(text) });
  };

  // An example only fills the box. Sending it is a decision of the person: it costs money and is stored.
  const fillWith = (example: string) => {
    setText(example);
    box.current?.focus();
  };

  // Cmd or Ctrl + Enter sends. A plain Enter is a new line, as in any text box.
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      submit();
    }
  };

  const latest = attempts[0];

  return (
    <section>
      <h1>Try it</h1>
      <p className={styles.intro}>
        Send a text through the cascade, the way your own system would. It is stored like any other
        request: it appears in the history and the statistics, and it may call the paid model.
      </p>

      <form className={styles.form} onSubmit={submit}>
        <label htmlFor="try-text">Text</label>
        <textarea
          id="try-text"
          ref={box}
          rows={4}
          value={text}
          maxLength={maxLength}
          readOnly={route.isPending}
          placeholder="For example: my card got declined at the store"
          aria-describedby="try-count"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className={styles.row}>
          <span id="try-count" className={styles.count}>
            {formatCount(text.length)} / {formatCount(maxLength)}
          </span>
          <button type="submit" disabled={!canSubmit(text) || route.isPending}>
            {route.isPending ? "Routing…" : "Route it"}
          </button>
        </div>
        <p className={styles.hint}>Press Ctrl or Cmd + Enter to send.</p>
      </form>

      {examples.length > 0 && (
        <div className={styles.examples} role="group" aria-label="Example texts">
          <span className={styles.examplesTitle}>Or start from an example:</span>
          {examples.map((example) => (
            <button key={example} type="button" disabled={route.isPending} onClick={() => fillWith(example)}>
              {example}
            </button>
          ))}
        </div>
      )}

      {route.isError && (
        <div className={styles.problem} role="alert">
          {describeRouteError(route.error, maxLength)}
        </div>
      )}

      <div role="status" aria-label="Result">
        {latest && <TryItResult text={latest.text} result={latest.result} />}
      </div>

      {attempts.length > 1 && (
        <section aria-labelledby="try-attempts-title">
          <h2 id="try-attempts-title" className={styles.subtitle}>
            Tried on this screen
          </h2>
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Text</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Label</th>
                  <th scope="col">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {attempts.map((attempt) => {
                  const view = describeRoute(attempt.result);
                  return (
                    <tr key={attempt.id}>
                      <td>{truncate(attempt.text, TEXT_PREVIEW)}</td>
                      <td>{view.headline}</td>
                      <td>{view.label}</td>
                      <td>{view.confidence}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className={styles.hint}>The list is cleared when you leave this screen. The history keeps the requests.</p>
        </section>
      )}
    </section>
  );
}
