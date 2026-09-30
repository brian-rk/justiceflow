import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ClipboardList, Flame, FolderOpen, ShieldCheck, ShieldX } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Card, Empty, Loading, Logo, Stat, fmtDate, useFetch } from "../components/ui";

interface Dash {
  pending: number;
  risk_counts: { High: number; Medium: number; Low: number };
  high_controllable: number;
  overdue: number;
  high_risk_awaiting_review: number;
  open_cycle: { id: string; week_start: string; awaiting_decision: number } | null;
  escalations_open: number;
  escalations_recent: { id: number; case_id: string; cycle_id: string; note: string }[];
  model: { id: number; trained_at: string; audit_passed: boolean; auc: number } | null;
}

/** Two layers of waves that drift sideways, for the welcome banner. */
function DriftingWaves() {
  const wave = "M0 40 C 100 10, 200 70, 300 40 S 500 10, 600 40 S 800 70, 900 40 S 1100 10, 1200 40 V80 H0Z";
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-0 h-20 overflow-hidden">
      <svg className="wave-drift absolute bottom-0 h-20 w-[200%]" viewBox="0 0 1200 80" preserveAspectRatio="none"><path d={wave} fill="white" opacity=".07" /></svg>
      <svg className="wave-drift-slow absolute bottom-0 h-14 w-[200%]" viewBox="0 0 1200 80" preserveAspectRatio="none"><path d={wave} fill="white" opacity=".06" /></svg>
    </div>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** Bar that grows from zero after mount. */
function GrowBar({ share, color, delay }: { share: number; color: string; delay: number }) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setW(share), 80 + delay);
    return () => clearTimeout(t);
  }, [share, delay]);
  return (
    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
      <div className={`h-2 rounded-full ${color} transition-[width] duration-700 ease-[var(--ease-out-quart)]`} style={{ width: `${w * 100}%` }} />
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const { data, error } = useFetch(() => api.get<Dash>("/dashboard"));
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;
  const total = data.risk_counts.High + data.risk_counts.Medium + data.risk_counts.Low;
  const isRegistrar = user?.role === "registrar";

  return (
    <>
      <section className="gradient-pan relative mb-6 overflow-hidden rounded-md bg-linear-to-br from-brand-900 via-[#34507a] to-brand-500 px-6 py-6 text-white shadow-lg shadow-brand-900/20 animate-scale-in md:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-16 h-56 w-56 rounded-full bg-white/10 blur-2xl animate-float" />
        <div className="relative flex items-center justify-between gap-6">
          <div className="min-w-0">
            <p className="text-sm text-white/70 animate-fade-up">{new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
            <h1 className="mt-1 text-2xl font-medium text-white animate-fade-up [animation-delay:80ms]">{greeting()}, {user?.full_name.split(" (")[0]}</h1>
            <p className="mt-2 max-w-xl text-sm text-white/80 animate-fade-up [animation-delay:160ms]">
              {data.open_cycle
                ? <><b className="text-warn">{data.open_cycle.awaiting_decision}</b> cause-list listings await a decision for the week of {fmtDate(data.open_cycle.week_start)}.</>
                : <>No cause list is waiting for approval.</>}
              {" "}<b className="text-warn">{data.risk_counts.High}</b> pending cases are rated High risk.
            </p>
          </div>
          <Logo size={88} motion="intro" className="hidden shrink-0 drop-shadow-xl sm:block" />
        </div>
        <DriftingWaves />
      </section>
      {data.model && !data.model.audit_passed && (
        <div className="mb-6"><Alert tone="error">The latest model failed the fairness audit. Scoring and scheduling are blocked until it is retrained and passes.</Alert></div>
      )}
      <div className="stagger grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat icon={FolderOpen} iconMotion="ic-rise" label="Pending cases" value={data.pending} hint={`${data.overdue} already past target`} to="/cases" />
        <Stat icon={Flame} iconMotion="ic-pulse" tone="danger" label="High risk" value={data.risk_counts.High} hint={`${data.high_controllable} court-controllable`} to="/cases?risk=High" />
        <Stat icon={ClipboardList} iconMotion="ic-check" tone="warn" label="Awaiting approval" value={data.open_cycle?.awaiting_decision ?? 0}
          hint={data.open_cycle ? `Cause list, week of ${fmtDate(data.open_cycle.week_start)}` : "No open cause list"}
          to={data.open_cycle ? `/cause-list/${data.open_cycle.id}` : "/cause-list"} />
        <Stat icon={AlertTriangle} iconMotion="ic-wiggle" tone={data.escalations_open ? "danger" : "ok"} label="Open escalations" value={data.escalations_open} hint="High risk, no registrar action" to="/escalations" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Risk distribution · pending cases">
          <div className="space-y-4">
            {(["High", "Medium", "Low"] as const).map((k, i) => {
              const n = data.risk_counts[k];
              const color = { High: "bg-danger", Medium: "bg-warn", Low: "bg-ok" }[k];
              return (
                <Link key={k} to={`/cases?risk=${k}`} className="group block">
                  <div className="flex justify-between text-sm">
                    <span className="text-ink transition group-hover:text-brand-500">{k}</span>
                    <span className="tabular-nums text-muted">{n} · {total ? Math.round((n / total) * 100) : 0}%</span>
                  </div>
                  <GrowBar share={total ? n / total : 0} color={color} delay={i * 120} />
                </Link>
              );
            })}
          </div>
          {isRegistrar && data.high_risk_awaiting_review > 0 && (
            <p className="mt-5 rounded-md bg-brand-50 px-3 py-2 text-sm text-brand-700">
              <Link to="/review" className="font-medium hover:underline">{data.high_risk_awaiting_review} High-risk scores</Link> are waiting for your review.
            </p>
          )}
          {data.model && (
            <div className="mt-5 flex items-center gap-2 border-t border-slate-100 pt-4 text-xs text-muted">
              {data.model.audit_passed ? <ShieldCheck size={16} className="text-ok" /> : <ShieldX size={16} className="text-danger" />}
              Model #{data.model.id} · AUC {data.model.auc?.toFixed(3)} · fairness gate {data.model.audit_passed ? "passed" : "FAILED"}
            </div>
          )}
        </Card>

        <Card title="Recent escalations" className="lg:col-span-2" actions={<Link to="/escalations" className="text-xs font-medium text-brand-500 hover:underline">View all</Link>}>
          {data.escalations_recent.length === 0 ? <Empty>No open escalations.</Empty> : (
            <ul className="stagger divide-y divide-slate-100">
              {data.escalations_recent.map((e) => (
                <li key={e.id} className="flex gap-3 py-3 text-sm">
                  <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-danger/10 text-danger"><AlertTriangle size={15} /></span>
                  <div className="min-w-0">
                    <Link to={`/cases/${e.case_id}`} className="font-medium text-brand-500 hover:underline">{e.case_id}</Link>
                    <p className="mt-0.5 text-muted">{e.note}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
