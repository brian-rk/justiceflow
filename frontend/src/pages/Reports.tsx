import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Alert, Card, Loading, PageHeader, pct, td, th, useFetch } from "../components/ui";

interface Report {
  benchmark_months: number;
  trend: { month: string; pending: number; over_benchmark: number; over_benchmark_share: number; filed: number; disposed: number }[];
  by_level: { court_level: string; pending: number; over_benchmark: number; over_target: number }[];
  by_station: { court_station: string; court_level: string; pending: number; over_benchmark: number }[];
}

const AXIS = { fontSize: 12, fill: "#64748b" };

export default function Reports() {
  const { data, error } = useFetch(() => api.get<Report>("/reports/backlog"));
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;
  const b = data.benchmark_months;
  const last = data.trend[data.trend.length - 1];
  const first = data.trend[0];

  return (
    <>
      <PageHeader title="Reports" subtitle={`Backlog trends tracked against the NAO ${b}-month disposition benchmark.`} />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Tile label="Pending now" value={last.pending.toLocaleString()} />
        <Tile label={`Pending > ${b} months`} value={last.over_benchmark.toLocaleString()} />
        <Tile label={`Share over ${b} months`} value={pct(last.over_benchmark_share, 1)}
          hint={`${last.over_benchmark_share > first.over_benchmark_share ? "up" : "down"} from ${pct(first.over_benchmark_share, 1)} in ${first.month}`} />
        <Tile label="Disposed this month" value={last.disposed} hint={`${last.filed} filed`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={`Share of pending cases older than ${b} months`}>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data.trend} margin={{ left: -10, right: 10 }}>
              <CartesianGrid stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="month" tick={AXIS} interval={3} />
              <YAxis tick={AXIS} tickFormatter={(v) => pct(v)} domain={[0, "auto"]} />
              <Tooltip formatter={(v) => pct(Number(v), 1)} />
              <Line type="monotone" dataKey="over_benchmark_share" name={`> ${b} months`} stroke="#e74c5e" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Filed vs disposed per month">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.trend} margin={{ left: -10, right: 10 }}>
              <CartesianGrid stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="month" tick={AXIS} interval={3} />
              <YAxis tick={AXIS} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="filed" name="Filed" fill="#c9d4e0" />
              <Bar dataKey="disposed" name="Disposed" fill="#4090cb" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="By court level">
          <table className="min-w-full text-sm">
            <thead><tr><th className={th}>Level</th><th className={th + " text-right"}>Pending</th><th className={th + " text-right"}>&gt; {b} mo</th><th className={th + " text-right"}>Past own target</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {data.by_level.map((r) => (
                <tr key={r.court_level}>
                  <td className={td}>{r.court_level}</td>
                  <td className={td + " text-right tabular-nums"}>{r.pending}</td>
                  <td className={td + " text-right tabular-nums"}>{r.over_benchmark} <span className="text-slate-400">({pct(r.over_benchmark / Math.max(r.pending, 1))})</span></td>
                  <td className={td + " text-right tabular-nums"}>{r.over_target}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Stations with the most pending cases">
          <div className="max-h-72 overflow-auto">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-white"><tr><th className={th}>Station</th><th className={th}>Level</th><th className={th + " text-right"}>Pending</th><th className={th + " text-right"}>&gt; {b} mo</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.by_station.map((r) => (
                  <tr key={r.court_station + r.court_level}>
                    <td className={td}>{r.court_station}</td><td className={td}>{r.court_level}</td>
                    <td className={td + " text-right tabular-nums"}>{r.pending}</td><td className={td + " text-right tabular-nums"}>{r.over_benchmark}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}

function Tile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}
