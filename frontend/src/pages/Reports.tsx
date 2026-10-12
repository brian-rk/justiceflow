import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Alert, Card, Loading, PageHeader, fmtMonth, pct, td, th, useFetch } from "../components/ui";
import { t } from "../i18n";

interface Report {
  benchmark_months: number;
  trend: { month: string; pending: number; over_benchmark: number; over_benchmark_share: number; filed: number; disposed: number; partial?: boolean }[];
  by_level: { court_level: string; pending: number; over_benchmark: number; over_target: number;
              avg_days_to_decision: number | null; published_avg_days_2025: number | null; published_backlog_share_2025: number }[];
  by_division: { division: string; pending: number; over_target: number }[];
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
  // Filings and disposals are monthly flows: a month still running would look like a collapse.
  const complete = data.trend.filter((x) => !x.partial);
  const lastFull = complete[complete.length - 1];

  return (
    <>
      <PageHeader title={t("Reports")} subtitle={t("Backlog trends against the NAO {b}-month benchmark, with this data set next to the Judiciary's published 2025 figures.", { b })} />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Tile label={t("Pending now")} value={last.pending.toLocaleString()} />
        <Tile label={t("Pending > {b} months", { b })} value={last.over_benchmark.toLocaleString()} />
        <Tile label={t("Share over {b} months", { b })} value={pct(last.over_benchmark_share, 1)}
          hint={t(last.over_benchmark_share > first.over_benchmark_share ? "Up from {p} in {m}" : "Down from {p} in {m}", { p: pct(first.over_benchmark_share, 1), m: fmtMonth(first.month) })} />
        <Tile label={t("Disposed in {m}", { m: fmtMonth(lastFull.month) })} value={lastFull.disposed} hint={t("{n} filed that month", { n: lastFull.filed })} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={t("Share of pending cases older than {b} months", { b })}>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data.trend} margin={{ left: -10, right: 10 }}>
              <CartesianGrid stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="month" tick={AXIS} interval={3} tickFormatter={fmtMonth} />
              <YAxis tick={AXIS} tickFormatter={(v) => pct(v)} domain={[0, "auto"]} />
              <Tooltip formatter={(v) => pct(Number(v), 1)} labelFormatter={(m) => fmtMonth(String(m))} />
              <Line type="monotone" dataKey="over_benchmark_share" name={t("> {b} months", { b })} stroke="#e74c5e" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card title={t("Filed vs disposed per month")}>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={complete} margin={{ left: -10, right: 10 }}>
              <CartesianGrid stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="month" tick={AXIS} interval={3} tickFormatter={fmtMonth} />
              <YAxis tick={AXIS} />
              <Tooltip labelFormatter={(m) => fmtMonth(String(m))} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="filed" name={t("Filed")} fill="#7a8799" />
              <Bar dataKey="disposed" name={t("Disposed")} fill="#4090cb" />
            </BarChart>
          </ResponsiveContainer>
          {last.partial && <p className="mt-2 text-xs text-slate-500">{t("{m} is shown once the month is complete.", { m: fmtMonth(last.month) })}</p>}
        </Card>
      </div>

      <Card title={t("By court level, next to the Judiciary's 2025 figures")} className="mt-6">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>
                <th className={th}>{t("Court")}</th><th className={th + " text-right"}>{t("Pending")}</th>
                <th className={th + " text-right"}>{t("Past own target")}</th><th className={th + " text-right"}>{t("Backlog share")}</th>
                <th className={th + " text-right"}>{t("Published 2025")}</th>
                <th className={th + " text-right"}>{t("Avg days to decision")}</th><th className={th + " text-right"}>{t("Published 2025")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.by_level.map((r) => (
                <tr key={r.court_level}>
                  <td className={td}>{t(r.court_level)}</td>
                  <td className={td + " text-right tabular-nums"}>{r.pending}</td>
                  <td className={td + " text-right tabular-nums"}>{r.over_target}</td>
                  <td className={td + " text-right tabular-nums"}>{pct(r.over_target / Math.max(r.pending, 1), 1)}</td>
                  <td className={td + " text-right tabular-nums text-slate-500"}>{pct(r.published_backlog_share_2025, 1)}</td>
                  <td className={td + " text-right tabular-nums"}>{r.avg_days_to_decision ?? "—"}</td>
                  <td className={td + " text-right tabular-nums text-slate-500"}>{r.published_avg_days_2025 ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500">{t("Source: Judiciary of Tanzania, Comprehensive Performance Report of the Judicial Functions 2025 (Tables 3.3 and 3.4, Chart 3.5). The demo data is synthetic, fitted to the published average days to decision; its backlog shares are a check, not a target.")}</p>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title={t("High Court by division")}>
          <table className="min-w-full text-sm">
            <thead><tr><th className={th}>{t("Division")}</th><th className={th + " text-right"}>{t("Pending")}</th><th className={th + " text-right"}>{t("Past own target")}</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {data.by_division.map((r) => (
                <tr key={r.division}>
                  <td className={td}>{t(r.division)}</td>
                  <td className={td + " text-right tabular-nums"}>{r.pending}</td>
                  <td className={td + " text-right tabular-nums"}>{r.over_target}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title={t("Stations with the most pending cases")}>
          <div className="max-h-72 overflow-auto">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-white"><tr><th className={th}>{t("Station")}</th><th className={th}>{t("Court")}</th><th className={th + " text-right"}>{t("Pending")}</th><th className={th + " text-right"}>{t("> {b} mo", { b })}</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.by_station.map((r) => (
                  <tr key={r.court_station + r.court_level}>
                    <td className={td}>{r.court_station}</td><td className={td}>{t(r.court_level)}</td>
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
