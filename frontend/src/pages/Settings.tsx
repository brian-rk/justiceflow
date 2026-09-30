import { useEffect, useState } from "react";
import { api } from "../api";
import { ROLE_LABEL } from "../auth";
import { Alert, Button, Card, Field, Loading, Modal, PageHeader, inputCls, td, th, useFetch } from "../components/ui";
import type { Magistrate, Role, User } from "../types";
import { FadeSwap, Tabs, useToast } from "../components/motion";

interface SettingsData {
  disposition_targets: Record<string, number>;
  escalation_cycles: number;
  fpr_gap_threshold: number;
  external_block_penalty: number;
  nao_benchmark_months: number;
}

export default function Settings() {
  const [tab, setTab] = useState<"system" | "roster" | "users">("system");
  return (
    <>
      <PageHeader title="Settings" subtitle="Disposition targets, the magistrate roster and courtroom capacity, and user accounts." />
      <Tabs value={tab} onChange={setTab} tabs={[["system", "Targets & thresholds"], ["roster", "Magistrate roster"], ["users", "Users & roles"]] as const} />
      <FadeSwap k={tab}>
        {tab === "system" && <SystemSettings />}
        {tab === "roster" && <Roster />}
        {tab === "users" && <Users />}
      </FadeSwap>
    </>
  );
}

function SystemSettings() {
  const { data, error } = useFetch(() => api.get<SettingsData>("/settings"));
  const [form, setForm] = useState<SettingsData | null>(null);
  const toast = useToast();
  useEffect(() => { if (data) setForm(data); }, [data]);
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!form) return <Loading />;

  const save = async () => {
    try {
      const res = await api.put<SettingsData & { note?: string }>("/settings", form);
      toast.success("Settings saved.");
      if (res.note) toast.info(res.note);
    } catch (e) { toast.error((e as Error).message); }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Disposition targets (months before a case counts as backlog)">
        <div className="grid grid-cols-2 gap-4">
          {Object.entries(form.disposition_targets).map(([level, months]) => (
            <Field key={level} label={level}>
              <input type="number" min={1} max={120} className={inputCls} value={months}
                onChange={(e) => setForm({ ...form, disposition_targets: { ...form.disposition_targets, [level]: Number(e.target.value) } })} />
            </Field>
          ))}
        </div>
        <p className="mt-3 text-xs text-slate-500">Changing targets requires retraining the model (Fairness audit → Retrain).</p>
      </Card>
      <Card title="Thresholds">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Escalate after N High cycles"><input type="number" min={2} max={10} className={inputCls} value={form.escalation_cycles} onChange={(e) => setForm({ ...form, escalation_cycles: Number(e.target.value) })} /></Field>
          <Field label="Fairness gap threshold" hint="0.10 = 10 points"><input type="number" step={0.01} min={0.01} max={0.5} className={inputCls} value={form.fpr_gap_threshold} onChange={(e) => setForm({ ...form, fpr_gap_threshold: Number(e.target.value) })} /></Field>
          <Field label="Externally-blocked priority weight" hint="1 = no deprioritisation"><input type="number" step={0.05} min={0} max={1} className={inputCls} value={form.external_block_penalty} onChange={(e) => setForm({ ...form, external_block_penalty: Number(e.target.value) })} /></Field>
          <Field label="NAO benchmark (months)"><input type="number" min={1} max={60} className={inputCls} value={form.nao_benchmark_months} onChange={(e) => setForm({ ...form, nao_benchmark_months: Number(e.target.value) })} /></Field>
        </div>
      </Card>
      <div className="lg:col-span-2 flex items-center justify-end gap-3">
        <Button variant="primary" onClick={save}>Save settings</Button>
      </div>
    </div>
  );
}

function Roster() {
  const { data, error, reload } = useFetch(() => api.get<Magistrate[]>("/magistrates"));
  const [edit, setEdit] = useState<Magistrate | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const toast = useToast();
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;

  const save = async (m: Magistrate) => {
    try {
      await api.patch(`/magistrates/${m.id}`, { full_name: m.full_name, daily_capacity: m.daily_capacity, unavailable_days: m.unavailable_days, active: m.active });
      setEdit(null);
      toast.success(`${m.full_name} updated.`);
      reload();
    } catch (e) { setMsg((e as Error).message); }
  };

  return (
    <Card title={`Magistrate roster (${data.length})`}>
      <div className="max-h-[60vh] overflow-auto">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-white"><tr><th className={th}>Magistrate</th><th className={th}>Station</th><th className={th}>Level</th><th className={th + " text-right"}>Cases / day</th><th className={th}>Not sitting</th><th className={th + " text-right"}>Pending</th><th className={th}></th></tr></thead>
          <tbody className="stagger-rows row-accent divide-y divide-slate-100">
            {data.map((m) => (
              <tr key={m.id} className={m.active ? "" : "text-slate-400"}>
                <td className={td}>{m.full_name}<div className="text-xs text-slate-500">{m.id}</div></td>
                <td className={td}>{m.court_station}</td><td className={td}>{m.court_level}</td>
                <td className={td + " text-right tabular-nums"}>{m.daily_capacity}</td>
                <td className={td}>{m.unavailable_days || "—"}</td>
                <td className={td + " text-right tabular-nums"}>{m.pending_cases}</td>
                <td className={td}><Button className="px-2 py-1 text-xs" onClick={() => { setEdit({ ...m }); setMsg(null); }}>Edit</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {edit && (
        <Modal title={`Edit ${edit.id}`} open onClose={() => setEdit(null)}>
          <div className="space-y-4">
            {msg && <Alert tone="error">{msg}</Alert>}
            <Field label="Name"><input className={inputCls} value={edit.full_name} onChange={(e) => setEdit({ ...edit, full_name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Courtroom slots per day"><input type="number" min={1} max={40} className={inputCls} value={edit.daily_capacity} onChange={(e) => setEdit({ ...edit, daily_capacity: Number(e.target.value) })} /></Field>
              <Field label="Not sitting on" hint="e.g. Mon,Fri"><input className={inputCls} value={edit.unavailable_days} onChange={(e) => setEdit({ ...edit, unavailable_days: e.target.value })} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} className="accent-brand-600" /> Active on the roster</label>
            <div className="flex justify-end gap-2"><Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" onClick={() => save(edit)}>Save</Button></div>
          </div>
        </Modal>
      )}
    </Card>
  );
}

function Users() {
  const { data, error, reload } = useFetch(() => api.get<User[]>("/users"));
  const mags = useFetch(() => api.get<Magistrate[]>("/magistrates"));
  const blank = { username: "", full_name: "", role: "clerk" as Role, password: "", magistrate_id: "" };
  const [form, setForm] = useState(blank);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Loading />;

  const create = async () => {
    try {
      await api.post("/users", { ...form, magistrate_id: form.role === "magistrate" ? form.magistrate_id : null });
      setForm(blank);
      setMsg({ tone: "success", text: "User created." });
      reload();
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  };
  const toggle = async (u: User) => {
    try { await api.patch(`/users/${u.id}`, { active: !u.active }); reload(); }
    catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="Accounts" className="lg:col-span-2">
        <table className="min-w-full text-sm">
          <thead><tr><th className={th}>User</th><th className={th}>Role</th><th className={th}>Linked magistrate</th><th className={th}></th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((u) => (
              <tr key={u.id} className={u.active ? "" : "text-slate-400"}>
                <td className={td}>{u.full_name}<div className="text-xs text-slate-500">{u.username}</div></td>
                <td className={td}>{ROLE_LABEL[u.role]}</td>
                <td className={td}>{u.magistrate_id ?? "—"}</td>
                <td className={td}><Button className="px-2 py-1 text-xs" onClick={() => toggle(u)}>{u.active ? "Deactivate" : "Reactivate"}</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title="Add a user">
        <div className="space-y-3">
          {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
          <Field label="Full name"><input className={inputCls} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
          <Field label="Username"><input className={inputCls} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></Field>
          <Field label="Role">
            <select className={inputCls} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
          </Field>
          {form.role === "magistrate" && (
            <Field label="Magistrate on roster">
              <select className={inputCls} value={form.magistrate_id} onChange={(e) => setForm({ ...form, magistrate_id: e.target.value })}>
                <option value="">Select…</option>
                {(mags.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
              </select>
            </Field>
          )}
          <Field label="Initial password" hint="At least 8 characters"><input type="password" className={inputCls} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
          <p className="text-xs text-slate-500">Clerks record data; registrars approve. Keep these roles with different people.</p>
          <Button variant="primary" className="w-full" onClick={create} disabled={!form.username || !form.full_name || form.password.length < 8}>Create user</Button>
        </div>
      </Card>
    </div>
  );
}
