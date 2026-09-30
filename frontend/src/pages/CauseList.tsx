import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, DelayBadge, Empty, Field, Loading, Modal, PageHeader, RiskBadge, cx, fmtDate, inputCls, inputInline, td, th, useFetch } from "../components/ui";
import type { Cycle, CycleDetail, Listing } from "../types";
import { Num, useToast } from "../components/motion";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

export default function CauseList() {
  const { cycleId } = useParams();
  const cycles = useFetch(() => api.get<Cycle[]>("/cycles"));
  const nav = useNavigate();
  const { user } = useAuth();
  const toast = useToast();
  const [creating, setCreating] = useState(false);

  const current = cycleId ?? cycles.data?.[0]?.id;
  const isRegistrar = user?.role === "registrar";
  const open = cycles.data?.find((c) => c.status === "PROPOSED");

  const create = async () => {
    setCreating(true);
    try {
      const c = await api.post<Cycle>("/cycles", {});
      await cycles.reload();
      toast.success(<>Cause list for the week of <b>{fmtDate(c.week_start)}</b> proposed ({c.listings} listings).</>);
      nav(`/cause-list/${c.id}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Cause list"
        subtitle="The optimiser's proposed magistrate-and-day assignments. Nothing is scheduled until the registrar approves it."
        actions={isRegistrar && !open && <Button variant="primary" onClick={create} disabled={creating}>{creating ? "Optimising…" : "Propose next week's list"}</Button>}
      />
      {cycles.data && cycles.data.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {cycles.data.map((c) => (
            <Link key={c.id} to={`/cause-list/${c.id}`}
              className={cx("rounded-md border px-3 py-1.5 text-sm transition duration-200 hover:-translate-y-0.5", c.id === current ? "border-brand-500 bg-brand-50 font-medium text-brand-700 shadow-sm" : "border-slate-200 bg-white text-muted hover:border-brand-300 hover:text-ink")}>
              Week of {fmtDate(c.week_start)} <span className={cx("ml-1 text-xs", c.status === "PROPOSED" ? "text-amber-700" : "text-slate-400")}>{c.status === "PROPOSED" ? "awaiting approval" : "approved"}</span>
            </Link>
          ))}
        </div>
      )}
      {cycles.loading && !cycles.data ? <Loading /> : !current ? <Empty>No cause lists yet.{isRegistrar && " Propose one for next week."}</Empty> :
        <CycleView key={current} cycleId={current} canEdit={isRegistrar} onChanged={cycles.reload} />}
    </>
  );
}

function CycleView({ cycleId, canEdit, onChanged }: { cycleId: string; canEdit: boolean; onChanged: () => void }) {
  const { data, error, reload, loading, setData } = useFetch(() => api.get<CycleDetail>(`/cycles/${cycleId}`), [cycleId]);
  const toast = useToast();
  const [flash, setFlash] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "undecided" | "High">("all");
  const [day, setDay] = useState<string>("all");
  const [editing, setEditing] = useState<Listing | null>(null);
  const [removing, setRemoving] = useState<Listing | null>(null);
  const [confirmFinal, setConfirmFinal] = useState(false);

  const rows = useMemo(() => (data?.items ?? []).filter((r) =>
    (filter === "all" || (filter === "undecided" ? r.decision === null : r.risk_category === "High")) &&
    (day === "all" || r.day === day)), [data, filter, day]);

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;
  const editable = canEdit && data.status === "PROPOSED";
  const undecided = data.listings - data.decided;

  const act = async (fn: () => Promise<unknown>, ok: string, touched: string[] = []) => {
    try {
      await fn();
      toast.success(ok);
      await reload();
      setFlash(new Set(touched));
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  /** Optimistic: mark the row approved at once, confirm with the server in the background. */
  const approve = async (r: Listing) => {
    setBusy(r.case_id);
    try {
      await api.post(`/cycles/${cycleId}/decisions`, { case_id: r.case_id, action: "approve" });
      setData((d) => d && {
        ...d,
        decided: d.decided + 1,
        approved: d.approved + 1,
        items: d.items.map((x) => (x.case_id === r.case_id ? { ...x, decision: "approve" } : x)),
      });
      setFlash(new Set([r.case_id]));
      toast.success(`${r.case_id} approved.`);
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
      reload();
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MiniStat label="Proposed listings" value={<Num value={data.listings} />} />
        <MiniStat label="Approved / edited" value={<Num value={data.approved} />} />
        <MiniStat label="Undecided" value={<Num value={undecided} />} warn={undecided > 0 && data.status === "PROPOSED"} />
        <MiniStat label="Solver" value={`${data.solver_info.solver_status ?? "—"} · ${data.solver_info.wall_time_s ?? "?"}s`} small />
      </div>
      {data.status === "APPROVED" && <div className="mb-4"><Alert tone="info">Approved by {data.finalised_by} on {fmtDate(data.finalised_at)}. Listings without a registrar decision were not scheduled.</Alert></div>}

      <Card
        title={`Week of ${fmtDate(data.week_start)}`}
        actions={editable && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => act(() => api.post(`/cycles/${cycleId}/approve-all`), "All remaining listings approved.", data.items.filter((r) => !r.decision).map((r) => r.case_id))} disabled={undecided === 0}>Approve all remaining</Button>
            <Button variant="primary" onClick={() => setConfirmFinal(true)}>Finalise cause list</Button>
          </div>
        )}
      >
        <div className="mb-3 flex flex-wrap gap-2">
          <select aria-label="Filter" className={inputInline} value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
            <option value="all">All listings</option><option value="undecided">Undecided only</option><option value="High">High risk only</option>
          </select>
          <select aria-label="Day" className={inputInline} value={day} onChange={(e) => setDay(e.target.value)}>
            <option value="all">All days</option>{DAYS.map((d) => <option key={d}>{d}</option>)}
          </select>
          <span key={rows.length} className="self-center text-sm text-muted animate-fade-in">{rows.length} shown</span>
        </div>
        <div className={cx("scroll-thin max-h-[65vh] overflow-auto transition-opacity duration-200", loading && "opacity-60")}>
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 z-10 bg-white">
              <tr><th className={th}>Day</th><th className={th}>Magistrate</th><th className={th}>#</th><th className={th}>Case</th><th className={th}>Risk</th><th className={th}>Delay status</th><th className={th}>Why</th><th className={th}>Decision</th></tr>
            </thead>
            <tbody key={`${filter}-${day}`} className="stagger-rows row-accent divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.case_id} className={cx("transition-[opacity,background-color] duration-300 hover:bg-brand-50/50", r.decision === "remove" && "opacity-50", flash.has(r.case_id) && "flash-ok")}>
                  <td className={td}>{r.day}<div className="text-xs text-slate-500">{fmtDate(r.date).slice(0, 6)}</div></td>
                  <td className={td}>{r.magistrate_name}<div className="text-xs text-slate-500">{r.court_station}</div></td>
                  <td className={td + " tabular-nums"}>{r.position}</td>
                  <td className={td}><Link to={`/cases/${r.case_id}`} className="font-medium text-brand-600 hover:underline">{r.case_id}</Link></td>
                  <td className={td}><RiskBadge category={r.risk_category} /><div className="text-xs tabular-nums text-slate-500">priority {r.priority}</div></td>
                  <td className={td + " max-w-48"}><DelayBadge status={r.delay_status} /></td>
                  <td className={td + " max-w-72 text-xs text-slate-600"}>{r.driving_factors}</td>
                  <td className={td + " whitespace-nowrap"}>
                    {r.decision ? (
                      <span className={cx("inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium animate-scale-in", r.decision === "remove" ? "bg-danger/10 text-danger" : "bg-ok/10 text-[#2f8a6f]")} title={r.decision_reason ?? ""}>
                        {r.decision === "approve" ? "Approved" : r.decision === "edit" ? "Edited" : "Removed"}
                      </span>
                    ) : editable ? (
                      <div className="flex gap-1">
                        <Button className="px-2 py-1 text-xs" variant="primary" disabled={busy === r.case_id} onClick={() => approve(r)}>{busy === r.case_id ? "…" : "Approve"}</Button>
                        <Button className="px-2 py-1 text-xs" onClick={() => setEditing(r)}>Edit</Button>
                        <Button className="px-2 py-1 text-xs" variant="danger" onClick={() => setRemoving(r)}>Remove</Button>
                      </div>
                    ) : <span className="text-xs text-slate-400">Not decided</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {editing && <EditModal listing={editing} options={data.magistrate_options} onClose={() => setEditing(null)}
        onSave={(body) => act(() => api.post(`/cycles/${cycleId}/decisions`, { case_id: editing.case_id, action: "edit", ...body }), `${editing.case_id} edited.`, [editing.case_id]).then(() => setEditing(null))} />}
      {removing && <ReasonModal title={`Remove ${removing.case_id} from the list`} onClose={() => setRemoving(null)}
        onSave={(reason) => act(() => api.post(`/cycles/${cycleId}/decisions`, { case_id: removing.case_id, action: "remove", reason }), `${removing.case_id} removed.`, [removing.case_id]).then(() => setRemoving(null))} />}
      <Modal title="Finalise cause list?" open={confirmFinal} onClose={() => setConfirmFinal(false)}>
        <p className="text-sm text-slate-600">
          {data.approved} listings will be scheduled.{undecided > 0 && <> <b>{undecided} undecided listings will not be scheduled.</b></>} After finalising, High-risk cases with no registrar action over the last cycles are escalated to court management.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={() => setConfirmFinal(false)}>Cancel</Button>
          <Button variant="primary" onClick={() => { setConfirmFinal(false); act(() => api.post<{ escalations: number }>(`/cycles/${cycleId}/finalise`).then((r) => { if (r.escalations) toast.info(`${r.escalations} cases escalated to court management.`); }), "Cause list finalised."); }}>Finalise</Button>
        </div>
      </Modal>
    </>
  );
}

function MiniStat({ label, value, warn, small }: { label: string; value: ReactNode; warn?: boolean; small?: boolean }) {
  return (
    <div className="rounded-md bg-white px-4 py-3 shadow-[0_0_13px_0_rgba(236,236,241,0.9)] ring-1 ring-slate-900/4 animate-fade-up">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={cx("font-semibold tabular-nums", small ? "text-sm" : "text-xl", warn && "text-amber-700")}>{value}</div>
    </div>
  );
}

function EditModal({ listing, options, onClose, onSave }: { listing: Listing; options: CycleDetail["magistrate_options"]; onClose: () => void; onSave: (b: { day: string; magistrate_id: string; reason: string }) => void }) {
  const pool = Object.entries(options).find(([, ms]) => ms.some((m) => m.id === listing.magistrate_id))?.[1] ?? [];
  const [day, setDay] = useState(listing.day);
  const [mag, setMag] = useState(listing.magistrate_id);
  const [reason, setReason] = useState("");
  const off = pool.find((m) => m.id === mag)?.unavailable_days ?? "";
  return (
    <Modal title={`Edit listing: ${listing.case_id}`} open onClose={onClose}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Day"><select className={inputCls} value={day} onChange={(e) => setDay(e.target.value)}>{DAYS.map((d) => <option key={d}>{d}</option>)}</select></Field>
          <Field label="Magistrate" hint="Same station and court level only">
            <select className={inputCls} value={mag} onChange={(e) => setMag(e.target.value)}>{pool.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>
          </Field>
        </div>
        {off.split(",").includes(day) && <Alert tone="warn">This magistrate is marked unavailable on {day}.</Alert>}
        <Field label="Reason (recorded in the audit log)"><textarea className={inputCls} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!reason.trim()} onClick={() => onSave({ day, magistrate_id: mag, reason })}>Save edit</Button>
        </div>
      </div>
    </Modal>
  );
}

function ReasonModal({ title, onClose, onSave }: { title: string; onClose: () => void; onSave: (reason: string) => void }) {
  const [reason, setReason] = useState("");
  return (
    <Modal title={title} open onClose={onClose}>
      <Field label="Reason (recorded in the audit log)"><textarea className={inputCls} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /></Field>
      <div className="mt-4 flex justify-end gap-2">
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="danger" disabled={!reason.trim()} onClick={() => onSave(reason)}>Remove from list</Button>
      </div>
    </Modal>
  );
}
