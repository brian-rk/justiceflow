import { useCallback, useEffect, useRef, useState, type ButtonHTMLAttributes, type ComponentType, type PointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, ChevronRight, ChevronUp, ChevronsDown, ChevronsUp, Inbox, Minus, X } from "lucide-react";
import type { RiskCategory } from "../types";
import { getLang, t, tDelay, tFactor } from "../i18n";

/** Fetch on mount / when deps change; `reload` refetches. */
export function useFetch<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps);
  const reload = useCallback(() => {
    setLoading(true);
    return run()
      .then((d) => { setData(d); setError(null); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [run]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Animates a number from 0 to `value` once on mount (and on change). */
export function useCountUp(value: number, ms = 700) {
  const [shown, setShown] = useState(reducedMotion() ? value : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reducedMotion()) { setShown(value); return; }
    const start = performance.now();
    const origin = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      const eased = 1 - Math.pow(1 - k, 4);
      setShown(Math.round(origin + (value - origin) * eased));
      if (k < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return shown;
}

/** Adds `.in` to the element once it scrolls into view (for `.reveal`). */
export function useReveal<T extends HTMLElement>(enabled = true) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return;
    if (reducedMotion() || typeof IntersectionObserver === "undefined") { el.classList.add("in"); return; }
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    // threshold 0: a card taller than the screen can never be 8% visible, so it would never appear.
    }, { threshold: 0, rootMargin: "0px 0px -40px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [enabled]);
  return ref;
}

/** Tracks the cursor position as --mx / --my for the `.spotlight` effect. */
export function trackSpotlight(e: PointerEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect();
  e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
  e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
}

// --- brand -------------------------------------------------------------------

/** JusticeFlow's own emblem: scales of justice inside a ring.
 *  motion="intro" draws the strokes then swings the pans; "hover" swings on hover. */
export function Logo({ size = 64, className, motion = "hover" }: { size?: number; className?: string; motion?: "intro" | "hover" | "none" }) {
  const cls = motion === "intro" ? "logo-draw logo-swing" : motion === "hover" ? "logo-hover" : "";
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={cx(cls, className)} aria-hidden="true">
      <defs>
        <linearGradient id="jf-ring" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4090cb" />
          <stop offset="1" stopColor="#2b354f" />
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#jf-ring)" />
      <circle cx="32" cy="32" r="25.5" fill="none" stroke="#f9d570" strokeWidth="1.5" opacity=".9" />
      <g stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none">
        <path pathLength={1} d="M32 16v30M24 46h16" />
        <g className="beam">
          <path pathLength={1} d="M20 22h24M20 22l-6 12h12zM44 22l-6 12h12z" />
        </g>
      </g>
      <circle cx="32" cy="16" r="2.4" fill="#f9d570" />
    </svg>
  );
}

// --- layout pieces ---------------------------------------------------------------

const ROUTE_LABEL: Record<string, string> = {
  dashboard: "Dashboard", entry: "Case data entry", review: "Review queue", "cause-list": "Cause list",
  cases: "Case list", "my-schedule": "My schedule", escalations: "Escalations", reports: "Reports",
  fairness: "Fairness audit", settings: "Settings", sessions: "Criminal sessions", agenda: "Committee agenda",
};

export const inputInline = "w-auto rounded-md border border-[#ced4da] bg-white px-3 py-2 text-sm text-ink transition duration-150 focus:border-brand-500 focus:outline-none focus:ring-3 focus:ring-brand-500/15";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  const { pathname } = useLocation();
  const crumbs = pathname.split("/").filter(Boolean).map((c) =>
    ROUTE_LABEL[c] ? t(ROUTE_LABEL[c]) : decodeURIComponent(c));
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-4 animate-fade-in">
      <div>
        <h1 className="text-xl font-medium tracking-tight text-ink">{title}</h1>
        <div className="title-accent mt-1.5" aria-hidden="true" />
        <nav aria-label={t("Breadcrumb")} className="mt-1 flex items-center gap-1 text-xs text-muted">
          <span>JusticeFlow</span>
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1">
              <ChevronRight size={12} className="opacity-60" />
              <span className={i === crumbs.length - 1 ? "text-brand-700" : ""}>{c}</span>
            </span>
          ))}
        </nav>
        {subtitle && <p className="mt-2 max-w-3xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, children, className, actions, still }: { title?: ReactNode; children: ReactNode; className?: string; actions?: ReactNode; still?: boolean }) {
  const ref = useReveal<HTMLElement>(!still);
  return (
    <section ref={ref} className={cx("rounded-md bg-white shadow-[0_0_13px_0_rgba(236,236,241,0.9)] ring-1 ring-slate-900/4 transition-shadow duration-300 hover:shadow-[0_6px_24px_-8px_rgba(43,53,79,0.18)]", !still && "reveal", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
          <h2 className="text-[15px] font-medium text-ink">{title}</h2>
          {actions}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

type Tone = "default" | "danger" | "warn" | "ok" | "info";
const TONE: Record<Tone, { icon: string; text: string }> = {
  default: { icon: "bg-brand-500", text: "text-ink" },
  danger: { icon: "bg-danger", text: "text-danger" },
  warn: { icon: "bg-warn text-ink", text: "text-ink" },
  ok: { icon: "bg-ok", text: "text-ok" },
  info: { icon: "bg-info", text: "text-ink" },
};

export function Stat({ label, value, hint, tone = "default", to, icon: Icon, iconMotion = "ic-rise" }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: Tone; to?: string; icon?: ComponentType<{ size?: number; className?: string }>; iconMotion?: string;
}) {
  const counted = useCountUp(typeof value === "number" ? value : 0);
  const shown = typeof value === "number" ? counted.toLocaleString() : value;
  const t = TONE[tone];
  const body = (
    <div onPointerMove={trackSpotlight}
      className="spotlight shine group flex h-full items-center gap-4 rounded-md bg-white p-5 shadow-[0_0_13px_0_rgba(236,236,241,0.9)] ring-1 ring-slate-900/4 transition duration-300 ease-out hover:-translate-y-1 hover:shadow-xl hover:shadow-slate-300/40">
      {Icon && (
        <div className={cx("relative grid h-12 w-12 shrink-0 place-items-center rounded-md text-white shadow-md transition-transform duration-300 group-hover:scale-105 animate-scale-in", t.icon)}>
          <span className="absolute inset-0 rounded-md bg-white/0 transition group-hover:bg-white/10" />
          <Icon size={22} className={iconMotion} />
        </div>
      )}
      <div className="min-w-0">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
        <div className={cx("mt-1 text-2xl font-medium tabular-nums", t.text)}>{shown}</div>
        {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
      </div>
    </div>
  );
  return to ? <Link to={to} className="block h-full rounded-md focus-visible:outline-2 focus-visible:outline-brand-500">{body}</Link> : body;
}

// --- controls --------------------------------------------------------------------

type BtnVariant = "primary" | "secondary" | "danger" | "ghost" | "success";
export function Button({ variant = "secondary", className, onPointerDown, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant }) {
  const styles: Record<BtnVariant, string> = {
    primary: "shine bg-brand-600 text-white hover:bg-brand-700 border-brand-600 shadow-sm shadow-brand-600/30 hover:shadow-md hover:shadow-brand-600/30",
    success: "bg-ok text-white hover:brightness-95 border-ok shadow-sm shadow-ok/30",
    secondary: "bg-white text-ink hover:bg-slate-50 border-slate-300",
    danger: "bg-white text-danger hover:bg-red-50 border-red-200",
    ghost: "bg-transparent text-muted hover:bg-slate-100 border-transparent",
  };
  const ripple = (e: PointerEvent<HTMLButtonElement>) => {
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2;
    const ink = document.createElement("span");
    ink.className = "ripple-ink";
    ink.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - rect.left - size / 2}px;top:${e.clientY - rect.top - size / 2}px`;
    el.appendChild(ink);
    ink.addEventListener("animationend", () => ink.remove());
    onPointerDown?.(e);
  };
  return (
    <button
      {...props}
      onPointerDown={ripple}
      className={cx("ripple inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md border px-3.5 py-1.5 text-sm font-medium transition duration-150 ease-out active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500", styles[variant], className)}
    />
  );
}

export function RiskBadge({ category, overridden, pulse }: { category: RiskCategory | string | null | undefined; overridden?: boolean; pulse?: boolean }) {
  if (!category) return <span className="text-xs text-slate-500">{t("Unscored")}</span>;
  const s: Record<string, string> = {
    High: "bg-danger/10 text-danger ring-danger/25",
    Medium: "bg-warn/25 text-[#8a6d0b] ring-warn/60",
    Low: "bg-ok/10 text-[#2f8a6f] ring-ok/30",
  };
  return (
    <span className={cx("inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset", s[category])}>
      <span className="relative flex h-1.5 w-1.5">
        {category === "High" && pulse && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60 [animation-duration:1.8s]" />}
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
      </span>
      {t(category)}
      {overridden && <span title={t("Overridden by registrar")}>*</span>}
    </span>
  );
}

export function DelayBadge({ status }: { status: string }) {
  const blocked = status.startsWith("Externally");
  return (
    <span title={tDelay(status)}
      className={cx("inline-flex max-w-full items-center rounded px-2 py-0.5 text-xs font-medium",
        blocked ? "bg-info/10 text-[#0788a0]" : "bg-brand-50 text-brand-700")}>
      <span className="truncate">{tDelay(status)}</span>
    </span>
  );
}

export function Alert({ tone = "info", children }: { tone?: "info" | "error" | "success" | "warn"; children: ReactNode }) {
  const s = {
    info: "border-brand-200 bg-brand-50 text-brand-700",
    error: "border-danger/30 bg-danger/10 text-[#b3293a]",
    success: "border-ok/30 bg-ok/10 text-[#2f8a6f]",
    warn: "border-warn/70 bg-warn/20 text-[#7a5f06]",
  }[tone];
  return <div role={tone === "error" ? "alert" : "status"} className={cx("rounded-md border px-4 py-3 text-sm animate-fade-in", s)}>{children}</div>;
}

/** Skeleton placeholder shaped like a page: header, stat row, table. */
export function Loading({ label }: { label?: string }) {
  return (
    <div aria-busy="true" aria-label={label ?? t("Loading")} className="space-y-4 py-2">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-24" />)}
      </div>
      <div className="rounded-md bg-white p-5">
        {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton mb-3 h-5" style={{ width: `${95 - i * 7}%` }} />)}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-slate-300 bg-slate-50/60 py-10 text-center text-sm text-muted animate-fade-in">
      <Inbox size={30} className="mx-auto mb-3 text-brand-300 animate-float" aria-hidden="true" />
      {children}
    </div>
  );
}

/** Ring that fills to `value` (0..1), coloured by risk category. */
export function RiskRing({ value, category, size = 104 }: { value: number; category: string; size?: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => { const t = setTimeout(() => setShown(value), 120); return () => clearTimeout(t); }, [value]);
  const pctShown = useCountUp(Math.round(value * 100), 1100);
  const r = 42, c = 2 * Math.PI * r;
  const color = { High: "#e74c5e", Medium: "#e0b43c", Low: "#47bd9a" }[category] ?? "#4090cb";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={t("{n}% risk", { n: Math.round(value * 100) })}>
      <svg viewBox="0 0 100 100" className="-rotate-90" width={size} height={size}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="#eef1f5" strokeWidth="9" />
        <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - shown)} className="ring-fill" style={{ filter: `drop-shadow(0 0 4px ${color}55)` }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span className="text-2xl font-medium tabular-nums text-ink">{pctShown}%</span>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-md border border-[#ced4da] bg-white px-3 py-2 text-sm text-ink placeholder:text-slate-500 transition duration-150 focus:border-brand-500 focus:outline-none focus:ring-3 focus:ring-brand-500/15";

/** Dialog with enter/exit animation; stays mounted until the exit finishes. */
export function Modal({ title, open, onClose, children }: { title: string; open: boolean; onClose: () => void; children: ReactNode }) {
  const [mounted, setMounted] = useState(open);
  const [closing, setClosing] = useState(false);
  useEffect(() => {
    if (open) { setMounted(true); setClosing(false); }
    else if (mounted) {
      setClosing(true);
      const t = setTimeout(() => { setMounted(false); setClosing(false); }, reducedMotion() ? 0 : 160);
      return () => clearTimeout(t);
    }
  }, [open, mounted]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!mounted) return null;
  return createPortal(
    <div className={cx("fixed inset-0 z-50 flex items-center justify-center bg-ink/45 p-4 backdrop-blur-[2px] transition-opacity duration-150", closing ? "opacity-0" : "animate-fade-in")} onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className={cx("w-full max-w-lg rounded-md bg-white shadow-2xl transition duration-150", closing ? "scale-95 opacity-0" : "animate-scale-in")}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h3 className="font-medium text-ink">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-slate-500 transition hover:rotate-90 hover:bg-slate-100 hover:text-ink" aria-label={t("Close")}><X size={18} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export function Pager({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (o: number) => void }) {
  if (total <= limit) return null;
  return (
    <div className="flex items-center justify-between pt-4 text-sm text-muted">
      <span className="tabular-nums">{t("{a}–{b} of {n}", { a: offset + 1, b: Math.min(offset + limit, total), n: total.toLocaleString() })}</span>
      <div className="flex gap-2">
        <Button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>{t("Previous")}</Button>
        <Button disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>{t("Next")}</Button>
      </div>
    </div>
  );
}

export const th = "px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted bg-[#f8f9fa]";
export const td = "px-3 py-2.5 align-top";
/** Row class for data tables: subtle hover highlight. */
export const tr = "transition-colors duration-150 hover:bg-brand-50/50";

// Fixed month abbreviations: browsers disagree on "Sep" vs "Sept".
const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_SW = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ago", "Sep", "Okt", "Nov", "Des"];
const months = () => (getLang() === "sw" ? MONTHS_SW : MONTHS_EN);
const toDate = (d: string) => new Date(d.length === 10 ? d + "T00:00:00" : d);

/** "05 Oct 2026" */
export function fmtDate(d: string | null | undefined) {
  if (!d) return "—";
  const x = toDate(d);
  return `${String(x.getDate()).padStart(2, "0")} ${months()[x.getMonth()]} ${x.getFullYear()}`;
}

/** "05 Oct" */
export function fmtDay(d: string | null | undefined) {
  return fmtDate(d).slice(0, 6);
}

/** "2026-10" -> "Oct 2026" */
export function fmtMonth(ym: string) {
  const [y, m] = ym.split("-");
  return `${months()[Number(m) - 1]} ${y}`;
}

export function fmtDays(n: number) {
  return n === 1 ? t("1 day") : t("{n} days", { n: n.toLocaleString() });
}

/** Weekday name for a court day code ("Mon" -> "Monday" / "Jumatatu"). */
export function dayName(code: string) {
  return t({ Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday" }[code] ?? code);
}

export function pct(x: number | null | undefined, digits = 0) {
  return x == null ? "—" : `${(x * 100).toFixed(digits)}%`;
}

// --- risk explanations in plain language ------------------------------------------

const PAST_TARGET = "Already past disposition target";

/** "84% of disposition target elapsed (+0.53); 6 hearings held (-0.25)" -> rows */
export function parseFactors(s: string) {
  return s.split("; ").map((part) => {
    const m = part.match(/^(.*) \(([+-]\d+\.\d+)\)$/);
    return m ? { label: m[1], effect: parseFloat(m[2]) } : { label: part, effect: null };
  });
}

/** How strongly a factor moves the risk, in words (the model's effect sizes are 0..1). */
export function effectWords(effect: number) {
  const size = Math.abs(effect);
  if (size < 0.05) return { words: t("barely changes risk"), level: 0 };
  const up = effect > 0;
  return size >= 0.3 ? { words: t(up ? "raises risk strongly" : "lowers risk strongly"), level: 2 }
    : { words: t(up ? "raises risk" : "lowers risk"), level: 1 };
}

export function EffectIcon({ effect, size = 14 }: { effect: number; size?: number }) {
  const { level } = effectWords(effect);
  const up = effect > 0;
  const Icon = level === 0 ? Minus : level === 2 ? (up ? ChevronsUp : ChevronsDown) : (up ? ChevronUp : ChevronDown);
  return <Icon size={size} aria-hidden="true" className={cx("shrink-0", level === 0 ? "text-slate-500" : up ? "text-danger" : "text-[#2f8a6f]")} />;
}

/** The model's driving factors, each with an arrow for direction and strength.
 *  The exact effect size is kept in the tooltip. */
export function Factors({ text, daysOverdue, className }: { text: string; daysOverdue?: number | null; className?: string }) {
  if (text === PAST_TARGET) {
    return <p className={cx("text-xs text-ink", className)}>{daysOverdue ? t("Past its disposition target by {d}", { d: fmtDays(daysOverdue) }) : t("Past its disposition target")}</p>;
  }
  return (
    <ul className={cx("space-y-0.5 text-xs text-slate-600", className)}>
      {parseFactors(text).map((f) => (
        <li key={f.label} className="flex items-start gap-1" title={f.effect === null ? undefined : t("Effect on risk: {v}", { v: `${f.effect > 0 ? "+" : ""}${f.effect.toFixed(2)}` })}>
          {f.effect !== null && <span className="mt-px"><EffectIcon effect={f.effect} /></span>}
          <span>{tFactor(f.label)}{f.effect !== null && <span className="sr-only"> ({effectWords(f.effect).words})</span>}</span>
        </li>
      ))}
    </ul>
  );
}

/** One-line key for the arrows used by <Factors>. */
export function FactorKey() {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
      <span className="inline-flex items-center gap-1"><EffectIcon effect={0.4} /> {t("raises risk strongly")}</span>
      <span className="inline-flex items-center gap-1"><EffectIcon effect={0.15} /> {t("raises risk")}</span>
      <span className="inline-flex items-center gap-1"><EffectIcon effect={-0.15} /> {t("lowers risk")}</span>
    </span>
  );
}

/** Risk badge plus either "Overdue N days" or the predicted chance of overrunning. */
export function RiskSummary({ category, probability, daysOverdue, overridden }: {
  category: RiskCategory | string | null | undefined; probability?: number | null; daysOverdue?: number | null; overridden?: boolean;
}) {
  return (
    <>
      <RiskBadge category={category} overridden={overridden} />
      {daysOverdue ? <div className="mt-0.5 whitespace-nowrap text-xs font-medium text-danger">{t("Overdue {d}", { d: fmtDays(daysOverdue) })}</div>
        : probability != null && <div className="mt-0.5 whitespace-nowrap text-xs tabular-nums text-slate-500">{t("{p} chance", { p: pct(probability) })}</div>}
    </>
  );
}

/** Small badge: accused held in remand. */
export function RemandBadge({ days }: { days?: number | null }) {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-[#5b3d8a]/10 px-2 py-0.5 text-xs font-medium text-[#5b3d8a]"
      title={t("Accused held in remand")}>
      {days ? t("In remand {d}", { d: fmtDays(days) }) : t("In remand")}
    </span>
  );
}
