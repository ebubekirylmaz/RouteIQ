import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { AccuracyRow } from "../../lib/evaluation";
import { AXIS, GRID, TOOLTIP } from "../charts/theme";
import styles from "./AccuracyChart.module.css";

const ROW_HEIGHT = 52;

/**
 * The accuracy of every setup as a bar from zero, with its 95% interval as a line. The axis starts
 * at zero on purpose: cutting it would make a small gap look big. The setup that counts every
 * person's answer as right has the warm colour, so it cannot be mistaken for a measurement.
 */
export function AccuracyChart({ rows }: { rows: AccuracyRow[] }) {
  // On a narrow screen the labels would leave the bars no room, so the chart keeps a minimum
  // width and scrolls inside its own box.
  return (
    <div className={styles.scroll}>
      <div className={styles.inner}>
        <ResponsiveContainer width="100%" height={rows.length * ROW_HEIGHT + 40}>
          <BarChart layout="vertical" data={rows} margin={{ top: 8, right: 24, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={GRID} horizontal={false} />
            <XAxis type="number" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={AXIS} tickFormatter={(value) => `${value}%`} />
            <YAxis type="category" dataKey="name" width={190} tick={AXIS} />
            <Tooltip
              {...TOOLTIP}
              cursor={{ fill: "var(--hover)" }}
              formatter={(_value, _name, item) => [(item.payload as AccuracyRow).label, "Accuracy"]}
            />
            <Bar dataKey="accuracy" name="Accuracy" isAnimationActive={false} barSize={22}>
              {rows.map((row) => (
                <Cell key={row.name} fill={row.assumesReviewer ? "var(--chart-warm)" : "var(--accent)"} />
              ))}
              <ErrorBar dataKey="error" direction="x" stroke="var(--text)" width={8} strokeWidth={1.5} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
