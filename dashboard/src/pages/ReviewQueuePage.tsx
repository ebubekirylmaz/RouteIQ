// D1. Uses: GET /review (limit, offset, X-Total-Count), GET /config (labels and descriptions),
// POST /review/{id}. A 409 means someone else resolved the request: drop the row and refetch.
export function ReviewQueuePage() {
  return (
    <section>
      <h1>Review queue</h1>
      <p>Requests the cascade was unsure about, oldest first. To do (D1).</p>
    </section>
  );
}
