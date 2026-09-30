import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, Empty, Field, Loading, Modal, PageHeader, cx, fmtDate, inputCls, useFetch } from "../components/ui";
import { useToast } from "../components/motion";

interface Esc {
  id: number; cycle_id: string; case_id: string; note: string; consecutive_high_cycles: number; created_at: string;
  court_station: string; court_level: string; case_type: string; case_status: string;
  acknowledged_by: string | null; acknowledged_at: string | null; response: string;
}

export default function Escalations() {
  const { user } = useAuth();
  const [showAll, setShowAll] = useState(false);
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
      toast.success(`Escalation for ${caseId} acknowledged.`);
      setLeaving(id);
      setTimeout(() => { reload().then(() => setLeaving(null)); }, showAll ? 0 : 280);
    } catch (e) { setErr((e as Error).message); }
  };

  const byStation = (data ?? []).filter((e) => !e.acknowledged_by).reduce<Record<string, number>>((acc, e) => {
    acc[e.court_station] = (acc[e.court_station] ?? 0) + 1; return acc;
  }, {});

  return (
    <>
      <PageHeader title="Escalations" subtitle="Cases rated High risk across consecutive review cycles with no registrar action."
        actions={<label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} className="accent-brand-600" /> Include acknowledged</label>} />
      {error && <Alert tone="error">{error}</Alert>}
      {!data ? <Loading /> : data.length === 0 ? <Empty>No escalations.</Empty> : (
        <div className="grid gap-6 lg:grid-cols-4">
          {/* Pinned beside the list while it scrolls; no entrance animation. */}
          <Card still title="Open by station" className="self-start lg:sticky lg:top-20 lg:col-span-1">
            <ul className="scroll-thin max-h-[calc(100vh-11rem)] space-y-1 overflow-y-auto text-sm">
              {Object.entries(byStation).sort((a, b) => b[1] - a[1]).map(([s, n]) => (
                <li key={s} className="flex justify-between"><span>{s}</span><span className="tabular-nums font-medium">{n}</span></li>
              ))}
            </ul>
          </Card>
          <div className="stagger space-y-3 lg:col-span-3">
            {data.map((e) => (
              <div key={e.id} className={cx("rounded-md border-l-4 bg-white p-4 shadow-[0_0_13px_0_rgba(236,236,241,0.9)] ring-1 ring-slate-900/4 transition duration-200 hover:shadow-md", e.acknowledged_by ? "border-ok" : "border-danger", leaving === e.id && !showAll && "leave")}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <Link to={`/cases/${e.case_id}`} className="font-semibold text-brand-600 hover:underline">{e.case_id}</Link>
                    <span className="text-sm text-slate-500"> · {e.case_type} · {e.court_level} · {e.court_station} · raised {fmtDate(e.created_at)}</span>
                    <p className="mt-1 text-sm text-slate-700">{e.note}</p>
                    {e.acknowledged_by && <p className="mt-2 text-sm text-brand-700">Acknowledged by {e.acknowledged_by}: {e.response}</p>}
                  </div>
                  {canAck && !e.acknowledged_by && <Button onClick={() => { setAck(e); setErr(null); }}>Acknowledge</Button>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <Modal title={`Acknowledge escalation: ${ack?.case_id ?? ""}`} open={!!ack} onClose={() => setAck(null)}>
        {err && <div className="mb-3"><Alert tone="error">{err}</Alert></div>}
        <Field label="What action is court management taking?">
          <textarea className={inputCls} rows={3} value={response} onChange={(e) => setResponse(e.target.value)} autoFocus />
        </Field>
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={() => setAck(null)}>Cancel</Button>
          <Button variant="primary" disabled={!response.trim()} onClick={submit}>Acknowledge</Button>
        </div>
      </Modal>
    </>
  );
}
