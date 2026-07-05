import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";

const COLORS = ["#4fc3f7", "#7ee787", "#f59e0b", "#ef4444", "#a78bfa", "#f472b6", "#34d399"];
const axis = { stroke: "#64748b", fontSize: 11 };
const tooltipStyle = {
  contentStyle: { background: "#16202e", border: "1px solid #24455f", borderRadius: 8 },
  labelStyle: { color: "#e6eef5" },
};

// Renders a chart from CityPulse's {type, x, y} spec + rows. Falls back to null.
export default function AutoChart({ chart, rows }) {
  if (!chart || chart.type === "none" || !rows?.length) return null;
  const { type, x, y } = chart;
  if (!x || !y) return null;
  const data = rows.slice(0, 40).map((r) => ({ ...r, [y]: Number(r[y]) }));

  return (
    <div className="h-56 w-full mt-2">
      <ResponsiveContainer>
        {type === "line" ? (
          <LineChart data={data} margin={{ top: 6, right: 12, bottom: 4, left: -12 }}>
            <CartesianGrid stroke="#1d2a3a" vertical={false} />
            <XAxis dataKey={x} {...axis} />
            <YAxis {...axis} />
            <Tooltip {...tooltipStyle} />
            <Line type="monotone" dataKey={y} stroke="#4fc3f7" strokeWidth={2} dot={false} />
          </LineChart>
        ) : type === "pie" ? (
          <PieChart>
            <Pie data={data} dataKey={y} nameKey={x} outerRadius={90} label>
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip {...tooltipStyle} />
          </PieChart>
        ) : (
          <BarChart data={data} margin={{ top: 6, right: 12, bottom: 4, left: -12 }}>
            <CartesianGrid stroke="#1d2a3a" vertical={false} />
            <XAxis dataKey={x} {...axis} interval={0} angle={-25} textAnchor="end" height={54} />
            <YAxis {...axis} />
            <Tooltip {...tooltipStyle} />
            <Bar dataKey={y} fill="#4fc3f7" radius={[3, 3, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
