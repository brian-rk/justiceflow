import { useState } from "react";
import { Link } from "react-router-dom";
import { Printer } from "lucide-react";
import { api } from "../api";
import { Alert, Button, Card, Empty, Loading, PageHeader, fmtDate, fmtDays, inputInline, useFetch } from "../components/ui";
import { t, tDelay } from "../i18n";
import type { Esc } from "./Escalations";

interface AgendaData {
  station: string | null;
  date: string;
  total: number;
  stations: string[];
  groups: { responsible: string; items: Esc[] }[];
}

/** One page per committee meeting: the open escalations, grouped by the body that can act. */
export default function Agenda() {
  const [station, setStation] = useState("");
  const { data, error } = useFetch(() => api.get<AgendaData>("/escalations/agenda", { station: station || null }), [station]);
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;

  return (
    <>
      <div className="print:hidden">
        <PageHeader title={t("Committee agenda")}
          subtitle={t("Open escalations for the case-flow committee, grouped by who can unblock them. Print it for the meeting.")}
          actions={<>
            <select aria-label={t("Station")} className={inputInline} value={station} onChange={(e) => setStation(e.target.value)}>
              <option value="">{t("All stations")}</option>
              {data.stations.map((s) => <option key={s}>{s}</option>)}
            </select>
            <Button variant="primary" onClick={() => window.print()}><Printer size={16} /> {t("Print")}</Button>
          </>} />
      </div>
      <Card>
        <div className="mb-4 border-b border-slate-200 pb-3">
          <h2 className="text-lg font-medium text-ink">{t("Case-flow committee: delayed cases")}</h2>
          <p className="text-sm text-muted">
            {station || t("All stations")}. {t("Prepared {date}", { date: fmtDate(data.date) })}. {t("{n} cases", { n: data.total })}.
          </p>
        </div>
        {data.groups.length === 0 ? <Empty>{t("No open escalations.")}</Empty> : data.groups.map((g) => (
          <section key={g.responsible} className="mb-6 break-inside-avoid">
            <h3 className="mb-2 font-medium text-ink">{t(g.responsible)} <span className="text-sm font-normal text-muted">({g.items.length})</span></h3>
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs text-muted">
                  <th className="py-1.5 pr-3 font-medium">{t("Case")}</th><th className="py-1.5 pr-3 font-medium">{t("Court")}</th>
                  <th className="py-1.5 pr-3 font-medium">{t("Pending")}</th><th className="py-1.5 pr-3 font-medium">{t("Blocked by")}</th>
                  <th className="py-1.5 font-medium">{t("Action agreed")}</th>
                </tr>
              </thead>
              <tbody>
                {g.items.map((e) => (
                  <tr key={e.id} className="border-b border-slate-100 align-top">
                    <td className="py-2 pr-3"><Link to={`/cases/${e.case_id}`} className="font-medium text-brand-600 hover:underline print:text-ink">{e.case_id}</Link>
                      {e.in_custody && <div className="text-xs text-[#5b3d8a]">{t("In remand")}</div>}</td>
                    <td className="py-2 pr-3">{t(e.case_type)}, {t(e.court_level)}, {e.court_station}</td>
                    <td className="whitespace-nowrap py-2 pr-3 tabular-nums">{fmtDays(e.days_pending)}</td>
                    <td className="py-2 pr-3 text-slate-600">{e.delay_status ? tDelay(e.delay_status) : "—"}</td>
                    <td className="w-48 py-2"><div className="h-8 border-b border-dashed border-slate-300" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}
      </Card>
    </>
  );
}
