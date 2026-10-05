// D2. Uses: GET /stats?since=, POST /deliveries/retry.
// `reviewer_agreement` is not accuracy: show the description from the OpenAPI schema as a tooltip
// and say "no reviews yet" while `rate` is null.
export function OverviewPage() {
  return (
    <section>
      <h1>Overview</h1>
      <p>Totals for a time window. To do (D2).</p>
    </section>
  );
}
