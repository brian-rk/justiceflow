import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { onActivity } from "../api";
import { cx, useCountUp } from "./ui";

// --- toasts ----------------------------------------------------------------------

type ToastTone = "success" | "error" | "info";
interface Toast { id: number; tone: ToastTone; text: ReactNode; leaving?: boolean }

const ToastCtx = createContext<(tone: ToastTone, text: ReactNode) => void>(() => {});
const TOAST_MS = 3800;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((ts) => ts.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    setTimeout(() => setToasts((ts) => ts.filter((t) => t.id !== id)), 220);
  }, []);

  const push = useCallback((tone: ToastTone, text: ReactNode) => {
    const id = nextId.current++;
    setToasts((ts) => [...ts.slice(-3), { id, tone, text }]);
    setTimeout(() => dismiss(id), TOAST_MS);
  }, [dismiss]);

  const icon = { success: CheckCircle2, error: AlertCircle, info: Info };
  const color = { success: "text-ok", error: "text-danger", info: "text-brand-500" };
  const bar = { success: "bg-ok", error: "bg-danger", info: "bg-brand-500" };

  return (
    <ToastCtx.Provider value={push}>
      {children}
      {createPortal(
        <div className="pointer-events-none fixed right-4 top-20 z-[60] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
          {toasts.map((t) => {
            const Icon = icon[t.tone];
            return (
              <div key={t.id} role={t.tone === "error" ? "alert" : "status"}
                className="pointer-events-auto relative overflow-hidden rounded-md bg-white shadow-xl ring-1 ring-slate-900/5"
                style={{ animation: t.leaving ? "toast-out 200ms ease-in forwards" : "toast-in 280ms var(--ease-out-quart) both" }}>
                <div className="flex items-start gap-3 px-4 py-3 text-sm text-ink">
                  <Icon size={18} className={cx("mt-0.5 shrink-0", color[t.tone])} />
                  <div className="min-w-0 flex-1">{t.text}</div>
                  <button onClick={() => dismiss(t.id)} className="rounded p-0.5 text-slate-400 transition hover:bg-slate-100 hover:text-ink" aria-label="Dismiss"><X size={14} /></button>
                </div>
                <div className={cx("h-0.5 origin-left opacity-60", bar[t.tone])} style={{ animation: `toast-timer ${TOAST_MS}ms linear forwards` }} />
              </div>
            );
          })}
        </div>,
        document.body,
      )}
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastCtx);
  return {
    success: (t: ReactNode) => push("success", t),
    error: (t: ReactNode) => push("error", t),
    info: (t: ReactNode) => push("info", t),
  };
}

// --- top progress bar -------------------------------------------------------------

/** Thin animated bar at the top of the page while any API request is in flight
 *  (shown only if the request lasts longer than 150 ms, to avoid flicker). */
export function TopProgress() {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const off = onActivity((n) => {
      clearTimeout(timer);
      if (n > 0) timer = setTimeout(() => setVisible(true), 150);
      else setVisible(false);
    });
    return () => { off(); clearTimeout(timer); };
  }, []);
  return (
    <div aria-hidden="true" className={cx("fixed inset-x-0 top-0 z-[70] h-[3px] transition-opacity duration-300", visible ? "opacity-100" : "opacity-0")}>
      <div className="top-progress h-full w-full" />
    </div>
  );
}

// --- bars & numbers -------------------------------------------------------------------

/** A bar that grows from zero to `share` (0..1) after mount. */
export function GrowBar({ share, className = "bg-brand-500", delay = 0, height = "h-2", track = "bg-slate-100" }: {
  share: number; className?: string; delay?: number; height?: string; track?: string;
}) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setW(Math.max(0, Math.min(1, share))), 60 + delay);
    return () => clearTimeout(t);
  }, [share, delay]);
  return (
    <div className={cx("overflow-hidden rounded-full", height, track)}>
      <div className={cx("h-full rounded-full transition-[width] duration-700 ease-[var(--ease-out-quart)]", className)} style={{ width: `${w * 100}%` }} />
    </div>
  );
}

/** Number that counts up to its value. */
export function Num({ value }: { value: number }) {
  return <>{useCountUp(value).toLocaleString()}</>;
}

// --- tabs with a sliding indicator ---------------------------------------------------------

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: readonly (readonly [T, string])[]; value: T; onChange: (v: T) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [pill, setPill] = useState({ left: 0, width: 0 });
  useLayoutEffect(() => {
    const el = refs.current[value];
    if (el) setPill({ left: el.offsetLeft, width: el.offsetWidth });
  }, [value, tabs]);
  return (
    <div role="tablist" className="relative mb-5 inline-flex max-w-full overflow-x-auto rounded-md bg-white p-1 shadow-sm ring-1 ring-slate-900/5">
      <span aria-hidden="true" className="absolute inset-y-1 rounded bg-brand-500 shadow-sm shadow-brand-500/30 transition-all duration-300 ease-[var(--ease-out-quart)]"
        style={{ left: pill.left, width: pill.width }} />
      {tabs.map(([k, label]) => (
        <button key={k} ref={(el) => { refs.current[k] = el; }} role="tab" aria-selected={value === k} onClick={() => onChange(k)}
          className={cx("relative z-10 whitespace-nowrap rounded px-4 py-1.5 text-sm font-medium transition-colors duration-200",
            value === k ? "text-white" : "text-muted hover:text-ink")}>
          {label}
        </button>
      ))}
    </div>
  );
}

/** Content that cross-fades when `k` changes (e.g. tab panels). */
export function FadeSwap({ k, children }: { k: string; children: ReactNode }) {
  return <div key={k} className="animate-fade-up">{children}</div>;
}
