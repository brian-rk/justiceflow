import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Alert, Card, DelayBadge, Loading, PageHeader, Pager, RiskBadge, inputCls, pct, td, th, useFetch } from "../components/ui";
import type { CaseRow, Reference } from "../types";

const LIMIT = 50;

export default function Cases() {
  const [params, setParams] = useSearchParams();
  const get = (k: string, d = "") => params.get(k) ?? d;
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    if (k !== "offset") next.delete("offset");
    setParams(next, { replace: true });
  };
  const offset = Number(get("offset", "0"));
  const query = {
    status: get("status", "Pending"), risk: get("risk"), controllable: get("controllable"),
    case_type: get("case_type"), court_level: get("court_level"), court_station: get("court_station"),
    q: get("q"), sort: get("sort", "risk"), order: get("order", "desc"), limit: LIMIT, offset,
  };
  const ref = useFetch(() => api.get<Reference>("/reference"));
  const { data, error, loading } = useFetch(() => api.get<{ total: number; items: CaseRow[] }>("/cases", query), [params.toString()]);

  const sortBy = (key: string) => {
    const next = new URLSearchParams(params);
    next.set("order", get("sort", "risk") === key && get("order", "desc") === "desc" ? "asc" : "desc");
    next.set("sort", key);
    next.delete("offset");
    setParams(next, { replace: true });
  };
  const arrow = (key: string) => (get("sort", "risk") === key ? (get("order", "desc") === "desc" ? " ↓" : " ↑") : "");

  const select = (k: string, label: string, options: [string, string][]) => (
    <select aria-label={label} className={inputCls} value={get(k)} onChange={(e) => set(k, e.target.value)}>
      <option value="">{label}</option>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );

  return (
    <>
      <PageHeader title="Case list" subtitle="Filter and sort pending cases by risk, delay status, type and court." />
      <Card>
        <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-7">
          <input aria-label="Search case number" className={inputCls} placeholder="Case no." defaultValue={get("q")}
            onKeyDown={(e) => e.key === "Enter" && set("q", (e.target as HTMLInputElement).value)} />
          {select("risk", "Any risk", [["High", "High"], ["Medium", "Medium"], ["Low", "Low"]])}
          {select("controllable", "Any delay status", [["true", "Court-controllable"], ["false", "Externally blocked"]])}
          {select("case_type", "Any case type", (ref.data?.case_types ?? []).map((x) => [x, x]))}
          {select("court_level", "Any court level", (ref.data?.court_levels ?? []).map((x) => [x, x]))}
          {select("court_station", "Any station", (ref.data?.stations ?? []).map((x) => [x, x]))}
          {select("status", "Pending", [["Disposed", "Disposed"], ["all", "All statuses"]])}
        </div>
        {error && <Alert tone="error">{error}</Alert>}
        {!data ? <Loading /> : (
          <>
            <div className={"overflow-x-auto transition-opacity duration-200 " + (loading ? "opacity-60" : "")}>
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr>
                    <th className={th}><button onClick={() => sortBy("id")}>Case{arrow("id")}</button></th>
                    <th className={th}>Type / court</th>
                    <th className={th}>Station</th>
                    <th className={th}><button onClick={() => sortBy("age")}>Age{arrow("age")}</button></th>
                    <th className={th}><button onClick={() => sortBy("risk")}>Risk{arrow("risk")}</button></th>
                    <th className={th}>Delay status</th>
                    <th className={th}>Target used</th>
                  </tr>
                </thead>
                <tbody key={params.toString()} className="stagger-rows row-accent divide-y divide-slate-100">
                  {data.items.map((c) => (
                    <tr key={c.id} className="transition-colors duration-150 hover:bg-brand-50/50">
                      <td className={td}><Link to={`/cases/${c.id}`} className="font-medium text-brand-600 hover:underline">{c.id}</Link></td>
                      <td className={td}>{c.case_type}<div className="text-xs text-slate-500">{c.court_level}</div></td>
                      <td className={td}>{c.court_station}</td>
                      <td className={td + " tabular-nums"}>{Math.round(c.age_days / 30.44)} mo</td>
                      <td className={td}>
                        <RiskBadge category={c.risk?.category} overridden={c.risk?.review_status === "overridden"} />
                        {c.risk && <div className="mt-0.5 text-xs tabular-nums text-slate-500">{pct(c.risk.probability)}</div>}
                      </td>
                      <td className={td + " max-w-56"}>{c.risk && <DelayBadge status={c.risk.delay_status} />}</td>
                      <td className={td + " tabular-nums"}>{c.risk ? pct(Math.min(c.risk.target_used, 9.99)) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.items.length === 0 && <p className="py-8 text-center text-sm text-slate-500">No cases match these filters.</p>}
            <Pager total={data.total} limit={LIMIT} offset={offset} onChange={(o) => set("offset", String(o))} />
          </>
        )}
      </Card>
    </>
  );
}
