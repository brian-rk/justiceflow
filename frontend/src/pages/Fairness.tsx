import { useState } from "react";
import { api } from "../api";
import { Alert, Button, Card, Loading, PageHeader, fmtDate, pct, td, th, useFetch } from "../components/ui";
import { GrowBar, useToast } from "../components/motion";

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
      setMsg({ tone: r.audit_passed ? "success" : "error", text: `Model #${r.id} trained. Fairness gate ${r.audit_passed ? "passed" : "FAILED: scoring and scheduling are blocked"}.` });
      if (r.audit_passed) toast.success(`Model #${r.id} passed the fairness gate.`);
      else toast.error(`Model #${r.id} failed the fairness gate.`);
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
      <PageHeader title="Fairness audit" subtitle="False-positive 'High risk' rates by region for otherwise similar cases (same case type and court level)."
        actions={<Button variant="primary" onClick={train} disabled={training}>{training ? "Training (about 30 s)…" : "Retrain & re-audit"}</Button>} />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {!r ? <Alert tone="info">No model has been trained yet.</Alert> : (
        <>
          <div className="mb-6">
            {data.cleared_for_real_data
              ? <Alert tone="success"><b>Cleared for real-data use.</b> Widest adjusted gap between regions is {pct(r.audit_max_gap, 1)}, within the {pct(r.audit_threshold)} threshold.</Alert>
              : <Alert tone="error"><b>Not cleared.</b> Widest gap {pct(r.audit_max_gap, 1)} exceeds {pct(r.audit_threshold)}. Real-data scoring and scheduling are blocked until the model is reweighted and passes.</Alert>}
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            <Card title={`Model #${r.id} · by region`} className="lg:col-span-2">
              <table className="min-w-full text-sm">
                <thead><tr><th className={th}>Region</th><th className={th + " text-right"}>True negatives</th><th className={th + " text-right"}>Raw FPR</th><th className={th}>Adjusted FPR</th></tr></thead>
                <tbody className="stagger-rows row-accent divide-y divide-slate-100">
                  {r.audit_table.map((g, i) => (
                    <tr key={g.region} className={g.gated ? "" : "text-slate-400"}>
                      <td className={td}>{g.region}{!g.gated && <span className="ml-1 text-xs">(too few cases to gate)</span>}</td>
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
                Region and court station are never model inputs. The gate compares each region's wrong "High" flags with the rate for cases of the same type and court level.
                Reweighting rounds this run: {r.audit_rounds.length} (gap per round: {r.audit_rounds.map((x) => pct(x, 1)).join(" → ")}).
              </p>
            </Card>
            <Card title="Model quality (holdout)">
              <dl className="grid grid-cols-2 gap-y-3 text-sm">
                <dt className="text-slate-500">AUC</dt><dd className="tabular-nums">{r.metrics.auc.toFixed(3)}</dd>
                <dt className="text-slate-500">Brier score</dt><dd className="tabular-nums">{r.metrics.brier.toFixed(3)}</dd>
                <dt className="text-slate-500">Snapshots</dt><dd className="tabular-nums">{r.metrics.n.toLocaleString()}</dd>
                <dt className="text-slate-500">Backlog rate</dt><dd className="tabular-nums">{pct(r.metrics.positive_rate, 1)}</dd>
                <dt className="text-slate-500">Trained</dt><dd>{fmtDate(r.trained_at)}</dd>
              </dl>
            </Card>
          </div>
          <Card title="Audit history" className="mt-6">
            <table className="min-w-full text-sm">
              <thead><tr><th className={th}>Model</th><th className={th}>Trained</th><th className={th}>Gate</th><th className={th + " text-right"}>Max gap</th><th className={th + " text-right"}>AUC</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.history.map((h) => (
                  <tr key={h.id}>
                    <td className={td}>#{h.id}</td><td className={td}>{fmtDate(h.trained_at)}</td>
                    <td className={td}><span className={h.audit_passed ? "text-brand-600" : "font-medium text-red-700"}>{h.audit_passed ? "Passed" : "Failed"}</span></td>
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
