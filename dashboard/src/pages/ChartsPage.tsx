// D3. Uses: GET /stats/timeseries?bucket=hour|day&since=&until= (Recharts).
// Empty buckets already arrive as zeros, so the x axis is continuous. Times are UTC ISO strings.
export function ChartsPage() {
  return (
    <section>
      <h1>Charts</h1>
      <p>Requests, cost and latency over time. To do (D3).</p>
    </section>
  );
}
