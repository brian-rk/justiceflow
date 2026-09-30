import { api } from "../api";
import { Alert, Card, DelayBadge, Empty, Loading, PageHeader, RiskBadge, fmtDate, useFetch } from "../components/ui";
import type { Listing } from "../types";

interface Schedule {
  magistrate: { id: string; name: string; court_station: string; court_level: string; unavailable_days: string; daily_capacity: number };
  weeks: { cycle_id: string; week_start: string; listings: Listing[] }[];
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

export default function MySchedule() {
  const { data, error } = useFetch(() => api.get<Schedule>("/my-schedule"));
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;
  const m = data.magistrate;
  return (
    <>
      <PageHeader title="My schedule" subtitle={<>{m.name} · {m.court_level} · {m.court_station}{m.unavailable_days && ` · not sitting ${m.unavailable_days}`} · read-only</>} />
      {data.weeks.length === 0 && <Empty>No approved cause lists yet. Listings appear here once the registrar approves them.</Empty>}
      <div className="space-y-6">
        {data.weeks.map((w) => (
          <Card key={w.cycle_id} title={`Week of ${fmtDate(w.week_start)} · ${w.listings.length} cases`}>
            {w.listings.length === 0 ? <p className="text-sm text-slate-500">No cases listed before you this week.</p> : (
              <div className="stagger grid gap-4 md:grid-cols-5">
                {DAYS.map((d) => {
                  const day = w.listings.filter((l) => l.day === d);
                  return (
                    <div key={d}>
                      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                        {d} {day[0] && <span className="font-normal normal-case">· {fmtDate(day[0].date).slice(0, 6)}</span>}
                      </div>
                      {day.length === 0 ? <p className="text-xs text-slate-400">No sitting</p> : (
                        <ol className="stagger space-y-2">
                          {day.map((l) => (
                            <li key={l.case_id} className="rounded-md border border-slate-200 bg-white p-2.5 text-sm transition duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md">
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-medium">{l.position}. {l.case_id}</span>
                                <RiskBadge category={l.risk_category} />
                              </div>
                              <div className="mt-1"><DelayBadge status={l.delay_status} /></div>
                              <p className="mt-1 text-xs text-slate-600">{l.driving_factors}</p>
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
