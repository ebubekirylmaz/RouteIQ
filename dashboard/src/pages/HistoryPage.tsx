// D4. Uses: GET /requests (filters, limit, offset, order, X-Total-Count).
// `delivery_error` is already masked by the API; `degraded` marks requests where a tier failed.
export function HistoryPage() {
  return (
    <section>
      <h1>History</h1>
      <p>Every request with filters, search and paging. To do (D4).</p>
    </section>
  );
}
