import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, DelayBadge, Field, Loading, Modal, PageHeader, RiskBadge, RiskRing, fmtDate, inputCls, pct, td, th, useFetch } from "../components/ui";
import type { CaseDetail as Detail, RiskCategory } from "../types";
import { useToast } from "../components/motion";

/** Diverging bar from the centre line that grows in after mount. */
function EffectBar({ effect, delay }: { effect: number; delay: number }) {
  const [on, setOn] = useState(false);
  useEffect(() => { const t = setTimeout(() => setOn(true), 120 + delay); return () => clearTimeout(t); }, [delay]);
  const w = Math.min(Math.abs(effect), 1) * 50;
  return (
    <div className="relative h-2 flex-1 rounded bg-slate-100">
      <div className={`absolute top-0 h-2 rounded transition-[width] duration-700 ease-[var(--ease-out-quart)] ${effect > 0 ? "left-1/2 bg-danger/70" : "right-1/2 bg-ok/80"}`}
        style={{ width: on ? `${w}%` : "0%" }} />
      <div className="absolute left-1/2 top-[-2px] h-3 w-px bg-slate-300" />
    </div>
  );
}

/** "84% of disposition target elapsed (+0.53); 6 hearings held (-0.25)" -> rows */
function parseFactors(s: string) {
  return s.split("; ").map((part) => {
    const m = part.match(/^(.*) \(([+-]\d+\.\d+)\)$/);
    return m ? { label: m[1], effect: parseFloat(m[2]) } : { label: part, effect: null };
  });
}

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
      toast.success(`Risk score for ${caseId} approved.`);
      reload();
    } catch (e) { toast.error((e as Error).message); }
  };

  return (
    <>
      <PageHeader
        title={data.id}
        subtitle={<>{data.case_type} · {data.court_level} · {data.court_station} · filed {fmtDate(data.filing_date)} · <span className="font-medium">{data.status}</span></>}
        actions={<Link to="/cases" className="text-sm font-medium text-brand-600 hover:underline">← Case list</Link>}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Risk score" className="lg:col-span-2"
          actions={r && isRegistrar && data.status === "Pending" && (
            <div className="flex gap-2">
              <Button onClick={approve} disabled={r.review_status === "approved"}>Approve</Button>
              <Button onClick={() => setOverride(true)}>Override…</Button>
            </div>
          )}>
          {!r ? <p className="text-sm text-slate-500">This case has no current risk score.</p> : (
            <>
              <div className="flex flex-wrap items-center gap-5">
                <RiskRing value={r.probability} category={r.category} />
                <div className="min-w-0">
                  <RiskBadge pulse category={r.category} overridden={r.review_status === "overridden"} />
                  <p className="mt-2 text-sm text-muted">chance of exceeding the <b className="text-ink">{data.disposition_target_months}-month</b> disposition target</p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                <DelayBadge status={r.delay_status} />
                <span>· {pct(Math.min(r.target_used, 9.99))} of target elapsed</span>
                <span>· scored {fmtDate(r.scored_at)}</span>
                <span>· review: <span className="font-medium text-slate-700">{r.review_status}</span></span>
              </div>
              {r.review_status === "overridden" && (
                <div className="mt-3"><Alert tone="warn">Registrar set this to <b>{r.reviewed_category}</b> (model said {r.model_category}): {r.review_reason}</Alert></div>
              )}
              <h3 className="mt-5 mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Driving factors</h3>
              {r.overdue ? <p className="text-sm">Already past its disposition target.</p> : (
                <ul className="space-y-2.5">
                  {parseFactors(r.driving_factors).map((f, i) => (
                    <li key={f.label} className="flex items-center gap-3 text-sm animate-fade-up" style={{ animationDelay: `${i * 90}ms` }}>
                      <span className="w-72 max-w-[60%] truncate">{f.label}</span>
                      {f.effect !== null && (
                        <>
                          <EffectBar effect={f.effect} delay={i * 90} />
                          <span className="w-14 text-right tabular-nums text-slate-600">{f.effect > 0 ? "+" : ""}{f.effect.toFixed(2)}</span>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-xs text-slate-500">Effect = how much each factor moves the probability compared with a neutral value. Region and station are never used.</p>
            </>
          )}
        </Card>

        <Card title="Case attributes">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <dt className="text-slate-500">Parties</dt><dd>{data.n_parties}</dd>
            <dt className="text-slate-500">Represented</dt><dd>{data.represented ? "Yes" : "No"}</dd>
            <dt className="text-slate-500">Region</dt><dd>{data.region} <span className="text-xs text-slate-400">(audit only)</span></dd>
            <dt className="text-slate-500">Magistrate</dt><dd>{data.assigned_magistrate_id ?? "—"}</dd>
            <dt className="text-slate-500">Age</dt><dd>{Math.round(data.age_days / 30.44)} months</dd>
            <dt className="text-slate-500">Source</dt><dd>{data.source}</dd>
          </dl>
          <h3 className="mt-5 mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">External-delay flags</h3>
          <ul className="space-y-1 text-sm">
            {Object.entries(data.flag_labels).map(([k, label]) => (
              <li key={k} className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full transition-colors duration-300 ${data.active_flags[k] ? "bg-info shadow-[0_0_0_3px_rgba(6,194,222,0.18)]" : "bg-slate-200"}`} />
                <span className={data.active_flags[k] ? "font-medium" : "text-slate-500"}>{label}</span>
              </li>
            ))}
          </ul>
          {data.latest_listing && (
            <p className="mt-5 text-sm text-slate-600">
              Listed {data.latest_listing.day} {fmtDate(data.latest_listing.date)} before {data.latest_listing.magistrate_id} (#{data.latest_listing.position},{" "}
              {data.latest_listing.cycle_status === "APPROVED" ? "approved" : "proposed"})
            </p>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title={`Hearing history (${data.hearings.length})`} className="lg:col-span-2">
          <div className="max-h-96 overflow-auto">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-white"><tr><th className={th}>#</th><th className={th}>Date</th><th className={th}>Outcome</th><th className={th}>Reason / flags</th><th className={th}>Recorded by</th></tr></thead>
              <tbody className="stagger-rows row-accent divide-y divide-slate-100">
                {data.hearings.map((h) => (
                  <tr key={h.hearing_no}>
                    <td className={td + " tabular-nums"}>{h.hearing_no}</td>
                    <td className={td}>{fmtDate(h.hearing_date)}</td>
                    <td className={td}>
                      <span className={h.outcome === "adjourned" ? "text-amber-700" : h.outcome === "disposed" ? "font-medium text-brand-600" : ""}>{h.outcome}</span>
                    </td>
                    <td className={td + " text-slate-600"}>
                      {h.adjournment_reason ?? "—"}
                      {h.notes && <div className="text-xs text-slate-500">{h.notes}</div>}
                    </td>
                    <td className={td + " text-slate-500"}>{h.recorded_by ?? "import"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.hearings.length === 0 && <p className="py-6 text-center text-sm text-slate-500">No hearings yet.</p>}
          </div>
        </Card>
        <Card title="Registrar decisions & escalations">
          {data.escalations.map((e) => (
            <div key={e.cycle_id} className="mb-3"><Alert tone={e.acknowledged ? "info" : "warn"}>{e.note}</Alert></div>
          ))}
          {data.decisions.length === 0 ? <p className="text-sm text-slate-500">No decisions recorded.</p> : (
            <ul className="stagger space-y-3 text-sm">
              {data.decisions.map((d, i) => (
                <li key={i}>
                  <span className="font-medium">{d.action.replace("_", " ")}</span>
                  {d.risk_category && <> → {d.risk_category}</>}
                  {d.day && <> → {d.day}</>}
                  <div className="text-xs text-slate-500">{d.by} · {fmtDate(d.timestamp)}{d.cycle_id && ` · ${d.cycle_id}`}</div>
                  {d.reason && d.reason !== "bulk approval" && <div className="text-xs text-slate-600">“{d.reason}”</div>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {r && <OverrideModal open={override} onClose={() => setOverride(false)} caseId={caseId} current={r.category}
        onDone={() => { setOverride(false); toast.success("Override recorded in the audit log."); reload(); }} />}
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
    <Modal title={`Override risk for ${caseId}`} open={open} onClose={onClose}>
      <div className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="New category">
          <select className={inputCls} value={category} onChange={(e) => setCategory(e.target.value as RiskCategory)}>
            {(["High", "Medium", "Low"] as const).map((c) => <option key={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Reason (recorded in the audit log)">
          <textarea className={inputCls} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={!reason.trim()}>Save override</Button>
        </div>
      </div>
    </Modal>
  );
}
