import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ClipboardList, Flame, FolderOpen, Info, ShieldCheck, ShieldX } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Card, DelayBadge, Empty, Loading, Logo, Stat, fmtDate, useFetch } from "../components/ui";
import { getLang, t, tBodies } from "../i18n";

interface Dash {
  pending: number;
  in_remand: number;
  risk_counts: { High: number; Medium: number; Low: number };
  high_controllable: number;
  overdue: number;
  high_risk_awaiting_review: number;
  open_cycle: { id: string; week_start: string; awaiting_decision: number } | null;
  escalations_open: number;
  escalations_recent: { id: number; case_id: string; cycle_id: string; note: string; consecutive_high_cycles: number;
                        delay_status: string | null; responsible: string }[];
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
  return t(h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening");
}

/** Bar that grows from zero after mount. */
function GrowBar({ share, color, delay }: { share: number; color: string; delay: number }) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const id = setTimeout(() => setW(share), 80 + delay);
    return () => clearTimeout(id);
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
  const today = new Date().toLocaleDateString(getLang() === "sw" ? "sw-TZ" : "en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <>
      <section className="gradient-pan relative mb-6 overflow-hidden rounded-md bg-linear-to-br from-brand-900 via-[#34507a] to-brand-500 px-6 py-6 text-white shadow-lg shadow-brand-900/20 animate-scale-in md:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-16 h-56 w-56 rounded-full bg-white/10 blur-2xl animate-float" />
        <div className="relative flex items-center justify-between gap-6">
          <div className="min-w-0">
            <p className="text-sm text-white/70 animate-fade-up">{today}</p>
            <h1 className="mt-1 text-2xl font-medium text-white animate-fade-up [animation-delay:80ms]">{greeting()}, {t(user?.full_name.split(" (")[0] ?? "")}</h1>
            <p className="mt-2 max-w-xl text-sm text-white/80 animate-fade-up [animation-delay:160ms]">
              {data.open_cycle
                ? t("{n} cause-list listings await a decision for the week of {date}.", { n: data.open_cycle.awaiting_decision, date: fmtDate(data.open_cycle.week_start) })
                : t("No cause list is waiting for approval.")}
              {" "}{t("{n} pending cases are rated High risk.", { n: data.risk_counts.High })}
            </p>
          </div>
          <Logo size={88} motion="intro" className="hidden shrink-0 drop-shadow-xl sm:block" />
        </div>
        <DriftingWaves />
      </section>
      {data.model && !data.model.audit_passed && (
        <div className="mb-6"><Alert tone="error">{t("The latest model failed the fairness audit. Scoring and scheduling are blocked until it is retrained and passes.")}</Alert></div>
      )}
      <div className="stagger grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat icon={FolderOpen} iconMotion="ic-rise" label={t("Pending cases")} value={data.pending}
          hint={t("{a} past target, {b} accused in remand", { a: data.overdue, b: data.in_remand })} to="/cases" />
        <Stat icon={Flame} iconMotion="ic-pulse" tone="danger" label={t("High risk")} value={data.risk_counts.High} hint={t("{n} court-controllable", { n: data.high_controllable })} to="/cases?risk=High" />
        <Stat icon={ClipboardList} iconMotion="ic-check" tone="warn" label={t("Awaiting approval")} value={data.open_cycle?.awaiting_decision ?? 0}
          hint={data.open_cycle ? t("Week of {date}", { date: fmtDate(data.open_cycle.week_start) }) : t("No open cause list")}
          to={data.open_cycle ? `/cause-list/${data.open_cycle.id}` : "/cause-list"} />
        <Stat icon={AlertTriangle} iconMotion="ic-wiggle" tone={data.escalations_open ? "danger" : "ok"} label={t("Open escalations")} value={data.escalations_open} hint={t("High risk, no registrar action")} to="/escalations" />
      </div>

      <div className="mt-4 flex items-start gap-2 rounded-md border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-700">
        <Info size={16} className="mt-0.5 shrink-0" />
        <p>{t("Judiciary 2025: 5% of pending cases are backlog, and 84.5% of that backlog is at the Court of Appeal. JusticeFlow's job is to keep courts on target and flag overruns early.")}</p>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title={t("Risk distribution, pending cases")}>
          <div className="space-y-4">
            {(["High", "Medium", "Low"] as const).map((k, i) => {
              const n = data.risk_counts[k];
              const color = { High: "bg-danger", Medium: "bg-warn", Low: "bg-ok" }[k];
              return (
                <Link key={k} to={`/cases?risk=${k}`} className="group block">
                  <div className="flex justify-between text-sm">
                    <span className="text-ink transition group-hover:text-brand-600">{t(k)}</span>
                    <span className="tabular-nums text-muted">{n} ({total ? Math.round((n / total) * 100) : 0}%)</span>
                  </div>
                  <GrowBar share={total ? n / total : 0} color={color} delay={i * 120} />
                </Link>
              );
            })}
          </div>
          {isRegistrar && data.high_risk_awaiting_review > 0 && (
            <p className="mt-5 rounded-md bg-brand-50 px-3 py-2 text-sm text-brand-700">
              <Link to="/review" className="font-medium hover:underline">{t("{n} High-risk scores", { n: data.high_risk_awaiting_review })}</Link> {t("are waiting for your review.")}
            </p>
          )}
          {data.model && (
            <div className="mt-5 flex items-center gap-2 border-t border-slate-100 pt-4 text-xs text-muted">
              {data.model.audit_passed ? <ShieldCheck size={16} className="text-ok" /> : <ShieldX size={16} className="text-danger" />}
              {t("Model #{id}, AUC {auc} on synthetic data, fairness gate {state}", { id: data.model.id, auc: data.model.auc?.toFixed(3), state: t(data.model.audit_passed ? "passed" : "FAILED") })}
            </div>
          )}
        </Card>

        <Card title={t("Recent escalations")} className="lg:col-span-2" actions={<Link to="/escalations" className="text-xs font-medium text-brand-600 hover:underline">{t("View all")}</Link>}>
          {data.escalations_recent.length === 0 ? <Empty>{t("No open escalations.")}</Empty> : (
            <ul className="stagger divide-y divide-slate-100">
              {data.escalations_recent.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2.5 text-sm">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-danger/10 text-danger"><AlertTriangle size={14} /></span>
                  <Link to={`/cases/${e.case_id}`} className="font-medium text-brand-600 hover:underline">{e.case_id}</Link>
                  <span className="text-muted">{t("High risk for {n} weeks, no registrar action", { n: e.consecutive_high_cycles })}</span>
                  {e.delay_status && <span className="ml-auto max-w-full"><DelayBadge status={e.delay_status} /></span>}
                  {e.responsible && <span className="w-full pl-10 text-xs text-slate-500">{t("For")}: {tBodies(e.responsible)}</span>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
