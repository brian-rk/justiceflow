import { createContext, useContext, useState, type ReactNode } from "react";
import { SW } from "./i18n.sw";

/** English and Kiswahili. English text is the key; Kiswahili comes from i18n.sw.ts and
 *  falls back to English for anything not yet translated. */
export type Lang = "en" | "sw";
const LANG_KEY = "jf_lang";

function load(): Lang {
  try {
    const v = localStorage.getItem(LANG_KEY);
    if (v === "en" || v === "sw") return v;
  } catch { /* storage unavailable */ }
  return "en";
}

let current: Lang = load();
export const getLang = () => current;

/** Translate an English UI string; {name} placeholders are filled from `vars`. */
export function t(s: string, vars?: Record<string, string | number>): string {
  let out = current === "sw" ? (SW[s] ?? s) : s;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}

/** Plural-aware count: tn(3, "case", "cases") -> "3 cases" / "mashauri 3". */
export function tn(n: number, one: string, many: string) {
  return t(n === 1 ? `{n} ${one}` : `{n} ${many}`, { n: n.toLocaleString() });
}

const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: current, setLang: () => {} });

/** Switching language remounts the app below, so every string is re-rendered. */
export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setState] = useState<Lang>(current);
  const setLang = (l: Lang) => {
    current = l;
    try { localStorage.setItem(LANG_KEY, l); } catch { /* per-viewer nicety only */ }
    document.documentElement.lang = l;
    setState(l);
  };
  document.documentElement.lang = lang;
  return <LangCtx.Provider value={{ lang, setLang }}><div key={lang} className="contents">{children}</div></LangCtx.Provider>;
}

export const useLang = () => useContext(LangCtx);

export function LangToggle({ dark }: { dark?: boolean }) {
  const { lang, setLang } = useLang();
  const btn = (l: Lang, label: string) => (
    <button type="button" onClick={() => setLang(l)} aria-pressed={lang === l}
      className={"rounded px-2 py-1 text-xs font-medium transition " + (lang === l
        ? (dark ? "bg-white text-brand-900" : "bg-brand-600 text-white")
        : (dark ? "text-white/85 hover:bg-white/15" : "text-muted hover:bg-slate-100 hover:text-ink"))}>
      {label}
    </button>
  );
  return (
    <div role="group" aria-label="Language / Lugha" className={"inline-flex gap-0.5 rounded-md p-0.5 " + (dark ? "bg-white/10 ring-1 ring-white/25" : "ring-1 ring-slate-200")}>
      {btn("en", "EN")}{btn("sw", "SW")}
    </div>
  );
}

// --- labels that come from the backend ---------------------------------------------

/** "Court-controllable" / "Externally blocked: a; b" */
export function tDelay(status: string) {
  if (!status.startsWith("Externally blocked: ")) return t(status);
  return t("Blocked") + ": " + status.replace("Externally blocked: ", "").split("; ").map((x) => t(x)).join("; ");
}

/** Who can unblock a case: "a; b" */
export function tBodies(s: string) {
  return s.split("; ").map((x) => t(x)).join("; ");
}

/** The model's driving-factor labels (see FEATURE_LABELS in justiceflow/model.py). */
export function tFactor(label: string) {
  if (current === "en") return label;
  const rules: [RegExp, (m: RegExpMatchArray) => string][] = [
    [/^Case type: (.+)$/, (m) => `Aina ya shauri: ${t(m[1])}`],
    [/^Court level: (.+)$/, (m) => `Ngazi ya mahakama: ${t(m[1])}`],
    [/^Offence: (.+)$/, (m) => `Kosa: ${t(m[1])}`],
    [/^(\d+) parties$/, (m) => `Wadaawa ${m[1]}`],
    [/^(\d+)% of disposition target elapsed$/, (m) => `${m[1]}% ya muda wa lengo umepita`],
    [/^(\d+) hearings held$/, (m) => `Vikao ${m[1]} vimefanyika`],
    [/^(\d+) adjournments$/, (m) => `Kuahirishwa mara ${m[1]}`],
    [/^(\d+) court-side adjournments$/, (m) => `Kuahirishwa na mahakama mara ${m[1]}`],
  ];
  for (const [re, fn] of rules) {
    const m = label.match(re);
    if (m) return fn(m);
  }
  return t(label);
}

/** Reasons returned with a next-date suggestion (services.suggest_next_date). */
export function tReason(r: string) {
  if (current === "en") return r;
  const rules: [RegExp, (m: RegExpMatchArray) => string][] = [
    [/^(High|Medium|Low) risk: relist within (\d+) to (\d+) days$/, (m) => `Hatari ${t(m[1]).toLowerCase()}: rudisha ndani ya siku ${m[2]} hadi ${m[3]}`],
    [/^Waiting for a forensic report: Government Chemist results take (\d+) days on average \(NAO 2022\)$/,
      (m) => `Inasubiri ripoti ya kitaalamu: majibu ya Mkemia Mkuu wa Serikali huchukua wastani wa siku ${m[1]} (NAO 2022)`],
    [/^Waiting for the record of proceedings: allow about (\d+) days$/, (m) => `Inasubiri kumbukumbu za mwenendo wa shauri: ruhusu takriban siku ${m[1]}`],
    [/^Investigation or prosecution delay: a short date \((\d+) days\) to check progress$/, (m) => `Ucheleweshaji wa upelelezi au mashtaka: tarehe fupi (siku ${m[1]}) kufuatilia maendeleo`],
    [/^Witness did not attend: time to serve a summons \(14 to 28 days\)$/, () => "Shahidi hakufika: muda wa kutoa hati ya wito (siku 14 hadi 28)"],
    [/^Accused in remand: bring back within (\d+) days$/, (m) => `Mshtakiwa yuko rumande: arudishwe ndani ya siku ${m[1]}`],
    [/^Every day in the window is fully booked; this is the earliest working day$/, () => "Kila siku katika kipindi hiki imejaa; hii ndiyo siku ya kazi ya mapema zaidi"],
    [/^The bench is full earlier in the window, so this is the first day with room$/, () => "Ratiba imejaa mapema, kwa hiyo hii ndiyo siku ya kwanza yenye nafasi"],
    [/^(.+) has (\d+) of (\d+) slots booked that day$/, (m) => `${m[1]} ana mashauri ${m[2]} kati ya nafasi ${m[3]} siku hiyo`],
    [/^The case is concluded: no next date\.$/, () => "Shauri limehitimishwa: hakuna tarehe ijayo."],
  ];
  for (const [re, fn] of rules) {
    const m = r.match(re);
    if (m) return fn(m);
  }
  return r;
}
