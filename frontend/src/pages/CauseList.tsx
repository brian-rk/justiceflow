import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, DelayBadge, Empty, FactorKey, Factors, Field, Loading, Modal, PageHeader, RemandBadge, RiskSummary, cx, dayName, fmtDate, fmtDay, inputCls, inputInline, td, th, useFetch } from "../components/ui";
import type { Cycle, CycleDetail, Listing } from "../types";
import { Num, useToast } from "../components/motion";
import { t, tn } from "../i18n";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

/** How a listing got onto the week: fixed in court, given a first date, or brought forward. */
function KindBadge({ r }: { r: Listing }) {
  const s = {
    fixed: ["bg-slate-100 text-slate-700", t("Date fixed in court")],
    new: ["bg-amber-50 text-amber-800", t("Needs a date")],
    brought_forward: ["bg-brand-50 text-brand-700", r.fixed_date ? t("Brought forward from {date}", { date: fmtDay(r.fixed_date) }) : t("Brought forward")],
  }[r.kind] ?? ["bg-slate-100 text-slate-700", r.kind];
  return <span className={cx("inline-flex whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium", s[0])}>{s[1]}</span>;
}

/** "Hon. Magistrate Arumeru DC-1" -> "Arumeru DC-1" (the title is the same on every bench). */
const shortName = (name?: string) => (name ?? "").replace(/^Hon\. (Magistrate|Judge|Justices \(panel\)) /, "");

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
      toast.success(t("Cause list for the week of {date} proposed ({n} listings).", { date: fmtDate(c.week_start), n: c.listings }));
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
        title={t("Cause list")}
        subtitle={t("Each week starts from the dates fixed in court. The optimiser only fills free slots: cases with no date yet, and high-risk cases it suggests bringing forward. Nothing is scheduled until the registrar approves it.")}
        actions={isRegistrar && !open && <Button variant="primary" onClick={create} disabled={creating}>{creating ? t("Optimising…") : t("Propose next week's list")}</Button>}
      />
      {cycles.data && cycles.data.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {cycles.data.map((c) => (
            <Link key={c.id} to={`/cause-list/${c.id}`}
              className={cx("rounded-md border px-3 py-1.5 text-sm transition duration-200 hover:-translate-y-0.5", c.id === current ? "border-brand-500 bg-brand-50 font-medium text-brand-700 shadow-sm" : "border-slate-200 bg-white text-muted hover:border-brand-300 hover:text-ink")}>
              {t("Week of {date}", { date: fmtDate(c.week_start) })} <span className={cx("ml-1 text-xs", c.status === "PROPOSED" ? "text-amber-700" : "text-slate-500")}>{t(c.status === "PROPOSED" ? "awaiting approval" : "approved")}</span>
            </Link>
          ))}
        </div>
      )}
      {cycles.loading && !cycles.data ? <Loading /> : !current ? <Empty>{t("No cause lists yet.")}{isRegistrar && " " + t("Propose one for next week.")}</Empty> :
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
  // Which day sections are expanded; null = the default (first day only).
  const [openDays, setOpenDays] = useState<Set<string> | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<Listing | null>(null);
  const [removing, setRemoving] = useState<Listing | null>(null);
  const [confirmFinal, setConfirmFinal] = useState(false);

  const rows = useMemo(() => (data?.items ?? []).filter((r) =>
    filter === "all" || (filter === "undecided" ? r.decision === null : r.risk_category === "High")), [data, filter]);

  // Day -> bench -> listings, keeping the server's order (date, magistrate, position).
  const days = useMemo(() => DAYS.map((d) => {
    const inDay = rows.filter((r) => r.day === d);
    const benches = new Map<string, Listing[]>();
    for (const r of inDay) benches.set(r.magistrate_id, [...(benches.get(r.magistrate_id) ?? []), r]);
    return { day: d, date: inDay[0]?.date, rows: inDay, benches: [...benches.values()] };
  }).filter((g) => g.rows.length), [rows]);

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;
  const editable = canEdit && data.status === "PROPOSED";
  const undecided = data.listings - data.decided;

  const defaultOpen = () => new Set(days[0] ? [days[0].day] : []);
  const isOpen = (d: string) => (openDays ?? defaultOpen()).has(d);
  const toggleDay = (d: string) => setOpenDays((cur) => {
    const next = new Set(cur ?? defaultOpen());
    if (next.has(d)) next.delete(d); else next.add(d);
    return next;
  });
  const selectable = (r: Listing) => editable && r.decision === null;
  const toggle = (ids: string[], on: boolean) => setSelected((cur) => {
    const next = new Set(cur);
    ids.forEach((id) => (on ? next.add(id) : next.delete(id)));
    return next;
  });

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
      toggle([r.case_id], false);
      toast.success(t("{id} approved.", { id: r.case_id }));
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
      reload();
    } finally {
      setBusy(null);
    }
  };
  const approveSelected = () => {
    const ids = [...selected];
    act(() => api.post(`/cycles/${cycleId}/approve-selected`, ids), t("{n} approved.", { n: tn(ids.length, "listing", "listings") }), ids)
      .then(() => setSelected(new Set()));
  };

  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MiniStat label={t("Listings")} value={<Num value={data.listings} />}
          note={data.solver_info.fixed_in_court != null ? t("{a} fixed in court, {b} added", { a: data.solver_info.fixed_in_court, b: data.solver_info.added_by_optimiser ?? 0 }) : undefined} />
        <MiniStat label={t("Approved / edited")} value={<Num value={data.approved} />} />
        <MiniStat label={t("Undecided")} value={<Num value={undecided} />} warn={undecided > 0 && data.status === "PROPOSED"} />
        <MiniStat label={t("Solver")} value={t("{s} in {n}s", { s: data.solver_info.solver_status ?? "—", n: data.solver_info.wall_time_s ?? "?" })} small />
      </div>
      {data.status === "APPROVED" && <div className="mb-4"><Alert tone="info">{t("Approved by {who} on {date}. Listings without a registrar decision were not scheduled.", { who: data.finalised_by ?? "", date: fmtDate(data.finalised_at) })}</Alert></div>}

      <Card
        title={t("Week of {date}", { date: fmtDate(data.week_start) })}
        actions={editable && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => act(() => api.post(`/cycles/${cycleId}/approve-all`), t("All remaining listings approved."), data.items.filter((r) => !r.decision).map((r) => r.case_id))} disabled={undecided === 0}>{t("Approve all remaining")}</Button>
            <Button variant="primary" onClick={() => setConfirmFinal(true)}>{t("Finalise cause list")}</Button>
          </div>
        )}
      >
        <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2">
          <select aria-label={t("Filter")} className={inputInline} value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
            <option value="all">{t("All listings")}</option><option value="undecided">{t("Undecided only")}</option><option value="High">{t("High risk only")}</option>
          </select>
          <span className="text-sm text-muted">{t("{n} shown", { n: rows.length })}</span>
          <span className="sm:ml-auto"><FactorKey /></span>
        </div>

        {selected.size > 0 && (
          <div className="sticky top-16 z-20 mb-3 flex flex-wrap items-center gap-3 rounded-md bg-brand-900 px-4 py-2.5 text-sm text-white shadow-lg animate-fade-in">
            <span>{t("{n} selected", { n: selected.size })}</span>
            <Button variant="primary" className="ml-auto" onClick={approveSelected}>{t("Approve selected")}</Button>
            <button onClick={() => setSelected(new Set())} className="rounded px-2 py-1 text-white/85 transition hover:bg-white/10 hover:text-white">{t("Clear")}</button>
          </div>
        )}

        {days.length === 0 ? <Empty>{t("No listings match this filter.")}</Empty> : (
          <div className={cx("space-y-3 transition-opacity duration-200", loading && "opacity-60")}>
            {days.map((g) => {
              const open = isOpen(g.day);
              const left = g.rows.filter((r) => r.decision === null).length;
              const high = g.rows.filter((r) => r.risk_category === "High").length;
              return (
                <section key={g.day} className="overflow-hidden rounded-md ring-1 ring-slate-200">
                  <button onClick={() => toggleDay(g.day)} aria-expanded={open}
                    className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 bg-[#f8f9fa] px-4 py-3 text-left transition hover:bg-slate-100">
                    <ChevronRight size={16} className={cx("shrink-0 text-muted transition-transform duration-200", open && "rotate-90")} />
                    <span className="font-medium text-ink">{dayName(g.day)} {fmtDay(g.date)}</span>
                    <span className="text-sm text-muted">{tn(g.rows.length, "listing", "listings")}, {tn(g.benches.length, "bench", "benches")}</span>
                    {high > 0 && <span className="text-sm text-danger">{t("{n} High risk", { n: high })}</span>}
                    {data.status === "PROPOSED" && <span className={cx("ml-auto text-sm", left ? "font-medium text-amber-800" : "text-[#2f8a6f]")}>{left ? t("{n} undecided", { n: left }) : t("All decided")}</span>}
                  </button>
                  {open && (
                    <div className="scroll-thin overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead>
                          <tr>
                            {editable && <th className={th + " w-10"}><span className="sr-only">{t("Select")}</span></th>}
                            <th className={th + " w-10"}>#</th><th className={th}>{t("Case")}</th><th className={th}>{t("Risk")}</th>
                            <th className={th}>{t("Delay status")}</th><th className={th}>{t("Why it is listed")}</th><th className={th}>{t("Decision")}</th>
                          </tr>
                        </thead>
                        {g.benches.map((bench) => {
                          const first = bench[0];
                          const ids = bench.filter(selectable).map((r) => r.case_id);
                          const all = ids.length > 0 && ids.every((id) => selected.has(id));
                          return (
                            <tbody key={first.magistrate_id} className="divide-y divide-slate-100 border-t border-slate-200">
                              <tr>
                                {editable && (
                                  <td className={td}>
                                    {ids.length > 0 && <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={all}
                                      aria-label={t("Select all undecided before {name}", { name: shortName(first.magistrate_name) })} onChange={(e) => toggle(ids, e.target.checked)} />}
                                  </td>
                                )}
                                <td colSpan={6} className="px-3 pb-1 pt-3">
                                  <span className="font-medium text-ink">{shortName(first.magistrate_name)}</span>
                                  <span className="ml-2 text-xs text-slate-500">{first.court_station}, {tn(bench.length, "case", "cases")}</span>
                                </td>
                              </tr>
                              {bench.map((r) => (
                                <tr key={r.case_id} className={cx("transition-[opacity,background-color] duration-300 hover:bg-brand-50/50", r.decision === "remove" && "opacity-50", flash.has(r.case_id) && "flash-ok")}>
                                  {editable && (
                                    <td className={td}>
                                      {selectable(r) && <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={selected.has(r.case_id)}
                                        aria-label={t("Select {id}", { id: r.case_id })} onChange={(e) => toggle([r.case_id], e.target.checked)} />}
                                    </td>
                                  )}
                                  <td className={td + " tabular-nums text-slate-500"}>{r.position}</td>
                                  <td className={td}><Link to={`/cases/${r.case_id}`} className="font-medium text-brand-600 hover:underline">{r.case_id}</Link>
                                    <div className="mt-1"><KindBadge r={r} /></div></td>
                                  <td className={td}><RiskSummary category={r.risk_category} probability={r.risk_probability} daysOverdue={r.days_overdue} /></td>
                                  <td className={td + " max-w-48"}><DelayBadge status={r.delay_status} />{r.in_custody && <div className="mt-1"><RemandBadge /></div>}</td>
                                  <td className={td + " max-w-72"}><Factors text={r.driving_factors} daysOverdue={r.days_overdue} /></td>
                                  <td className={td + " whitespace-nowrap"}>
                                    {r.decision ? (
                                      <span className={cx("inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium animate-scale-in", r.decision === "remove" ? "bg-danger/10 text-danger" : "bg-ok/10 text-[#2f8a6f]")} title={r.decision_reason ?? ""}>
                                        {t(r.decision === "approve" ? "Approved" : r.decision === "edit" ? "Edited" : "Removed")}
                                      </span>
                                    ) : editable ? (
                                      <div className="flex gap-1">
                                        <Button className="px-2 py-1 text-xs" disabled={busy === r.case_id} onClick={() => approve(r)}>{busy === r.case_id ? "…" : t("Approve")}</Button>
                                        <Button className="px-2 py-1 text-xs" variant="ghost" onClick={() => setEditing(r)}>{t("Edit")}</Button>
                                        <Button className="px-2 py-1 text-xs hover:bg-danger/5 hover:text-danger" variant="ghost" onClick={() => setRemoving(r)}>{t("Remove")}</Button>
                                      </div>
                                    ) : <span className="text-xs text-slate-500">{t("Not decided")}</span>}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          );
                        })}
                      </table>
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </Card>

      {editing && <EditModal listing={editing} options={data.magistrate_options} onClose={() => setEditing(null)}
        onSave={(body) => act(() => api.post(`/cycles/${cycleId}/decisions`, { case_id: editing.case_id, action: "edit", ...body }), t("{id} edited.", { id: editing.case_id }), [editing.case_id]).then(() => setEditing(null))} />}
      {removing && <ReasonModal title={t("Remove {id} from the list", { id: removing.case_id })} onClose={() => setRemoving(null)}
        onSave={(reason) => act(() => api.post(`/cycles/${cycleId}/decisions`, { case_id: removing.case_id, action: "remove", reason }), t("{id} removed.", { id: removing.case_id }), [removing.case_id]).then(() => setRemoving(null))} />}
      <Modal title={t("Finalise cause list?")} open={confirmFinal} onClose={() => setConfirmFinal(false)}>
        <p className="text-sm text-slate-600">
          {t("{n} listings will be scheduled and become each case's next date.", { n: data.approved })}{undecided > 0 && <> <b>{t("{n} undecided listings will not be scheduled.", { n: undecided })}</b></>} {t("After finalising, High-risk cases with no registrar action over the last cycles are escalated to the case-flow committee.")}
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={() => setConfirmFinal(false)}>{t("Cancel")}</Button>
          <Button variant="primary" onClick={() => { setConfirmFinal(false); act(() => api.post<{ escalations: number }>(`/cycles/${cycleId}/finalise`).then((r) => { if (r.escalations) toast.info(t("{n} cases escalated to the case-flow committee.", { n: r.escalations })); }), t("Cause list finalised.")); }}>{t("Finalise")}</Button>
        </div>
      </Modal>
    </>
  );
}

function MiniStat({ label, value, warn, small, note }: { label: string; value: ReactNode; warn?: boolean; small?: boolean; note?: string }) {
  return (
    <div className="rounded-md bg-white px-4 py-3 shadow-[0_0_13px_0_rgba(236,236,241,0.9)] ring-1 ring-slate-900/4 animate-fade-up">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={cx("font-semibold tabular-nums", small ? "text-sm" : "text-xl", warn && "text-amber-700")}>{value}</div>
      {note && <div className="text-xs text-slate-500">{note}</div>}
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
    <Modal title={t("Edit listing: {id}", { id: listing.case_id })} open onClose={onClose}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("Day")}><select className={inputCls} value={day} onChange={(e) => setDay(e.target.value)}>{DAYS.map((d) => <option key={d} value={d}>{dayName(d)}</option>)}</select></Field>
          <Field label={t("Magistrate")} hint={t("Same station and court level only")}>
            <select className={inputCls} value={mag} onChange={(e) => setMag(e.target.value)}>{pool.map((m) => <option key={m.id} value={m.id}>{shortName(m.name)}</option>)}</select>
          </Field>
        </div>
        {off.split(",").includes(day) && <Alert tone="warn">{t("This magistrate is marked unavailable on {day}.", { day: dayName(day) })}</Alert>}
        <Field label={t("Reason (recorded in the audit log)")}><textarea className={inputCls} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t("Cancel")}</Button>
          <Button variant="primary" disabled={!reason.trim()} onClick={() => onSave({ day, magistrate_id: mag, reason })}>{t("Save edit")}</Button>
        </div>
      </div>
    </Modal>
  );
}

function ReasonModal({ title, onClose, onSave }: { title: string; onClose: () => void; onSave: (reason: string) => void }) {
  const [reason, setReason] = useState("");
  return (
    <Modal title={title} open onClose={onClose}>
      <Field label={t("Reason (recorded in the audit log)")}><textarea className={inputCls} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /></Field>
      <div className="mt-4 flex justify-end gap-2">
        <Button onClick={onClose}>{t("Cancel")}</Button>
        <Button variant="danger" disabled={!reason.trim()} onClick={() => onSave(reason)}>{t("Remove from list")}</Button>
      </div>
    </Modal>
  );
}
