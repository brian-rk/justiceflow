import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { api } from "../api";
import { Alert, Button, Card, DelayBadge, Empty, FactorKey, Factors, Loading, PageHeader, Pager, RemandBadge, RiskBadge, RiskSummary, cx, fmtDate, fmtDays, inputInline, td, th, useFetch } from "../components/ui";
import type { CaseRow, Listing, RiskCategory } from "../types";
import { OverrideModal } from "./CaseDetail";
import { Num, useToast } from "../components/motion";
import { t, tBodies } from "../i18n";

interface Queue {
  open_cycle: string | null;
  open_cycle_week: string | null;
  undecided_listings: number;
  listings: Listing[];
  risk_pending_total: number;
  risk_pending: CaseRow[];
}

interface AttentionItem {
  case_id: string; case_type: string; court_level: string; court_station: string; risk_category: RiskCategory | null;
  next_date: string | null; delay_status: string | null; in_custody: boolean; detail: string;
  responsible?: string; remand_days?: number;
}
type Attention = Record<"date_passed" | "no_date" | "far_date_high" | "repeated_external" | "long_remand", { total: number; items: AttentionItem[] }>;

const GROUPS: [keyof Attention, string, string][] = [
  ["date_passed", "Date passed, no hearing recorded", "Ask the clerk to record what happened, or fix a new date."],
  ["no_date", "No next date fixed", "These cases will be offered free slots on next week's list."],
  ["far_date_high", "High risk, next date far away", "Consider bringing these forward."],
  ["repeated_external", "Same external delay three times in a row", "Raise with the body named, through the case-flow committee."],
  ["long_remand", "Accused in remand more than 6 months", "Priority for listing and for the committee."],
];

const LIMIT = 25;

export default function ReviewQueue() {
  const [risk, setRisk] = useState<RiskCategory | "">("High");
  const [offset, setOffset] = useState(0);
  const { data, error, reload, loading } = useFetch(() => api.get<Queue>("/review-queue", { risk, limit: LIMIT, offset }), [risk, offset]);
  const attention = useFetch(() => api.get<Attention>("/needs-attention"));
  const [override, setOverride] = useState<CaseRow | null>(null);
  const [leaving, setLeaving] = useState<Set<string>>(new Set());
  const toast = useToast();

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;

  const approve = async (ids: string[]) => {
    try {
      await api.post("/risk-review/approve-bulk", ids);
      toast.success(t("{n} risk scores approved.", { n: ids.length }));
      setLeaving(new Set(ids));  // slide the rows out, then refresh the list
      setTimeout(() => { reload().then(() => setLeaving(new Set())); }, 280);
    } catch (e) { toast.error((e as Error).message); }
  };

  return (
    <>
      <PageHeader title={t("Review queue")} subtitle={t("Everything waiting on a registrar this week: cases that need attention, cause-list listings, and new or changed risk scores.")} />

      {attention.data && <NeedsAttention data={attention.data} />}

      <Card title={t("Cause-list listings awaiting a decision")} className="mb-6"
        actions={data.open_cycle && <Link to={`/cause-list/${data.open_cycle}`} className="text-sm font-medium text-brand-600 hover:underline">{t("Open cause list")} →</Link>}>
        {!data.open_cycle ? <Empty>{t("No cause list is awaiting approval.")} <Link to="/cause-list" className="text-brand-600 hover:underline">{t("Propose one")}</Link>.</Empty> :
          data.undecided_listings === 0 ? <Alert tone="success">{t("Every listing for the week of {date} has a decision. Finalise it on the cause-list screen.", { date: fmtDate(data.open_cycle_week) })}</Alert> : (
            <p className="text-sm text-slate-700">
              <span className="text-2xl font-medium tabular-nums text-[#b8860b]"><Num value={data.undecided_listings} /></span>{" "}
              {t("listings for the week of {date} have no decision yet.", { date: fmtDate(data.open_cycle_week) })}{" "}
              {t("{a} of the first {b} are High risk.", { a: data.listings.filter((l) => l.risk_category === "High").length, b: data.listings.length })}
            </p>
          )}
      </Card>

      <Card title={t("Risk scores awaiting review ({n})", { n: data.risk_pending_total })}
        actions={
          <div className="flex gap-2">
            <select aria-label={t("Risk filter")} className={inputInline} value={risk} onChange={(e) => { setRisk(e.target.value as RiskCategory | ""); setOffset(0); }}>
              <option value="High">{t("High")}</option><option value="Medium">{t("Medium")}</option><option value="Low">{t("Low")}</option><option value="">{t("All")}</option>
            </select>
            <Button onClick={() => approve(data.risk_pending.map((c) => c.id))} disabled={!data.risk_pending.length}>{t("Approve all on this page")}</Button>
          </div>
        }>
        {data.risk_pending.length === 0 ? <Empty>{t("Nothing waiting at this risk level.")}</Empty> : (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-slate-500">{t("Most urgent first: overdue, court-controllable and remand cases, then the oldest filings.")}</p>
              <FactorKey />
            </div>
            <div className={cx("overflow-x-auto transition-opacity duration-200", loading && "opacity-60")}>
              <table className="min-w-full text-sm">
                <thead><tr><th className={th}>{t("Case")}</th><th className={th}>{t("Risk")}</th><th className={th}>{t("Delay status")}</th><th className={th}>{t("Driving factors")}</th><th className={th}></th></tr></thead>
                <tbody key={`${risk}-${offset}`} className="stagger-rows row-accent divide-y divide-slate-100">
                  {data.risk_pending.map((c) => c.risk && (
                    <tr key={c.id} className={cx("transition-colors duration-150 hover:bg-brand-50/50", leaving.has(c.id) && "leave")}>
                      <td className={td}><Link to={`/cases/${c.id}`} className="font-medium text-brand-600 hover:underline">{c.id}</Link><div className="text-xs text-slate-500">{t(c.case_type)}, {t(c.division)}</div></td>
                      <td className={td}><RiskSummary category={c.risk.category} probability={c.risk.probability} daysOverdue={c.days_overdue} /></td>
                      <td className={td + " max-w-48"}><DelayBadge status={c.risk.delay_status} />{c.in_custody && <div className="mt-1"><RemandBadge /></div>}</td>
                      <td className={td + " max-w-md"}><Factors text={c.risk.driving_factors} daysOverdue={c.days_overdue} /></td>
                      <td className={td + " whitespace-nowrap"}>
                        <div className="flex gap-1">
                          <Button className="px-2 py-1 text-xs" onClick={() => approve([c.id])}>{t("Approve")}</Button>
                          <Button className="px-2 py-1 text-xs" onClick={() => setOverride(c)}>{t("Override")}</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager total={data.risk_pending_total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
      </Card>

      {override?.risk && <OverrideModal open onClose={() => setOverride(null)} caseId={override.id} current={override.risk.category}
        onDone={() => { const id = override.id; setOverride(null); toast.success(t("Override recorded for {id}.", { id })); setLeaving(new Set([id])); setTimeout(() => { reload().then(() => setLeaving(new Set())); }, 280); }} />}
    </>
  );
}

function NeedsAttention({ data }: { data: Attention }) {
  const [open, setOpen] = useState<keyof Attention | null>(null);
  const total = GROUPS.reduce((n, [k]) => n + data[k].total, 0);
  const detail = (g: keyof Attention, r: AttentionItem) => {
    if (g === "date_passed") return t("Was due {date}", { date: fmtDate(r.next_date) });
    if (g === "far_date_high") return t("Next due {date}", { date: fmtDate(r.next_date) });
    if (g === "long_remand") return t("In remand {d}", { d: fmtDays(r.remand_days ?? 0) });
    if (g === "repeated_external") return r.responsible ? `${t("For")}: ${tBodies(r.responsible)}` : "";
    return t("No date");
  };
  return (
    <Card title={t("Needs attention this week ({n})", { n: total })} className="mb-6">
      <div className="space-y-2">
        {GROUPS.map(([key, title, hint]) => {
          const g = data[key];
          const isOpen = open === key;
          return (
            <section key={key} className="overflow-hidden rounded-md ring-1 ring-slate-200">
              <button onClick={() => setOpen(isOpen ? null : key)} aria-expanded={isOpen} disabled={!g.total}
                className="flex w-full flex-wrap items-center gap-x-3 gap-y-0.5 px-4 py-2.5 text-left transition hover:bg-slate-50 disabled:cursor-default disabled:hover:bg-transparent">
                <ChevronRight size={16} className={cx("shrink-0 text-muted transition-transform duration-200", isOpen && "rotate-90", !g.total && "opacity-30")} />
                <span className={cx("font-medium", g.total ? "text-ink" : "text-slate-500")}>{t(title)}</span>
                <span className={cx("rounded-full px-2 text-xs font-medium tabular-nums", g.total ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-500")}>{g.total}</span>
                <span className="w-full pl-7 text-xs text-slate-500 sm:ml-auto sm:w-auto sm:pl-0">{t(hint)}</span>
              </button>
              {isOpen && (
                <div className="scroll-thin max-h-80 overflow-auto border-t border-slate-100">
                  <table className="min-w-full text-sm">
                    <tbody className="divide-y divide-slate-100">
                      {g.items.map((r) => (
                        <tr key={r.case_id}>
                          <td className={td}><Link to={`/cases/${r.case_id}`} className="font-medium text-brand-600 hover:underline">{r.case_id}</Link>
                            <div className="text-xs text-slate-500">{t(r.case_type)}, {t(r.court_level)}, {r.court_station}</div></td>
                          <td className={td}><RiskBadge category={r.risk_category} /></td>
                          <td className={td + " max-w-48"}>{r.delay_status && <DelayBadge status={r.delay_status} />}{r.in_custody && key !== "long_remand" && <div className="mt-1"><RemandBadge /></div>}</td>
                          <td className={td + " text-xs text-slate-600"}>{detail(key, r)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {g.total > g.items.length && <p className="px-4 py-2 text-xs text-slate-500">{t("Showing {a} of {b}.", { a: g.items.length, b: g.total })}</p>}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </Card>
  );
}
