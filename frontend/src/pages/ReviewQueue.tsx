import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Alert, Button, Card, DelayBadge, Empty, Loading, PageHeader, Pager, RiskBadge, inputInline, pct, td, th, useFetch } from "../components/ui";
import type { CaseRow, Listing, RiskCategory } from "../types";
import { OverrideModal } from "./CaseDetail";
import { Num, useToast } from "../components/motion";
import { cx } from "../components/ui";

interface Queue {
  open_cycle: string | null;
  undecided_listings: number;
  listings: Listing[];
  risk_pending_total: number;
  risk_pending: CaseRow[];
}

const LIMIT = 25;

export default function ReviewQueue() {
  const [risk, setRisk] = useState<RiskCategory | "">("High");
  const [offset, setOffset] = useState(0);
  const { data, error, reload, loading } = useFetch(() => api.get<Queue>("/review-queue", { risk, limit: LIMIT, offset }), [risk, offset]);
  const [override, setOverride] = useState<CaseRow | null>(null);
  const [leaving, setLeaving] = useState<Set<string>>(new Set());
  const toast = useToast();

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;

  const approve = async (ids: string[]) => {
    try {
      await api.post("/risk-review/approve-bulk", ids);
      toast.success(`${ids.length} risk score${ids.length > 1 ? "s" : ""} approved.`);
      setLeaving(new Set(ids));  // slide the rows out, then refresh the list
      setTimeout(() => { reload().then(() => setLeaving(new Set())); }, 280);
    } catch (e) { toast.error((e as Error).message); }
  };

  return (
    <>
      <PageHeader title="Review queue" subtitle="Everything waiting on a registrar: cause-list listings and new or changed risk scores." />

      <Card title="Cause-list listings awaiting a decision" className="mb-6"
        actions={data.open_cycle && <Link to={`/cause-list/${data.open_cycle}`} className="text-sm font-medium text-brand-600 hover:underline">Open cause list →</Link>}>
        {!data.open_cycle ? <Empty>No cause list is awaiting approval. <Link to="/cause-list" className="text-brand-600 hover:underline">Propose one</Link>.</Empty> :
          data.undecided_listings === 0 ? <Alert tone="success">Every listing in {data.open_cycle} has a decision. Finalise it on the cause-list screen.</Alert> : (
            <p className="text-sm text-slate-700">
              <span className="text-2xl font-medium tabular-nums text-[#b8860b]"><Num value={data.undecided_listings} /></span> listings in <b>{data.open_cycle}</b> have no decision yet.
              {" "}{data.listings.filter((l) => l.risk_category === "High").length} of the first {data.listings.length} are High risk.
            </p>
          )}
      </Card>

      <Card title={`Risk scores awaiting review (${data.risk_pending_total})`}
        actions={
          <div className="flex gap-2">
            <select aria-label="Risk filter" className={inputInline} value={risk} onChange={(e) => { setRisk(e.target.value as RiskCategory | ""); setOffset(0); }}>
              <option value="High">High</option><option value="Medium">Medium</option><option value="Low">Low</option><option value="">All</option>
            </select>
            <Button onClick={() => approve(data.risk_pending.map((c) => c.id))} disabled={!data.risk_pending.length}>Approve all on this page</Button>
          </div>
        }>
        {data.risk_pending.length === 0 ? <Empty>Nothing waiting at this risk level.</Empty> : (
          <>
            <div className={cx("overflow-x-auto transition-opacity duration-200", loading && "opacity-60")}>
              <table className="min-w-full text-sm">
                <thead><tr><th className={th}>Case</th><th className={th}>Risk</th><th className={th}>Delay status</th><th className={th}>Driving factors</th><th className={th}></th></tr></thead>
                <tbody key={`${risk}-${offset}`} className="stagger-rows row-accent divide-y divide-slate-100">
                  {data.risk_pending.map((c) => c.risk && (
                    <tr key={c.id} className={cx("transition-colors duration-150 hover:bg-brand-50/50", leaving.has(c.id) && "leave")}>
                      <td className={td}><Link to={`/cases/${c.id}`} className="font-medium text-brand-600 hover:underline">{c.id}</Link><div className="text-xs text-slate-500">{c.case_type} · {c.court_level}</div></td>
                      <td className={td}><RiskBadge category={c.risk.category} /><div className="text-xs tabular-nums text-slate-500">{pct(c.risk.probability)}</div></td>
                      <td className={td + " max-w-48"}><DelayBadge status={c.risk.delay_status} /></td>
                      <td className={td + " max-w-md text-xs text-slate-600"}>{c.risk.driving_factors}</td>
                      <td className={td + " whitespace-nowrap"}>
                        <div className="flex gap-1">
                          <Button className="px-2 py-1 text-xs" variant="primary" onClick={() => approve([c.id])}>Approve</Button>
                          <Button className="px-2 py-1 text-xs" onClick={() => setOverride(c)}>Override</Button>
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
        onDone={() => { const id = override.id; setOverride(null); toast.success(`Override recorded for ${id}.`); setLeaving(new Set([id])); setTimeout(() => { reload().then(() => setLeaving(new Set())); }, 280); }} />}
    </>
  );
}
