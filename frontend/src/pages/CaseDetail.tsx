import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, DelayBadge, EffectIcon, Field, Loading, Modal, PageHeader, RemandBadge, RiskBadge, RiskRing, effectWords, fmtDate, fmtDays, inputCls, parseFactors, pct, td, th, useFetch } from "../components/ui";
import type { CaseDetail as Detail, RiskCategory } from "../types";
import { useToast } from "../components/motion";
import { t, tBodies, tFactor } from "../i18n";

/** Diverging bar from the centre line that grows in after mount. */
function EffectBar({ effect, delay }: { effect: number; delay: number }) {
  const [on, setOn] = useState(false);
  useEffect(() => { const id = setTimeout(() => setOn(true), 120 + delay); return () => clearTimeout(id); }, [delay]);
  const w = Math.min(Math.abs(effect), 1) * 50;
  return (
    <div className="relative h-2 flex-1 rounded bg-slate-100">
      <div className={`absolute top-0 h-2 rounded transition-[width] duration-700 ease-[var(--ease-out-quart)] ${effect > 0 ? "left-1/2 bg-danger/70" : "right-1/2 bg-ok/80"}`}
        style={{ width: on ? `${w}%` : "0%" }} />
      <div className="absolute left-1/2 top-[-2px] h-3 w-px bg-slate-300" />
    </div>
  );
}

const OUTCOME: Record<string, string> = { adjourned: "adjourned", proceeded: "proceeded", disposed: "disposed" };
const REASON: Record<string, string> = {
  advocate: "Advocate-requested postponement", prosecution: "State attorney / prosecution delay",
  forensic: "Pending forensic / expert report", witness: "Witness did not attend",
  record: "Awaiting record of proceedings", court: "Court-side",
};

export default function CaseDetail() {
  const { caseId = "" } = useParams();
  const { user } = useAuth();
  const { data, error, reload } = useFetch(() => api.get<Detail>(`/cases/${caseId}`), [caseId]);
  const [override, setOverride] = useState(false);
  const toast = useToast();

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;
  const r = data.risk;
  const isRegistrar = user?.role === "registrar";

  const approve = async () => {
    try {
      await api.post(`/cases/${caseId}/risk-review`, { action: "approve" });
      toast.success(t("Risk score for {id} approved.", { id: caseId }));
      reload();
    } catch (e) { toast.error((e as Error).message); }
  };

  return (
    <>
      <PageHeader
        title={data.id}
        subtitle={<>{t(data.case_type)}{data.offence !== "Not criminal" && `, ${t(data.offence)}`}, {t(data.division)}, {data.court_station}. {t("Filed {date}", { date: fmtDate(data.filing_date) })}. <span className="font-medium">{t(data.status)}</span></>}
        actions={<Link to="/cases" className="text-sm font-medium text-brand-600 hover:underline">← {t("Case list")}</Link>}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title={t("Risk score")} className="lg:col-span-2"
          actions={r && isRegistrar && data.status === "Pending" && (
            <div className="flex gap-2">
              <Button onClick={approve} disabled={r.review_status === "approved"}>{t("Approve")}</Button>
              <Button onClick={() => setOverride(true)}>{t("Override…")}</Button>
            </div>
          )}>
          {!r ? <p className="text-sm text-slate-500">{t("This case has no current risk score.")}</p> : (
            <>
              {data.days_overdue ? (
                // Already past the target: there is nothing left to predict, so show by how much.
                <div className="flex flex-wrap items-center gap-5">
                  <div className="grid h-[104px] w-[104px] shrink-0 place-items-center rounded-full border-[9px] border-danger/80 text-center">
                    <span className="leading-tight"><span className="block text-2xl font-medium tabular-nums text-ink">{data.days_overdue}</span><span className="text-xs text-muted">{t("days over")}</span></span>
                  </div>
                  <div className="min-w-0">
                    <RiskBadge pulse category={r.category} overridden={r.review_status === "overridden"} />
                    <p className="mt-2 text-sm text-muted">{t("Past its {m}-month disposition target by {d}", { m: data.disposition_target_months, d: fmtDays(data.days_overdue) })}</p>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-5">
                  <RiskRing value={r.probability} category={r.category} />
                  <div className="min-w-0">
                    <RiskBadge pulse category={r.category} overridden={r.review_status === "overridden"} />
                    <p className="mt-2 text-sm text-muted">{t("chance of exceeding the {m}-month disposition target", { m: data.disposition_target_months })}</p>
                  </div>
                </div>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
                <DelayBadge status={r.delay_status} />
                {data.in_custody && <RemandBadge days={data.remand_days} />}
                <span>{t("{p} of target time used", { p: pct(Math.min(r.target_used, 9.99)) })}</span>
                <span>{t("Scored {date}", { date: fmtDate(r.scored_at) })}</span>
                <span>{t("Review")}: <span className="font-medium text-slate-700">{t(r.review_status)}</span></span>
              </div>
              {!r.court_controllable && (
                <p className="mt-3 text-sm text-slate-600"><span className="font-medium text-ink">{t("Who can unblock it")}:</span> {tBodies(data.responsible)}</p>
              )}
              {r.review_status === "overridden" && (
                <div className="mt-3"><Alert tone="warn">{t("Registrar set this to {a} (model said {b})", { a: t(r.reviewed_category ?? ""), b: t(r.model_category) })}: {r.review_reason}</Alert></div>
              )}
              <h3 className="mt-5 mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t("Driving factors")}</h3>
              {r.overdue ? <p className="text-sm">{t("The case is already past its disposition target, so its age outweighs every other factor.")}</p> : (
                <ul className="space-y-2.5">
                  {parseFactors(r.driving_factors).map((f, i) => (
                    <li key={f.label} className="flex items-center gap-3 text-sm animate-fade-up" style={{ animationDelay: `${i * 90}ms` }}>
                      <span className="w-72 max-w-[60%] truncate">{tFactor(f.label)}</span>
                      {f.effect !== null && (
                        <>
                          <EffectBar effect={f.effect} delay={i * 90} />
                          <span className="flex w-40 items-center gap-1 text-xs text-slate-600" title={t("Effect on risk: {v}", { v: `${f.effect > 0 ? "+" : ""}${f.effect.toFixed(2)}` })}>
                            <EffectIcon effect={f.effect} /> {effectWords(f.effect).words}
                          </span>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-xs text-slate-500">{t("Each bar shows how much a factor moves the risk compared with a neutral value (hover for the exact figure). Region and station are never used.")}</p>
            </>
          )}
        </Card>

        <Card title={t("Case details")}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <dt className="text-slate-500">{t("Next date")}</dt>
            <dd className="font-medium">{data.next_date ? fmtDate(data.next_date) : data.sessions_case ? t("Awaiting session") : t("Not fixed")}</dd>
            <dt className="text-slate-500">{data.case_type === "Criminal" ? t("Accused") : t("Parties")}</dt>
            <dd>{data.case_type === "Criminal" ? Math.max(1, data.n_parties - 1) : data.n_parties}</dd>
            <dt className="text-slate-500">{t("Represented")}</dt><dd>{t(data.represented ? "Yes" : "No")}</dd>
            {data.in_custody && <><dt className="text-slate-500">{t("In remand")}</dt><dd>{fmtDays(data.remand_days ?? 0)}</dd></>}
            <dt className="text-slate-500">{t("Region")}</dt><dd>{data.region} <span className="text-xs text-slate-500">({t("audit only")})</span></dd>
            <dt className="text-slate-500">{t("Magistrate")}</dt><dd>{data.assigned_magistrate_id ?? "—"}</dd>
            <dt className="text-slate-500">{t("Age")}</dt><dd>{t("{n} months", { n: Math.round(data.age_days / 30.44) })}</dd>
            <dt className="text-slate-500">{t("Source")}</dt><dd>{data.source}</dd>
          </dl>
          <h3 className="mt-5 mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t("External-delay flags")}</h3>
          <ul className="space-y-1 text-sm">
            {Object.entries(data.flag_labels).map(([k, label]) => (
              <li key={k} className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full transition-colors duration-300 ${data.active_flags[k] ? "bg-info shadow-[0_0_0_3px_rgba(6,194,222,0.18)]" : "bg-slate-200"}`} />
                <span className={data.active_flags[k] ? "font-medium" : "text-slate-500"}>{t(label)}</span>
              </li>
            ))}
          </ul>
          {data.latest_listing && (
            <p className="mt-5 text-sm text-slate-600">
              {t("Listed {day} {date} before {mag} (#{pos}, {state})", {
                day: t(data.latest_listing.day), date: fmtDate(data.latest_listing.date), mag: data.latest_listing.magistrate_id,
                pos: data.latest_listing.position, state: t(data.latest_listing.cycle_status === "APPROVED" ? "approved" : "proposed"),
              })}
            </p>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title={t("Hearing history ({n})", { n: data.hearings.length })} className="lg:col-span-2">
          <div className="max-h-96 overflow-auto">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-white"><tr><th className={th}>#</th><th className={th}>{t("Date")}</th><th className={th}>{t("Outcome")}</th><th className={th}>{t("Reason")}</th><th className={th}>{t("Next date")}</th><th className={th}>{t("Recorded by")}</th></tr></thead>
              <tbody className="stagger-rows row-accent divide-y divide-slate-100">
                {data.hearings.map((h) => (
                  <tr key={h.hearing_no}>
                    <td className={td + " tabular-nums"}>{h.hearing_no}</td>
                    <td className={td + " whitespace-nowrap"}>{fmtDate(h.hearing_date)}</td>
                    <td className={td}>
                      <span className={h.outcome === "adjourned" ? "text-amber-700" : h.outcome === "disposed" ? "font-medium text-brand-600" : ""}>{t(OUTCOME[h.outcome] ?? h.outcome)}</span>
                    </td>
                    <td className={td + " text-slate-600"}>
                      {h.adjournment_reason ? t(REASON[h.adjournment_reason] ?? h.adjournment_reason) : "—"}
                      {h.notes && <div className="text-xs text-slate-500">{h.notes}</div>}
                    </td>
                    <td className={td + " whitespace-nowrap text-slate-600"}>{fmtDate(h.next_date)}</td>
                    <td className={td + " text-slate-500"}>{h.recorded_by ?? t("import")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.hearings.length === 0 && <p className="py-6 text-center text-sm text-slate-500">{t("No hearings yet.")}</p>}
          </div>
        </Card>
        <Card title={t("Registrar decisions & escalations")}>
          {data.escalations.map((e) => (
            <div key={e.cycle_id} className="mb-3"><Alert tone={e.acknowledged ? "info" : "warn"}>{t("Escalated in {cycle}: High risk for consecutive weeks with no registrar action.", { cycle: e.cycle_id })}</Alert></div>
          ))}
          {data.decisions.length === 0 ? <p className="text-sm text-slate-500">{t("No decisions recorded.")}</p> : (
            <ul className="stagger space-y-3 text-sm">
              {data.decisions.map((d, i) => (
                <li key={i}>
                  <span className="font-medium">{t(d.action.replace("_", " "))}</span>
                  {d.risk_category && <> → {t(d.risk_category)}</>}
                  {d.day && <> → {t(d.day)}</>}
                  <div className="text-xs text-slate-500">{d.by}, {fmtDate(d.timestamp)}{d.cycle_id && `, ${d.cycle_id}`}</div>
                  {d.reason && d.reason !== "bulk approval" && <div className="text-xs text-slate-600">“{d.reason}”</div>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {r && <OverrideModal open={override} onClose={() => setOverride(false)} caseId={caseId} current={r.category}
        onDone={() => { setOverride(false); toast.success(t("Override recorded in the audit log.")); reload(); }} />}
    </>
  );
}

export function OverrideModal({ open, onClose, caseId, current, onDone }: { open: boolean; onClose: () => void; caseId: string; current: RiskCategory; onDone: () => void }) {
  const [category, setCategory] = useState<RiskCategory>(current === "High" ? "Medium" : "High");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    try {
      await api.post(`/cases/${caseId}/risk-review`, { action: "override", category, reason });
      setReason("");
      onDone();
    } catch (e) { setError((e as Error).message); }
  };
  return (
    <Modal title={t("Override risk for {id}", { id: caseId })} open={open} onClose={onClose}>
      <div className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <Field label={t("New category")}>
          <select className={inputCls} value={category} onChange={(e) => setCategory(e.target.value as RiskCategory)}>
            {(["High", "Medium", "Low"] as const).map((c) => <option key={c} value={c}>{t(c)}</option>)}
          </select>
        </Field>
        <Field label={t("Reason (recorded in the audit log)")}>
          <textarea className={inputCls} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t("Cancel")}</Button>
          <Button variant="primary" onClick={submit} disabled={!reason.trim()}>{t("Save override")}</Button>
        </div>
      </div>
    </Modal>
  );
}
