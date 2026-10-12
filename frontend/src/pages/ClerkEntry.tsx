import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { CalendarCheck } from "lucide-react";
import { api } from "../api";
import { Alert, Button, Card, DelayBadge, Field, PageHeader, RemandBadge, RiskBadge, fmtDate, inputCls, pct, useFetch } from "../components/ui";
import type { CaseDetail, NextDateSuggestion, Reference, Risk } from "../types";
import { FadeSwap, Tabs, useToast } from "../components/motion";
import { t, tReason } from "../i18n";

const today = () => new Date().toISOString().slice(0, 10);
const FLAGS = ["flag_advocate", "flag_prosecution", "flag_forensic", "flag_witness", "flag_record"] as const;
type Flag = (typeof FLAGS)[number];

export default function ClerkEntry() {
  const ref = useFetch(() => api.get<Reference>("/reference"));
  const [tab, setTab] = useState<"hearing" | "register">("hearing");
  return (
    <>
      <PageHeader title={t("Case data entry")} subtitle={t("Record hearing outcomes, delay causes and the next date fixed in court. Each entry re-scores the case for the registrar's review.")} />
      <Tabs value={tab} onChange={setTab} tabs={[["hearing", t("Record a hearing")], ["register", t("Register a new case")]] as const} />
      {ref.data && <FadeSwap k={tab}>{tab === "hearing" ? <HearingForm reference={ref.data} /> : <RegisterForm reference={ref.data} />}</FadeSwap>}
    </>
  );
}

function HearingForm({ reference }: { reference: Reference }) {
  const [caseNo, setCaseNo] = useState("");
  const [c, setCase] = useState<CaseDetail | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const blank = { hearing_date: today(), outcome: "adjourned", adjournment_reason: "", next_date: "", notes: "",
    in_custody: false, ...Object.fromEntries(FLAGS.map((f) => [f, false])) as Record<Flag, boolean> };
  const [form, setForm] = useState(blank);
  const [suggestion, setSuggestion] = useState<NextDateSuggestion | null>(null);
  const [result, setResult] = useState<{ tone: "success" | "error"; text: string; risk?: Risk | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const criminal = !!c && reference.criminal_types.includes(c.case_type);

  const lookup = async (e?: FormEvent) => {
    e?.preventDefault();
    setLookupError(null);
    setResult(null);
    if (!caseNo.trim()) { setLookupError(t("Enter a case number, for example SYN-00042.")); return; }
    try {
      const d = await api.get<CaseDetail>(`/cases/${caseNo.trim()}`);
      setCase(d);
      setForm({ ...blank, ...d.active_flags, in_custody: d.in_custody });
    } catch (err) {
      setCase(null);
      setLookupError((err as Error).message);
    }
  };

  // Ask for a next-date suggestion whenever the hearing details change.
  useEffect(() => {
    if (!c || c.status !== "Pending" || !form.hearing_date) return;
    if (form.outcome === "adjourned" && !form.adjournment_reason) { setSuggestion(null); return; }
    const id = setTimeout(() => {
      api.post<NextDateSuggestion>(`/cases/${c.id}/suggest-next-date`, {
        hearing_date: form.hearing_date, outcome: form.outcome,
        adjournment_reason: form.outcome === "adjourned" ? form.adjournment_reason : null,
        in_custody: criminal ? form.in_custody : null, ...Object.fromEntries(FLAGS.map((f) => [f, form[f]])),
      }).then(setSuggestion).catch(() => setSuggestion(null));
    }, 250);
    return () => clearTimeout(id);
  }, [c, form.hearing_date, form.outcome, form.adjournment_reason, form.in_custody, criminal, ...FLAGS.map((f) => form[f])]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!c) return;
    setBusy(true);
    try {
      const res = await api.post<{ hearing_no: number; rescored_risk: Risk | null }>(`/cases/${c.id}/hearings`, {
        ...form,
        adjournment_reason: form.outcome === "adjourned" ? form.adjournment_reason : null,
        next_date: form.outcome === "disposed" || !form.next_date ? null : form.next_date,
        in_custody: criminal ? form.in_custody : null,
      });
      setResult({ tone: "success", text: t("Hearing #{n} recorded for {id}.", { n: res.hearing_no, id: c.id }), risk: res.rescored_risk });
      toast.success(t("Hearing #{n} saved; {id} re-scored.", { n: res.hearing_no, id: c.id }));
      const d = await api.get<CaseDetail>(`/cases/${c.id}`);
      setCase(d);
      setForm({ ...blank, ...d.active_flags, in_custody: d.in_custody });
    } catch (err) {
      setResult({ tone: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const setF = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const reasons = Object.entries(reference.adjournment_reasons).filter(([k]) =>
    (criminal || !["prosecution", "forensic"].includes(k)) && (k !== "advocate" || !reference.no_advocates_levels.includes(c?.court_level ?? "")));

  return (
    <Card title={t("Record a hearing")} className="max-w-3xl">
      <form onSubmit={lookup}>
        <label htmlFor="case-no" className="mb-1.5 block text-[13px] font-medium text-ink">{t("Case number")}</label>
        <div className="flex gap-2">
          <input id="case-no" className={inputCls} placeholder={t("e.g. SYN-00042")} value={caseNo} onChange={(e) => setCaseNo(e.target.value)} autoFocus />
          <Button variant="primary" className="px-5">{t("Find case")}</Button>
        </div>
        <p className="mt-1.5 text-xs text-slate-500">{t("Or browse the")} <Link to="/cases" className="text-brand-600 hover:underline">{t("case list")}</Link>.</p>
      </form>
      {lookupError && <div className="mt-3"><Alert tone="error">{lookupError}</Alert></div>}

      {c && (
        <div key={c.id} className="mt-5 animate-fade-up">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 rounded-md bg-brand-50/70 px-4 py-3 text-sm">
            <Link to={`/cases/${c.id}`} className="font-semibold text-brand-700 hover:underline">{c.id}</Link>
            <span className="text-slate-600">{t(c.case_type)}{c.offence !== "Not criminal" && `, ${t(c.offence)}`}, {t(c.division)}, {c.court_station}</span>
            <span className="text-slate-600">{t("Filed {date}", { date: fmtDate(c.filing_date) })}</span>
            <span className="text-slate-600">{c.next_date ? t("Due {date}", { date: fmtDate(c.next_date) }) : t("No next date fixed")}</span>
            {c.in_custody && <RemandBadge days={c.remand_days} />}
          </div>
        </div>
      )}

      {c && (c.status !== "Pending" ? <div className="mt-4"><Alert tone="info">{t("This case is disposed, so no further hearings can be recorded.")}</Alert></div> : (
        <form onSubmit={submit} className="mt-5 space-y-4 border-t border-slate-100 pt-5">
          {result && <Alert tone={result.tone}>
            {result.text}
            {result.risk && <span className="ml-2 inline-flex items-center gap-2">{t("Re-scored")}: <RiskBadge category={result.risk.category} /> {pct(result.risk.probability)} <DelayBadge status={result.risk.delay_status} /></span>}
          </Alert>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("Hearing date")}>
              <input type="date" className={inputCls} value={form.hearing_date} max={today()} onChange={(e) => setF("hearing_date", e.target.value)} required />
            </Field>
            <Field label={t("Outcome")}>
              <select className={inputCls} value={form.outcome} onChange={(e) => setF("outcome", e.target.value)}>
                <option value="proceeded">{t("Proceeded (hearing took place)")}</option>
                <option value="adjourned">{t("Adjourned")}</option>
                <option value="disposed">{t("Disposed (case concluded)")}</option>
              </select>
            </Field>
          </div>
          {form.outcome === "adjourned" && (
            <div className="animate-fade-up"><Field label={t("Adjournment reason")}>
              <select className={inputCls} value={form.adjournment_reason} onChange={(e) => setF("adjournment_reason", e.target.value)} required>
                <option value="">{t("Select…")}</option>
                {reasons.map(([k, l]) => <option key={k} value={k}>{t(l)}</option>)}
              </select>
            </Field></div>
          )}
          {form.outcome !== "disposed" && (
            <fieldset className="animate-fade-up">
              <legend className="mb-1 text-xs font-medium text-slate-600">{t("External-delay flags still active after this hearing")}</legend>
              <div className="grid gap-1 sm:grid-cols-2">
                {FLAGS.map((k) => (
                  <label key={k} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form[k]} onChange={(e) => setF(k, e.target.checked)} className="h-4 w-4 accent-brand-600" />
                    {t(reference.flag_labels[k])}
                  </label>
                ))}
              </div>
              <p className="mt-1 text-xs text-slate-500">{t("The flag matching the adjournment reason is set automatically.")}</p>
            </fieldset>
          )}
          {criminal && form.outcome !== "disposed" && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.in_custody} onChange={(e) => setF("in_custody", e.target.checked)} className="h-4 w-4 accent-brand-600" />
              {t("Accused still in remand after this hearing (untick if bail was granted)")}
            </label>
          )}
          {form.outcome !== "disposed" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("Next date fixed in court")} hint={t("The judge or magistrate fixes the date in open court. Record what was fixed.")}>
                <input type="date" className={inputCls} value={form.next_date} min={form.hearing_date} onChange={(e) => setF("next_date", e.target.value)} />
              </Field>
              {suggestion?.date && (
                <div className="rounded-md border border-brand-200 bg-brand-50/60 p-3 text-sm animate-fade-in">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 font-medium text-brand-700"><CalendarCheck size={16} /> {t("Suggested: {date}", { date: fmtDate(suggestion.date) })}</span>
                    <Button type="button" className="px-2 py-1 text-xs" onClick={() => setF("next_date", suggestion.date!)}>{t("Use this date")}</Button>
                  </div>
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-slate-600">
                    {suggestion.reasons.map((r) => <li key={r}>{tReason(r)}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
          <Field label={t("Notes (optional)")}>
            <textarea className={inputCls} rows={2} value={form.notes} onChange={(e) => setF("notes", e.target.value)} />
          </Field>
          <div className="flex justify-end"><Button variant="primary" disabled={busy}>{busy ? t("Saving…") : t("Save hearing")}</Button></div>
        </form>
      ))}
    </Card>
  );
}

function RegisterForm({ reference }: { reference: Reference }) {
  const [form, setForm] = useState({ court_level: "District", case_type: "", court_station: "", n_parties: 2, represented: false,
    filing_date: today(), offence: "", in_custody: false, next_date: "" });
  const [result, setResult] = useState<{ tone: "success" | "error"; text: string; id?: string } | null>(null);
  const types = reference.case_types_by_level[form.court_level] ?? [];
  const criminal = reference.criminal_types.includes(form.case_type);
  const noAdvocates = reference.no_advocates_levels.includes(form.court_level);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const c = await api.post<{ id: string; risk: Risk | null }>("/cases", {
        ...form, represented: noAdvocates ? false : form.represented,
        offence: form.case_type === "Criminal" ? form.offence : null, in_custody: criminal && form.in_custody,
        next_date: form.next_date || null,
      });
      setResult({ tone: "success", text: c.risk ? t("Registered {id}. Initial risk {cat} ({p}).", { id: c.id, cat: t(c.risk.category), p: pct(c.risk.probability) }) : t("Registered {id}.", { id: c.id }), id: c.id });
    } catch (err) {
      setResult({ tone: "error", text: (err as Error).message });
    }
  };

  return (
    <Card title={t("Register a new case")} className="max-w-2xl">
      <form onSubmit={submit} className="space-y-4">
        {result && <Alert tone={result.tone}>{result.text} {result.id && <Link className="font-medium underline" to={`/cases/${result.id}`}>{t("Open")}</Link>}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("Court level")}>
            <select className={inputCls} value={form.court_level} onChange={(e) => setForm({ ...form, court_level: e.target.value, case_type: "" })}>
              {reference.court_levels.map((l) => <option key={l} value={l}>{t(l)}</option>)}
            </select>
          </Field>
          <Field label={t("Case type")} hint={!types.includes("Land") ? t("Land disputes go to the District Land and Housing Tribunal or the High Court Land Division.") : undefined}>
            <select className={inputCls} value={form.case_type} onChange={(e) => setForm({ ...form, case_type: e.target.value })} required>
              <option value="">{t("Select…")}</option>
              {types.map((x) => <option key={x} value={x}>{t(x)}</option>)}
            </select>
          </Field>
          {form.case_type === "Criminal" && (
            <Field label={t("Offence")}>
              <select className={inputCls} value={form.offence} onChange={(e) => setForm({ ...form, offence: e.target.value })} required>
                <option value="">{t("Select…")}</option>
                {reference.offences.filter((o) => o !== "Corruption / economic" || form.court_level !== "Primary").map((o) => <option key={o} value={o}>{t(o)}</option>)}
              </select>
            </Field>
          )}
          <Field label={t("Court station")}>
            <select className={inputCls} value={form.court_station} onChange={(e) => setForm({ ...form, court_station: e.target.value })} required>
              <option value="">{t("Select…")}</option>
              {reference.stations.map((s) => <option key={s}>{s}</option>)}
            </select>
          </Field>
          <Field label={t("Filing date")}>
            <input type="date" className={inputCls} value={form.filing_date} max={today()} onChange={(e) => setForm({ ...form, filing_date: e.target.value })} required />
          </Field>
          <Field label={t("First date fixed (optional)")}>
            <input type="date" className={inputCls} value={form.next_date} min={form.filing_date} onChange={(e) => setForm({ ...form, next_date: e.target.value })} />
          </Field>
          <Field label={criminal ? t("Number of accused") : t("Number of parties")}>
            <input type="number" min={1} max={50} className={inputCls} value={criminal ? form.n_parties - 1 : form.n_parties}
              onChange={(e) => setForm({ ...form, n_parties: Math.max(2, Number(e.target.value) + (criminal ? 1 : 0)) })} />
          </Field>
          <Field label={t("Legal representation")} hint={noAdvocates ? t("Advocates may not appear in a Primary Court (Magistrates' Courts Act, s.33).") : undefined}>
            <select className={inputCls} value={form.represented && !noAdvocates ? "yes" : "no"} disabled={noAdvocates} onChange={(e) => setForm({ ...form, represented: e.target.value === "yes" })}>
              <option value="no">{t("No")}</option><option value="yes">{t("Yes")}</option>
            </select>
          </Field>
        </div>
        {criminal && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.in_custody} onChange={(e) => setForm({ ...form, in_custody: e.target.checked })} className="h-4 w-4 accent-brand-600" />
            {t("Accused held in remand")}
          </label>
        )}
        <p className="text-xs text-slate-500">{t("Region is derived from the station and is used only for the fairness audit, never for scoring.")}</p>
        <div className="flex justify-end"><Button variant="primary">{t("Register case")}</Button></div>
      </form>
    </Card>
  );
}
