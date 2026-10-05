import { useMemo, useState } from "react";

import { ChartCard } from "../components/charts/ChartCard";
import { ChartTable } from "../components/charts/ChartTable";
import { CostChart, LatencyChart, RequestsChart } from "../components/charts/Charts";
import { WindowSelect } from "../components/WindowSelect";
import { useTimeseries } from "../hooks/useTimeseries";
import { toChartPoints, hasRequests } from "../lib/chartData";
import { CHART_RANGES, bucketOf, type ChartRange } from "../lib/chartRanges";
import { formatCost, formatCount } from "../lib/format";
import styles from "./ChartsPage.module.css";

/** D3: requests, cost and latency over time. Lazy-loaded, because it brings the chart library. */
export function ChartsPage() {
  const [range, setRange] = useState<ChartRange>("24h");
  const series = useTimeseries(range);
  const bucket = bucketOf(range);
  const points = series.data?.points;

  // The data the API answered with decides the bucket, so a chart never mixes two sizes while
  // the next range is still loading.
  const shownBucket = series.data?.bucket ?? bucket;
  const data = useMemo(() => (points ? toChartPoints(points, shownBucket) : []), [points, shownBucket]);
  const requests = data.reduce((sum, point) => sum + point.requests, 0);
  const cost = data.at(-1)?.cumulativeCost ?? 0;

  return (
    <section>
      <header className={styles.header}>
        <div>
          <h1>Charts</h1>
          <p className={styles.sub}>
            One bar or point per {shownBucket}. Times are in UTC.
          </p>
        </div>
        <WindowSelect value={range} options={CHART_RANGES} onChange={setRange} />
      </header>

      {series.isPending ? (
        <p role="status" aria-label="Loading">
          Loading the charts…
        </p>
      ) : !series.data ? (
        <div className={styles.problem} role="alert">
          <span>The charts could not be loaded.</span>
          <button type="button" onClick={() => void series.refetch()}>
            Try again
          </button>
        </div>
      ) : (
        <>
          {series.isRefetchError && (
            <div className={styles.problem} role="alert">
              The charts could not be refreshed. They show the last version that was loaded.
            </div>
          )}

          {!hasRequests(series.data.points) ? (
            <p className={styles.empty}>No requests in this period.</p>
          ) : (
            <div className={styles.grid} aria-busy={series.isPlaceholderData}>
              <ChartCard
                title="Requests"
                description={`${formatCount(requests)} requests, accepted by the cascade or sent to a person.`}
              >
                <RequestsChart data={data} />
              </ChartCard>
              <ChartCard title="Cost" description={`${formatCost(cost)} in total, added up over the period.`}>
                <CostChart data={data} />
              </ChartCard>
              <ChartCard
                title="Latency"
                description="Average time per request. A gap means there were no requests in that period."
              >
                <LatencyChart data={data} />
              </ChartCard>
            </div>
          )}

          {hasRequests(series.data.points) && <ChartTable data={data} />}
        </>
      )}
    </section>
  );
}
