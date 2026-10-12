import { api } from "../api";
import { Alert, Card, DelayBadge, Empty, FactorKey, Factors, Loading, PageHeader, RemandBadge, RiskBadge, fmtDate, fmtDay, useFetch } from "../components/ui";
import type { Listing, SessionPlan } from "../types";
import { t, tn } from "../i18n";

interface Schedule {
  magistrate: { id: string; name: string; court_station: string; court_level: string; unavailable_days: string; daily_capacity: number };
  weeks: { cycle_id: string; week_start: string; listings: Listing[] }[];
  sessions: SessionPlan[];
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

export default function MySchedule() {
  const { data, error } = useFetch(() => api.get<Schedule>("/my-schedule"));
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;
  const m = data.magistrate;
  return (
    <>
      <PageHeader title={t("My schedule")} subtitle={<>{m.name}, {t(m.court_level)}, {m.court_station}{m.unavailable_days && `. ${t("Not sitting on {d}", { d: m.unavailable_days.split(",").map((d) => t(d)).join(", ") })}`}. {t("Read-only.")}</>} />
      {data.sessions.map((p) => (
        <Card key={p.id} className="mb-6" title={t("Criminal session at {s}, from {date}", { s: p.court_station, date: fmtDate(p.start_date) })}
          actions={<span className="text-sm text-muted">{tn(p.cases.length, "trial", "trials")}</span>}>
          <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {p.cases.map((c) => (
              <li key={c.case_id} className="rounded-md border border-slate-200 p-2.5 text-sm">
                <div className="flex items-center justify-between gap-2"><span className="font-medium">{c.case_id}</span><span className="text-xs text-slate-500">{fmtDate(c.planned_date)}</span></div>
                <div className="mt-1 flex flex-wrap gap-1">{c.in_custody && <RemandBadge days={c.days_pending} />}{c.delay_status && <DelayBadge status={c.delay_status} />}</div>
              </li>
            ))}
          </ol>
        </Card>
      ))}
      {data.weeks.length === 0 && <Empty>{t("No approved cause lists yet. Listings appear here once the registrar approves them.")}</Empty>}
      {data.weeks.length > 0 && <div className="mb-3 flex justify-end"><FactorKey /></div>}
      <div className="space-y-6">
        {data.weeks.map((w) => (
          <Card key={w.cycle_id} title={t("Week of {date}", { date: fmtDate(w.week_start) })}
            actions={<span className="text-sm text-muted">{tn(w.listings.length, "case", "cases")}</span>}>
            {w.listings.length === 0 ? <p className="text-sm text-slate-500">{t("No cases listed before you this week.")}</p> : (
              <div className="stagger grid gap-4 md:grid-cols-5">
                {DAYS.map((d) => {
                  const day = w.listings.filter((l) => l.day === d);
                  return (
                    <div key={d}>
                      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                        {t(d)} {day[0] && <span className="ml-1 font-normal normal-case">{fmtDay(day[0].date)}</span>}
                      </div>
                      {day.length === 0 ? <p className="text-xs text-slate-500">{t("No sitting")}</p> : (
                        <ol className="stagger space-y-2">
                          {day.map((l) => (
                            <li key={l.case_id} className="rounded-md border border-slate-200 bg-white p-2.5 text-sm transition duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md">
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-medium">{l.position}. {l.case_id}</span>
                                <RiskBadge category={l.risk_category} />
                              </div>
                              <div className="mt-1 flex flex-wrap gap-1"><DelayBadge status={l.delay_status} />{l.in_custody && <RemandBadge />}</div>
                              <Factors className="mt-1.5" text={l.driving_factors} daysOverdue={l.days_overdue} />
                            </li>
                          ))}
                        </ol>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        ))}
      </div>
    </>
  );
}
