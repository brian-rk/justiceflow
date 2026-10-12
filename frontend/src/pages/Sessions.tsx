import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, DelayBadge, Empty, Field, Loading, PageHeader, RemandBadge, RiskBadge, cx, fmtDate, fmtDays, inputCls, td, th, useFetch } from "../components/ui";
import { useToast } from "../components/motion";
import type { SessionPlan } from "../types";
import { t, tn } from "../i18n";

interface Options {
  stations: { court_station: string; waiting: number; judges: { id: string; name: string }[] }[];
  cases_per_week: number;
  next_monday: string;
}

/** High Court criminal sessions: murder and other committal trials are heard in sessions,
 *  a judge sitting for some weeks at a registry, so they are planned here, not weekly. */
export default function Sessions() {
  const { user } = useAuth();
  const isRegistrar = user?.role === "registrar";
  const plans = useFetch(() => api.get<SessionPlan[]>("/sessions"));
  const opts = useFetch(() => api.get<Options>("/sessions/options"));
  const toast = useToast();
  const [form, setForm] = useState({ court_station: "", magistrate_id: "", start_date: "", weeks: 4 });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const o = opts.data;
    if (o && !form.court_station && o.stations[0]) {
      setForm((f) => ({ ...f, court_station: o.stations[0].court_station, magistrate_id: o.stations[0].judges[0]?.id ?? "",
        start_date: o.next_monday }));
    }
  }, [opts.data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (plans.error) return <Alert tone="error">{plans.error}</Alert>;
  if (!plans.data || !opts.data) return <Loading />;
  const station = opts.data.stations.find((s) => s.court_station === form.court_station);

  const propose = async () => {
    setBusy(true);
    try {
      const p = await api.post<SessionPlan>("/sessions", form);
      toast.success(t("Session proposed at {s}: {n}.", { s: p.court_station, n: tn(p.cases.length, "case", "cases") }));
      await Promise.all([plans.reload(), opts.reload()]);
    } catch (e) { toast.error((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title={t("Criminal sessions")}
        subtitle={t("Murder and other committal trials in the High Court are heard in criminal sessions, so they are planned here rather than on the weekly cause list. Cases are ranked by time in remand first.")} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title={t("Plan a session")} className="self-start">
          {opts.data.stations.length === 0 ? <Empty>{t("No High Court judges on the roster.")}</Empty> : (
            <div className="space-y-4">
              <Field label={t("High Court station")}>
                <select className={inputCls} value={form.court_station} onChange={(e) => {
                  const s = opts.data!.stations.find((x) => x.court_station === e.target.value);
                  setForm({ ...form, court_station: e.target.value, magistrate_id: s?.judges[0]?.id ?? "" });
                }}>
                  {opts.data.stations.map((s) => <option key={s.court_station} value={s.court_station}>{s.court_station} ({t("{n} waiting", { n: s.waiting })})</option>)}
                </select>
              </Field>
              <Field label={t("Judge")}>
                <select className={inputCls} value={form.magistrate_id} onChange={(e) => setForm({ ...form, magistrate_id: e.target.value })}>
                  {(station?.judges ?? []).map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}
                </select>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("Starts (Monday)")}>
                  <input type="date" className={inputCls} value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
                </Field>
                <Field label={t("Weeks")} hint={t("{n} trials a week", { n: opts.data.cases_per_week })}>
                  <input type="number" min={1} max={12} className={inputCls} value={form.weeks} onChange={(e) => setForm({ ...form, weeks: Number(e.target.value) })} />
                </Field>
              </div>
              {isRegistrar
                ? <Button variant="primary" className="w-full" onClick={propose} disabled={busy || !station?.waiting}>{busy ? t("Planning…") : t("Propose session")}</Button>
                : <p className="text-xs text-slate-500">{t("Only the registrar can plan sessions.")}</p>}
            </div>
          )}
        </Card>
        <div className="space-y-6 lg:col-span-2">
          {plans.data.length === 0 ? <Empty>{t("No sessions planned yet.")}</Empty> : plans.data.map((p) => (
            <PlanCard key={p.id} plan={p} canEdit={isRegistrar} onChanged={() => { plans.reload(); opts.reload(); }} />
          ))}
        </div>
      </div>
    </>
  );
}

function PlanCard({ plan, canEdit, onChanged }: { plan: SessionPlan; canEdit: boolean; onChanged: () => void }) {
  const toast = useToast();
  const editable = canEdit && plan.status === "PROPOSED";
  const remove = async (caseId: string) => {
    try { await api.del(`/sessions/${plan.id}/cases/${caseId}`); toast.success(t("{id} removed.", { id: caseId })); onChanged(); }
    catch (e) { toast.error((e as Error).message); }
  };
  const approve = async () => {
    try { await api.post(`/sessions/${plan.id}/approve`); toast.success(t("Session approved. Each case now has its trial date.")); onChanged(); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <Card title={<>{plan.court_station}, {t("from {date}", { date: fmtDate(plan.start_date) })} <span className="font-normal text-muted">({tn(plan.weeks, "week", "weeks")})</span></>}
      actions={<div className="flex items-center gap-2">
        <span className={cx("rounded px-2 py-0.5 text-xs font-medium", plan.status === "APPROVED" ? "bg-ok/10 text-[#2f8a6f]" : "bg-amber-50 text-amber-800")}>{t(plan.status === "APPROVED" ? "approved" : "awaiting approval")}</span>
        {editable && <Button variant="primary" onClick={approve} disabled={!plan.cases.length}>{t("Approve session")}</Button>}
      </div>}>
      <p className="mb-3 text-sm text-muted">{plan.magistrate_name}. {tn(plan.cases.length, "case", "cases")}.{plan.approved_by && ` ${t("Approved by {who}", { who: plan.approved_by })}.`}</p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead><tr><th className={th}>#</th><th className={th}>{t("Case")}</th><th className={th}>{t("Trial date")}</th><th className={th}>{t("Pending")}</th><th className={th}>{t("Risk")}</th><th className={th}>{t("Delay status")}</th>{editable && <th className={th}></th>}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {plan.cases.map((c) => (
              <tr key={c.case_id}>
                <td className={td + " tabular-nums text-slate-500"}>{c.position}</td>
                <td className={td}><Link to={`/cases/${c.case_id}`} className="font-medium text-brand-600 hover:underline">{c.case_id}</Link>
                  {c.in_custody && <div className="mt-1"><RemandBadge days={c.days_pending} /></div>}</td>
                <td className={td + " whitespace-nowrap"}>{fmtDate(c.planned_date)}</td>
                <td className={td + " whitespace-nowrap tabular-nums"}>{c.days_pending != null ? fmtDays(c.days_pending) : "—"}</td>
                <td className={td}><RiskBadge category={c.risk_category} /></td>
                <td className={td + " max-w-48"}>{c.delay_status && <DelayBadge status={c.delay_status} />}</td>
                {editable && <td className={td}><Button variant="ghost" className="px-2 py-1 text-xs hover:text-danger" onClick={() => remove(c.case_id)}>{t("Remove")}</Button></td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
