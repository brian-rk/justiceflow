import { useState } from "react";
import { Link } from "react-router-dom";
import { ClipboardList } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, DelayBadge, Empty, Field, Loading, Modal, PageHeader, RemandBadge, cx, fmtDate, fmtDays, inputCls, useFetch } from "../components/ui";
import { useToast } from "../components/motion";
import { t, tBodies } from "../i18n";

export interface Esc {
  id: number; cycle_id: string; case_id: string; note: string; consecutive_high_cycles: number; created_at: string;
  court_station: string; court_level: string; case_type: string; case_status: string;
  acknowledged_by: string | null; acknowledged_at: string | null; response: string;
  responsible: string; in_custody: boolean; days_pending: number; delay_status: string | null;
}

export default function Escalations() {
  const { user } = useAuth();
  const [showAll, setShowAll] = useState(false);
  const [body, setBody] = useState("");
  const { data, error, reload } = useFetch(() => api.get<Esc[]>("/escalations", { include_acknowledged: showAll }), [showAll]);
  const [ack, setAck] = useState<Esc | null>(null);
  const [response, setResponse] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [leaving, setLeaving] = useState<number | null>(null);
  const toast = useToast();
  const canAck = user?.role === "management" || user?.role === "admin";

  const submit = async () => {
    if (!ack) return;
    try {
      await api.post(`/escalations/${ack.id}/acknowledge`, { response });
      const id = ack.id, caseId = ack.case_id;
      setAck(null);
      setResponse("");
      toast.success(t("Escalation for {id} acknowledged.", { id: caseId }));
      setLeaving(id);
      setTimeout(() => { reload().then(() => setLeaving(null)); }, showAll ? 0 : 280);
    } catch (e) { setErr((e as Error).message); }
  };

  const open = (data ?? []).filter((e) => !e.acknowledged_by);
  const count = (key: (e: Esc) => string[]) => open.reduce<Record<string, number>>((acc, e) => {
    for (const k of key(e)) acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});
  const byBody = count((e) => e.responsible.split("; "));
  const byStation = count((e) => [e.court_station]);
  const shown = (data ?? []).filter((e) => !body || e.responsible.split("; ").includes(body));

  return (
    <>
      <PageHeader title={t("Escalations")} subtitle={t("Cases rated High risk across consecutive weeks with no registrar action, for the case-flow committee. Each names who can unblock it.")}
        actions={<>
          <Link to="/escalations/agenda" className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3.5 py-1.5 text-sm font-medium text-ink transition hover:bg-slate-50">
            <ClipboardList size={16} /> {t("Committee agenda")}
          </Link>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} className="accent-brand-600" /> {t("Include acknowledged")}</label>
        </>} />
      {error && <Alert tone="error">{error}</Alert>}
      {!data ? <Loading /> : data.length === 0 ? <Empty>{t("No escalations.")}</Empty> : (
        <div className="grid gap-6 lg:grid-cols-4">
          {/* Pinned beside the list while it scrolls; no entrance animation. */}
          <div className="space-y-6 self-start lg:sticky lg:top-20 lg:col-span-1">
            <Card still title={t("Who can unblock them")}>
              <ul className="space-y-1 text-sm">
                <li><button onClick={() => setBody("")} className={cx("flex w-full justify-between rounded px-2 py-1 text-left hover:bg-slate-50", !body && "bg-brand-50 font-medium text-brand-700")}><span>{t("All")}</span><span className="tabular-nums">{open.length}</span></button></li>
                {Object.entries(byBody).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                  <li key={k}><button onClick={() => setBody(k)} className={cx("flex w-full justify-between gap-2 rounded px-2 py-1 text-left hover:bg-slate-50", body === k && "bg-brand-50 font-medium text-brand-700")}><span>{t(k)}</span><span className="tabular-nums">{n}</span></button></li>
                ))}
              </ul>
            </Card>
            <Card still title={t("Open by station")}>
              <ul className="scroll-thin max-h-72 space-y-1 overflow-y-auto text-sm">
                {Object.entries(byStation).sort((a, b) => b[1] - a[1]).map(([s, n]) => (
                  <li key={s} className="flex justify-between"><span>{s}</span><span className="tabular-nums font-medium">{n}</span></li>
                ))}
              </ul>
            </Card>
          </div>
          <div className="stagger space-y-3 lg:col-span-3">
            {shown.map((e) => (
              <div key={e.id} className={cx("rounded-md border-l-4 bg-white p-4 shadow-[0_0_13px_0_rgba(236,236,241,0.9)] ring-1 ring-slate-900/4 transition duration-200 hover:shadow-md", e.acknowledged_by ? "border-ok" : "border-danger", leaving === e.id && !showAll && "leave")}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/cases/${e.case_id}`} className="font-semibold text-brand-600 hover:underline">{e.case_id}</Link>
                      <span className="text-sm text-slate-500">{t(e.case_type)}, {t(e.court_level)}, {e.court_station}</span>
                      {e.delay_status && <DelayBadge status={e.delay_status} />}
                      {e.in_custody && <RemandBadge />}
                    </div>
                    <p className="mt-1 text-sm text-slate-700">
                      {t("High risk for {n} consecutive weeks with no registrar action. Pending {d}.", { n: e.consecutive_high_cycles, d: fmtDays(e.days_pending) })}
                    </p>
                    <p className="mt-1 text-sm"><span className="font-medium text-ink">{t("For")}:</span> <span className="text-slate-600">{tBodies(e.responsible)}</span></p>
                    <p className="mt-0.5 text-xs text-slate-500">{t("Raised {date}", { date: fmtDate(e.created_at) })}</p>
                    {e.acknowledged_by && <p className="mt-2 text-sm text-brand-700">{t("Acknowledged by {who}", { who: e.acknowledged_by })}: {e.response}</p>}
                  </div>
                  {canAck && !e.acknowledged_by && <Button onClick={() => { setAck(e); setErr(null); }}>{t("Acknowledge")}</Button>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <Modal title={t("Acknowledge escalation: {id}", { id: ack?.case_id ?? "" })} open={!!ack} onClose={() => setAck(null)}>
        {err && <div className="mb-3"><Alert tone="error">{err}</Alert></div>}
        <Field label={t("What action is being taken, and by whom?")}>
          <textarea className={inputCls} rows={3} value={response} onChange={(e) => setResponse(e.target.value)} autoFocus />
        </Field>
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={() => setAck(null)}>{t("Cancel")}</Button>
          <Button variant="primary" disabled={!response.trim()} onClick={submit}>{t("Acknowledge")}</Button>
        </div>
      </Modal>
    </>
  );
}
