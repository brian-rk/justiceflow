import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Alert, Button, Card, DelayBadge, Field, PageHeader, RiskBadge, fmtDate, inputCls, pct, useFetch } from "../components/ui";
import type { CaseDetail, Reference, Risk } from "../types";
import { FadeSwap, Tabs, useToast } from "../components/motion";

const today = () => new Date().toISOString().slice(0, 10);

export default function ClerkEntry() {
  const ref = useFetch(() => api.get<Reference>("/reference"));
  const [tab, setTab] = useState<"hearing" | "register">("hearing");
  return (
    <>
      <PageHeader title="Case data entry" subtitle="Record hearing outcomes and delay causes. Each entry re-scores the case for the registrar's review." />
      <Tabs value={tab} onChange={setTab} tabs={[["hearing", "Record a hearing"], ["register", "Register a new case"]] as const} />
      {ref.data && <FadeSwap k={tab}>{tab === "hearing" ? <HearingForm reference={ref.data} /> : <RegisterForm reference={ref.data} />}</FadeSwap>}
    </>
  );
}

function HearingForm({ reference }: { reference: Reference }) {
  const [caseNo, setCaseNo] = useState("");
  const [c, setCase] = useState<CaseDetail | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [form, setForm] = useState({ hearing_date: today(), outcome: "adjourned", adjournment_reason: "", flag_advocate: false, flag_prosecution: false, flag_forensic: false, notes: "" });
  const [result, setResult] = useState<{ tone: "success" | "error"; text: string; risk?: Risk | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const lookup = async (e?: FormEvent) => {
    e?.preventDefault();
    setLookupError(null);
    setResult(null);
    try {
      const d = await api.get<CaseDetail>(`/cases/${caseNo.trim()}`);
      setCase(d);
      setForm((f) => ({ ...f, ...d.active_flags }));
    } catch (err) {
      setCase(null);
      setLookupError((err as Error).message);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!c) return;
    setBusy(true);
    try {
      const res = await api.post<{ hearing_no: number; rescored_risk: Risk | null }>(`/cases/${c.id}/hearings`, {
        ...form, adjournment_reason: form.outcome === "adjourned" ? form.adjournment_reason : null,
      });
      setResult({ tone: "success", text: `Hearing #${res.hearing_no} recorded for ${c.id}.`, risk: res.rescored_risk });
      toast.success(`Hearing #${res.hearing_no} saved; ${c.id} re-scored.`);
      const d = await api.get<CaseDetail>(`/cases/${c.id}`);
      setCase(d);
    } catch (err) {
      setResult({ tone: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const setF = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="1 · Find the case" className="lg:col-span-1">
        <form onSubmit={lookup} className="flex gap-2">
          <input aria-label="Case number" className={inputCls} placeholder="e.g. SYN-00042" value={caseNo} onChange={(e) => setCaseNo(e.target.value)} />
          <Button variant="primary" disabled={!caseNo.trim()}>Find</Button>
        </form>
        <p className="mt-2 text-xs text-slate-500">Or browse the <Link to="/cases" className="text-brand-600 hover:underline">case list</Link>.</p>
        {lookupError && <div className="mt-3"><Alert tone="error">{lookupError}</Alert></div>}
        {c && (
          <div key={c.id} className="mt-4 space-y-1 rounded-md bg-brand-50/60 p-3 text-sm animate-scale-in">
            <div className="font-semibold">{c.id} <span className="font-normal text-slate-500">· {c.status}</span></div>
            <div className="text-slate-600">{c.case_type} · {c.court_level} · {c.court_station}</div>
            <div className="text-slate-600">Filed {fmtDate(c.filing_date)} · {c.hearings.length} hearings</div>
            {c.hearings[0] && <div className="text-slate-600">Last: {fmtDate(c.hearings[0].hearing_date)} ({c.hearings[0].outcome})</div>}
          </div>
        )}
      </Card>

      <Card title="2 · Record the hearing" className="lg:col-span-2">
        {!c ? <p className="text-sm text-slate-500">Find a case first.</p> : c.status !== "Pending" ? <Alert tone="info">This case is disposed.</Alert> : (
          <form onSubmit={submit} className="space-y-4">
            {result && <Alert tone={result.tone}>
              {result.text}
              {result.risk && <span className="ml-2 inline-flex items-center gap-2">Re-scored: <RiskBadge category={result.risk.category} /> {pct(result.risk.probability)} <DelayBadge status={result.risk.delay_status} /></span>}
            </Alert>}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Hearing date">
                <input type="date" className={inputCls} value={form.hearing_date} max={today()} onChange={(e) => setF("hearing_date", e.target.value)} required />
              </Field>
              <Field label="Outcome">
                <select className={inputCls} value={form.outcome} onChange={(e) => setF("outcome", e.target.value)}>
                  <option value="proceeded">Proceeded (hearing took place)</option>
                  <option value="adjourned">Adjourned</option>
                  <option value="disposed">Disposed (case concluded)</option>
                </select>
              </Field>
            </div>
            {form.outcome === "adjourned" && (
              <div className="animate-fade-up"><Field label="Adjournment reason">
                <select className={inputCls} value={form.adjournment_reason} onChange={(e) => setF("adjournment_reason", e.target.value)} required>
                  <option value="">Select…</option>
                  {Object.entries(reference.adjournment_reasons).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </Field></div>
            )}
            {form.outcome !== "disposed" && (
              <fieldset className="animate-fade-up">
                <legend className="mb-1 text-xs font-medium text-slate-600">External-delay flags still active after this hearing</legend>
                <div className="space-y-1">
                  {(["flag_advocate", "flag_prosecution", "flag_forensic"] as const).map((k) => (
                    <label key={k} className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={form[k]} onChange={(e) => setF(k, e.target.checked)} className="h-4 w-4 accent-brand-600" />
                      {reference.flag_labels[k]}
                    </label>
                  ))}
                </div>
                <p className="mt-1 text-xs text-slate-500">The flag matching the adjournment reason is set automatically.</p>
              </fieldset>
            )}
            <Field label="Notes (optional)">
              <textarea className={inputCls} rows={2} value={form.notes} onChange={(e) => setF("notes", e.target.value)} />
            </Field>
            <div className="flex justify-end"><Button variant="primary" disabled={busy}>{busy ? "Saving…" : "Save hearing"}</Button></div>
          </form>
        )}
      </Card>
    </div>
  );
}

function RegisterForm({ reference }: { reference: Reference }) {
  const [form, setForm] = useState({ court_level: "District", case_type: "", court_station: "", n_parties: 2, represented: false, filing_date: today() });
  const [result, setResult] = useState<{ tone: "success" | "error"; text: string; id?: string } | null>(null);
  const types = reference.case_types_by_level[form.court_level] ?? [];

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const c = await api.post<{ id: string; risk: Risk | null }>("/cases", form);
      setResult({ tone: "success", text: `Registered ${c.id}${c.risk ? ` · initial risk ${c.risk.category} (${pct(c.risk.probability)})` : ""}.`, id: c.id });
    } catch (err) {
      setResult({ tone: "error", text: (err as Error).message });
    }
  };

  return (
    <Card title="Register a new case" className="max-w-2xl">
      <form onSubmit={submit} className="space-y-4">
        {result && <Alert tone={result.tone}>{result.text} {result.id && <Link className="font-medium underline" to={`/cases/${result.id}`}>Open</Link>}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Court level">
            <select className={inputCls} value={form.court_level} onChange={(e) => setForm({ ...form, court_level: e.target.value, case_type: "" })}>
              {reference.court_levels.map((l) => <option key={l}>{l}</option>)}
            </select>
          </Field>
          <Field label="Case type">
            <select className={inputCls} value={form.case_type} onChange={(e) => setForm({ ...form, case_type: e.target.value })} required>
              <option value="">Select…</option>
              {types.map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Court station">
            <select className={inputCls} value={form.court_station} onChange={(e) => setForm({ ...form, court_station: e.target.value })} required>
              <option value="">Select…</option>
              {reference.stations.map((s) => <option key={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Filing date">
            <input type="date" className={inputCls} value={form.filing_date} max={today()} onChange={(e) => setForm({ ...form, filing_date: e.target.value })} required />
          </Field>
          <Field label="Number of parties">
            <input type="number" min={2} max={50} className={inputCls} value={form.n_parties} onChange={(e) => setForm({ ...form, n_parties: Number(e.target.value) })} />
          </Field>
          <Field label="Legal representation">
            <select className={inputCls} value={form.represented ? "yes" : "no"} onChange={(e) => setForm({ ...form, represented: e.target.value === "yes" })}>
              <option value="no">No</option><option value="yes">Yes</option>
            </select>
          </Field>
        </div>
        <p className="text-xs text-slate-500">Region is derived from the station and is used only for the fairness audit, never for scoring.</p>
        <div className="flex justify-end"><Button variant="primary">Register case</Button></div>
      </form>
    </Card>
  );
}
