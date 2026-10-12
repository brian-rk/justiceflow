import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, Loader2, Lock, LogIn } from "lucide-react";
import { HOME, ROLE_LABEL, useAuth } from "../auth";
import { Alert, Button, Logo, cx, inputCls } from "../components/ui";
import loginBg from "../assets/login-bg.jpg";
import { LangToggle, t } from "../i18n";

const DEMO = [
  ["clerk", "clerk"], ["registrar", "registrar"], ["magistrate", "magistrate"],
  ["manager", "management"], ["admin", "admin"],
] as const;

/** Specks of light rising behind the card. Fixed pseudo-random layout. */
const PARTICLES = Array.from({ length: 26 }, (_, i) => {
  const r = (n: number) => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1;
  return { left: r(1) * 100, size: 4 + Math.round(r(2) * 7), t: 12 + r(3) * 14, d: -r(4) * 26, dx: (r(5) - 0.5) * 120, o: 0.35 + r(6) * 0.5 };
});

/** Waves drifting along the bottom of the screen. */
function BottomWaves() {
  const wave = "M0 60 C 150 20, 300 100, 450 60 S 750 20, 900 60 S 1200 100, 1350 60 S 1650 20, 1800 60 V120 H0Z";
  return (
    <div className="absolute inset-x-0 bottom-0 h-40 overflow-hidden">
      <svg className="wave-drift-slow absolute bottom-0 h-40 w-[200%]" viewBox="0 0 1800 120" preserveAspectRatio="none"><path d={wave} fill="#4090cb" opacity=".18" /></svg>
      <svg className="wave-drift absolute bottom-0 h-28 w-[200%]" viewBox="0 0 1800 120" preserveAspectRatio="none"><path d={wave} fill="#2b354f" opacity=".35" /></svg>
    </div>
  );
}

/** Layered waves anchored to the bottom of the card (the "bg-pattern" look). */
function WavePattern() {
  return (
    <svg className="pointer-events-none absolute inset-x-0 bottom-0 h-40 w-full" viewBox="0 0 400 160" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 100 C 80 70, 160 130, 240 100 S 360 70, 400 90 V160 H0Z" fill="#4090cb" opacity=".06" />
      <path d="M0 120 C 90 95, 170 150, 260 118 S 360 100, 400 115 V160 H0Z" fill="#4090cb" opacity=".08" />
      <path d="M0 140 C 100 125, 180 160, 280 138 S 370 130, 400 138 V160 H0Z" fill="#2b354f" opacity=".06" />
    </svg>
  );
}

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anim, setAnim] = useState<"enter" | "shake" | null>("enter");
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(username, password);
      nav(HOME[u.role], { replace: true });
    } catch (err) {
      setError((err as Error).message);
      setAnim(null);
      requestAnimationFrame(() => setAnim("shake"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-brand-900 px-4 py-10">
      {/* Background photo: softly blurred (the source is low resolution), slow zoom,
          under a deep-blue wash so the card and text stay readable. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="login-photo absolute -inset-6 bg-cover bg-center" style={{ backgroundImage: `url(${loginBg})` }} />
        <div className="absolute inset-0 bg-linear-to-br from-brand-900/70 via-brand-900/45 to-brand-700/35" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,rgba(20,28,45,0.45)_100%)]" />
        <div className="light-beam" />
        {PARTICLES.map((pt, i) => (
          <span key={i} className="particle" style={{
            left: `${pt.left}%`, width: pt.size, height: pt.size,
            ["--t" as string]: `${pt.t}s`, ["--d" as string]: `${pt.d}s`, ["--dx" as string]: `${pt.dx}px`, ["--o" as string]: pt.o,
          }} />
        ))}
        <BottomWaves />
      </div>

      <div className="absolute right-4 top-4 z-10"><LangToggle dark /></div>
      <div className="relative w-full max-w-[440px]">
        <div className="relative">
        <div aria-hidden="true" className="card-halo blurred" />
        <div aria-hidden="true" className="card-halo" />
        <div onAnimationEnd={(e) => e.target === e.currentTarget && setAnim(null)}
          className={cx("relative overflow-hidden rounded-md bg-white shadow-[0_24px_60px_-12px_rgba(0,0,0,0.45)] ring-1 ring-white/10", anim === "shake" && "animate-[shake_380ms_ease-in-out]", anim === "enter" && "animate-scale-in")}>
          <div className="h-1 bg-linear-to-r from-brand-500 via-brand-300 to-warn" />
          <WavePattern />

          <div className="relative px-8 pb-10 pt-8">
            <div className="text-center">
              <Logo size={80} motion="intro" className="mx-auto animate-float drop-shadow-md" />
              <h1 className="mt-4 text-[22px] font-medium text-ink">JusticeFlow TZ</h1>
              <p className="mt-1 text-sm text-muted">{t("Sign in to continue to the case-flow dashboard")}</p>
            </div>

            <form onSubmit={submit} className="stagger mt-7 space-y-4">
              {error && <Alert tone="error">{error}</Alert>}
              <div>
                <label htmlFor="username" className="mb-1.5 block text-[13px] font-medium text-ink">{t("Username")}</label>
                <input id="username" className={inputCls} placeholder={t("Enter your username")} value={username}
                  onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
              </div>
              <div>
                <label htmlFor="password" className="mb-1.5 block text-[13px] font-medium text-ink">{t("Password")}</label>
                <div className="relative">
                  <input id="password" className={inputCls + " pr-10"} type={show ? "text" : "password"} placeholder={t("Enter your password")}
                    value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
                  <button type="button" onClick={() => setShow((s) => !s)} aria-label={t(show ? "Hide password" : "Show password")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 transition hover:text-ink">
                    {show ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </div>
              <div className="pt-2">
                <Button variant="primary" className="w-full py-2.5 text-[15px]" disabled={busy}>
                  {busy ? <Loader2 size={18} className="animate-spin" /> : <LogIn size={18} />}
                  {busy ? t("Signing in…") : t("Sign in")}
                </Button>
              </div>
              <div className="pt-2 text-center">
                <button type="button" onClick={() => setForgot((f) => !f)} className="inline-flex items-center gap-1.5 text-sm text-muted transition hover:text-brand-600">
                  <Lock size={14} /> {t("Forgot your password?")}
                </button>
                <div className={cx("grid transition-[grid-template-rows,opacity] duration-300 ease-out", forgot ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0")}>
                  <p className="overflow-hidden text-xs text-muted"><span className="block pt-2">{t("Passwords are reset by your court's system administrator.")}</span></p>
                </div>
              </div>
            </form>
          </div>
        </div>

        </div>

        <div className="mt-6 animate-fade-up [animation-delay:250ms]">
          <p className="mb-2 text-center text-xs text-white/85 [text-shadow:0_1px_3px_rgba(0,0,0,0.6)]">{t("Demo accounts, password")} <code className="rounded bg-white/15 px-1.5 py-0.5 text-white ring-1 ring-white/25">demo1234</code></p>
          <div className="flex flex-wrap justify-center gap-2">
            {DEMO.map(([u, role]) => (
              <button key={u} type="button" onClick={() => { setUsername(u); setPassword("demo1234"); setError(null); }}
                aria-pressed={username === u}
                className={cx("rounded-full px-3 py-1 text-xs shadow-sm ring-1 transition duration-200 hover:-translate-y-0.5",
                  username === u ? "bg-brand-600 text-white ring-brand-300" : "bg-brand-900/70 text-white ring-white/35 backdrop-blur-sm hover:bg-brand-900/85")}>
                {t(ROLE_LABEL[role])}
              </button>
            ))}
          </div>
        </div>

        <p className="mt-8 text-center text-xs text-white/75 [text-shadow:0_1px_3px_rgba(0,0,0,0.6)]">
          © {new Date().getFullYear()} JusticeFlow TZ. {t("Decision support for court registries, Judiciary of Tanzania (Tanzania Mainland).")}<br />
          {t("Read-only overlay: never writes to JoT-eCMS or JSDS2. No schedule is final without registrar approval.")}
        </p>
      </div>
    </div>
  );
}
