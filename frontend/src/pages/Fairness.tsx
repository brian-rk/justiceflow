import { useState } from "react";
import { api } from "../api";
import { Alert, Button, Card, Loading, PageHeader, fmtDate, pct, td, th, useFetch } from "../components/ui";
import { GrowBar, useToast } from "../components/motion";
import { t } from "../i18n";

interface Run {
  id: number; trained_at: string; as_of: string; metrics: { auc: number; brier: number; n: number; positive_rate: number };
  audit_passed: boolean; audit_max_gap: number; audit_threshold: number; audit_rounds: number[];
  audit_table: { region: string; negatives: number; raw_fpr: number; adjusted_fpr: number; fairlearn_fpr?: number; gated: boolean }[];
}
interface FairnessData {
  cleared_for_real_data: boolean;
  latest: Run | null;
  history: { id: number; trained_at: string; audit_passed: boolean; audit_max_gap: number; auc: number }[];
}

export default function Fairness() {
  const { data, error, reload } = useFetch(() => api.get<FairnessData>("/fairness"));
  const [training, setTraining] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const toast = useToast();

  const train = async () => {
    setTraining(true);
    setMsg(null);
    try {
      const r = await api.post<Run>("/model/train");
      setMsg({ tone: r.audit_passed ? "success" : "error", text: t(r.audit_passed ? "Model #{id} trained. Fairness gate passed." : "Model #{id} trained. Fairness gate FAILED: scoring and scheduling are blocked.", { id: r.id }) });
      if (r.audit_passed) toast.success(t("Model #{id} passed the fairness gate.", { id: r.id }));
      else toast.error(t("Model #{id} failed the fairness gate.", { id: r.id }));
      reload();
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
    finally { setTraining(false); }
  };

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;
  const r = data.latest;
  const maxFpr = Math.max(0.01, ...(r?.audit_table.map((x) => x.adjusted_fpr) ?? [0]));

  return (
    <>
      <PageHeader title={t("Fairness audit")} subtitle={t("False-positive 'High risk' rates by region for otherwise similar cases (same case type and court level).")}
        actions={<Button variant="primary" onClick={train} disabled={training}>{training ? t("Training (about 30 s)…") : t("Retrain & re-audit")}</Button>} />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {!r ? <Alert tone="info">{t("No model has been trained yet.")}</Alert> : (
        <>
          <div className="mb-6">
            {data.cleared_for_real_data
              ? <Alert tone="success"><b>{t("Cleared for real-data use.")}</b> {t("Widest adjusted gap between regions is {a}, within the {b} threshold.", { a: pct(r.audit_max_gap, 1), b: pct(r.audit_threshold) })}</Alert>
              : <Alert tone="error"><b>{t("Not cleared.")}</b> {t("Widest gap {a} exceeds {b}. Real-data scoring and scheduling are blocked until the model is reweighted and passes.", { a: pct(r.audit_max_gap, 1), b: pct(r.audit_threshold) })}</Alert>}
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            <Card title={t("Model #{id} by region", { id: r.id })} className="lg:col-span-2">
              <table className="min-w-full text-sm">
                <thead><tr><th className={th}>{t("Region")}</th><th className={th + " text-right"}>{t("True negatives")}</th><th className={th + " text-right"}>{t("Raw FPR")}</th><th className={th}>{t("Adjusted FPR")}</th></tr></thead>
                <tbody className="stagger-rows row-accent divide-y divide-slate-100">
                  {r.audit_table.map((g, i) => (
                    <tr key={g.region} className={g.gated ? "" : "text-slate-500"}>
                      <td className={td}>{g.region}{!g.gated && <span className="ml-1 text-xs">({t("too few cases to gate")})</span>}</td>
                      <td className={td + " text-right tabular-nums"}>{g.negatives}</td>
                      <td className={td + " text-right tabular-nums"}>{pct(g.raw_fpr, 1)}</td>
                      <td className={td}>
                        <div className="flex items-center gap-2">
                          <div className="w-40"><GrowBar share={g.adjusted_fpr / maxFpr} delay={i * 70} /></div>
                          <span className="tabular-nums">{pct(g.adjusted_fpr, 1)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-3 text-xs text-slate-500">
                {t("Region and court station are never model inputs. The gate compares each region's wrong \"High\" flags with the rate for cases of the same type and court level.")}{" "}
                {t("Reweighting rounds this run: {n} (gap per round: {g}).", { n: r.audit_rounds.length, g: r.audit_rounds.map((x) => pct(x, 1)).join(" → ") })}
              </p>
            </Card>
            <Card title={t("Model quality (holdout)")}>
              <dl className="grid grid-cols-2 gap-y-3 text-sm">
                <dt className="text-slate-500">AUC</dt><dd className="tabular-nums">{r.metrics.auc.toFixed(3)}</dd>
                <dt className="text-slate-500">{t("Brier score")}</dt><dd className="tabular-nums">{r.metrics.brier.toFixed(3)}</dd>
                <dt className="text-slate-500">{t("Snapshots")}</dt><dd className="tabular-nums">{r.metrics.n.toLocaleString()}</dd>
                <dt className="text-slate-500">{t("Backlog rate")}</dt><dd className="tabular-nums">{pct(r.metrics.positive_rate, 1)}</dd>
                <dt className="text-slate-500">{t("Trained")}</dt><dd>{fmtDate(r.trained_at)}</dd>
              </dl>
              <p className="mt-3 text-xs text-slate-500">{t("Measured on synthetic data. Most overruns in the 2025 picture are at the Court of Appeal, so the court level alone predicts much of this. See the real-case test in data/validation.")}</p>
            </Card>
          </div>
          <Card title={t("Audit history")} className="mt-6">
            <table className="min-w-full text-sm">
              <thead><tr><th className={th}>{t("Model")}</th><th className={th}>{t("Trained")}</th><th className={th}>{t("Gate")}</th><th className={th + " text-right"}>{t("Max gap")}</th><th className={th + " text-right"}>AUC</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.history.map((h) => (
                  <tr key={h.id}>
                    <td className={td}>#{h.id}</td><td className={td}>{fmtDate(h.trained_at)}</td>
                    <td className={td}><span className={h.audit_passed ? "text-brand-600" : "font-medium text-red-700"}>{t(h.audit_passed ? "Passed" : "Failed")}</span></td>
                    <td className={td + " text-right tabular-nums"}>{pct(h.audit_max_gap, 1)}</td>
                    <td className={td + " text-right tabular-nums"}>{h.auc?.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </>
  );
}
