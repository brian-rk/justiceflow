import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Alert, Card, DelayBadge, Loading, PageHeader, Pager, RemandBadge, RiskSummary, fmtDate, inputCls, pct, td, th, useFetch } from "../components/ui";
import type { CaseRow, Reference } from "../types";
import { t } from "../i18n";

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
      <PageHeader title={t("Case list")} subtitle={t("Filter and sort pending cases by risk, delay status, type and court.")} />
      <Card>
        <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-7">
          <input aria-label={t("Search case number")} className={inputCls} placeholder={t("Case no.")} defaultValue={get("q")}
            onKeyDown={(e) => e.key === "Enter" && set("q", (e.target as HTMLInputElement).value)} />
          {select("risk", t("Any risk"), [["High", t("High")], ["Medium", t("Medium")], ["Low", t("Low")]])}
          {select("controllable", t("Any delay status"), [["true", t("Court-controllable")], ["false", t("Externally blocked")]])}
          {select("case_type", t("Any case type"), (ref.data?.case_types ?? []).map((x) => [x, t(x)]))}
          {select("court_level", t("Any court level"), (ref.data?.court_levels ?? []).map((x) => [x, t(x)]))}
          {select("court_station", t("Any station"), (ref.data?.stations ?? []).map((x) => [x, x]))}
          {select("status", t("Pending"), [["Disposed", t("Disposed")], ["all", t("All statuses")]])}
        </div>
        {error && <Alert tone="error">{error}</Alert>}
        {!data ? <Loading /> : (
          <>
            <div className={"overflow-x-auto transition-opacity duration-200 " + (loading ? "opacity-60" : "")}>
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr>
                    <th className={th}><button onClick={() => sortBy("id")}>{t("Case")}{arrow("id")}</button></th>
                    <th className={th}>{t("Type / court")}</th>
                    <th className={th}>{t("Station")}</th>
                    <th className={th}><button onClick={() => sortBy("age")}>{t("Age")}{arrow("age")}</button></th>
                    <th className={th}><button onClick={() => sortBy("risk")}>{t("Risk")}{arrow("risk")}</button></th>
                    <th className={th}>{t("Delay status")}</th>
                    <th className={th}>{t("Next date")}</th>
                    <th className={th}>{t("Target used")}</th>
                  </tr>
                </thead>
                <tbody key={params.toString()} className="stagger-rows row-accent divide-y divide-slate-100">
                  {data.items.map((c) => (
                    <tr key={c.id} className="transition-colors duration-150 hover:bg-brand-50/50">
                      <td className={td}><Link to={`/cases/${c.id}`} className="font-medium text-brand-600 hover:underline">{c.id}</Link></td>
                      <td className={td}>{t(c.case_type)}{c.offence !== "Not criminal" && <span className="text-slate-500">, {t(c.offence)}</span>}
                        <div className="text-xs text-slate-500">{t(c.division)}</div></td>
                      <td className={td}>{c.court_station}</td>
                      <td className={td + " tabular-nums"}>{t("{n} mo", { n: Math.round(c.age_days / 30.44) })}</td>
                      <td className={td}>
                        <RiskSummary category={c.risk?.category} probability={c.risk?.probability} daysOverdue={c.days_overdue}
                          overridden={c.risk?.review_status === "overridden"} />
                      </td>
                      <td className={td + " max-w-56"}>
                        {c.risk && <DelayBadge status={c.risk.delay_status} />}
                        {c.in_custody && <div className="mt-1"><RemandBadge /></div>}
                      </td>
                      <td className={td + " whitespace-nowrap"}>{c.sessions_case && !c.next_date ? <span className="text-xs text-slate-500">{t("Awaiting session")}</span> : fmtDate(c.next_date)}</td>
                      <td className={td + " tabular-nums"}>{c.risk ? pct(Math.min(c.risk.target_used, 9.99)) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.items.length === 0 && <p className="py-8 text-center text-sm text-slate-500">{t("No cases match these filters.")}</p>}
            <Pager total={data.total} limit={LIMIT} offset={offset} onChange={(o) => set("offset", String(o))} />
          </>
        )}
      </Card>
    </>
  );
}
