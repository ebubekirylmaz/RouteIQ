import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartPoint } from "../../lib/chartData";
import { formatCost, formatCount, formatLatency, formatLatencyTick } from "../../lib/format";
import { AXIS, GRID, TOOLTIP } from "./theme";

const HEIGHT = 260;
const FRAME = { width: "100%", height: HEIGHT } as const;

/** The tooltip names the full time, not the short axis label. */
const titleOf = (_label: unknown, payload: readonly { payload?: ChartPoint }[]) => payload[0]?.payload?.title ?? "";

/** Requests per bucket, stacked: the ones the cascade accepted and the ones sent to a person. */
export function RequestsChart({ data }: { data: ChartPoint[] }) {
  return (
    <ResponsiveContainer {...FRAME}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={AXIS} interval="preserveStartEnd" />
        <YAxis tick={AXIS} allowDecimals={false} width={44} />
        <Tooltip {...TOOLTIP} cursor={{ fill: "var(--hover)" }} labelFormatter={titleOf} formatter={(value) => formatCount(Number(value))} />
        <Legend />
        <Bar dataKey="accepted" name="Accepted by the cascade" stackId="requests" fill="var(--accent)" isAnimationActive={false} />
        <Bar dataKey="human_review" name="Sent to a person" stackId="requests" fill="var(--chart-warm)" isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** The cost added up over the range, so the line only ever rises. */
export function CostChart({ data }: { data: ChartPoint[] }) {
  return (
    <ResponsiveContainer {...FRAME}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={AXIS} interval="preserveStartEnd" />
        <YAxis tick={AXIS} tickFormatter={(value) => formatCost(Number(value))} width={72} />
        <Tooltip {...TOOLTIP} labelFormatter={titleOf} formatter={(value) => formatCost(Number(value))} />
        <Line
          type="monotone"
          dataKey="cumulativeCost"
          name="Cost so far"
          stroke="var(--accent)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** The average latency per bucket. A bucket without requests is a gap, not a drop to zero. */
export function LatencyChart({ data }: { data: ChartPoint[] }) {
  return (
    <ResponsiveContainer {...FRAME}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={AXIS} interval="preserveStartEnd" />
        <YAxis tick={AXIS} tickFormatter={(value) => formatLatencyTick(Number(value))} width={64} />
        <Tooltip {...TOOLTIP} labelFormatter={titleOf} formatter={(value) => formatLatency(Number(value))} />
        <Line
          type="monotone"
          dataKey="avgLatency"
          name="Average latency"
          stroke="var(--chart-warm)"
          strokeWidth={2}
          dot={{ r: 2 }}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
