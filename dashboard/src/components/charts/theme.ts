export const GRID = "var(--border)";
export const AXIS = { fill: "var(--muted)", fontSize: 12 };

// Recharts draws its tooltip white, whatever the page looks like. These colours follow the theme.
export const TOOLTIP = {
  contentStyle: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    color: "var(--text)",
  },
  labelStyle: { color: "var(--text)", fontWeight: 600 },
  itemStyle: { color: "var(--text)" },
} as const;
