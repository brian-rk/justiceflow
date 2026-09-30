import { useEffect, useLayoutEffect, useRef, useState, type ComponentType, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  AlertTriangle, BarChart3, Bell, CalendarDays, ChevronDown, ClipboardCheck, FilePenLine, FolderOpen,
  Gauge, ListChecks, LogOut, Menu, PanelLeftClose, PanelLeftOpen, Scale, Search, Settings as SettingsIcon, X,
} from "lucide-react";
import { api } from "../api";
import { ROLE_LABEL, useAuth } from "../auth";
import type { Role } from "../types";
import { TopProgress } from "./motion";
import { Logo, cx } from "./ui";

// `motion` is the icon's hover animation (see "Icon micro-animations" in index.css).
type NavItem = { to: string; label: string; roles: Role[]; icon: ComponentType<{ size?: number; className?: string }>; motion: string };

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Main",
    items: [
      { to: "/dashboard", label: "Dashboard", roles: ["registrar", "management", "admin"], icon: Gauge, motion: "ic-sweep" },
      { to: "/entry", label: "Case data entry", roles: ["clerk"], icon: FilePenLine, motion: "ic-rise" },
      { to: "/my-schedule", label: "My schedule", roles: ["magistrate"], icon: CalendarDays, motion: "ic-flip" },
      { to: "/review", label: "Review queue", roles: ["registrar"], icon: ClipboardCheck, motion: "ic-check" },
      { to: "/cause-list", label: "Cause list", roles: ["registrar", "management", "admin"], icon: ListChecks, motion: "ic-rise" },
      { to: "/cases", label: "Case list", roles: ["clerk", "registrar", "management", "admin"], icon: FolderOpen, motion: "ic-rise" },
    ],
  },
  {
    section: "Oversight",
    items: [
      { to: "/escalations", label: "Escalations", roles: ["registrar", "management", "admin"], icon: AlertTriangle, motion: "ic-pulse" },
      { to: "/reports", label: "Reports", roles: ["management", "admin"], icon: BarChart3, motion: "ic-rise" },
      { to: "/fairness", label: "Fairness audit", roles: ["management", "admin"], icon: Scale, motion: "ic-swing" },
    ],
  },
  {
    section: "Administration",
    items: [{ to: "/settings", label: "Settings", roles: ["admin"], icon: SettingsIcon, motion: "ic-spin" }],
  },
];

const COLLAPSE_KEY = "jf_sidebar_collapsed";

export default function Layout() {
  const { user } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; }
  });
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    setDrawer(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [location.pathname]);
  useEffect(() => {
    try { localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0"); } catch { /* per-viewer nicety only */ }
  }, [collapsed]);

  if (!user) return null;
  const sections = NAV.map((s) => ({ ...s, items: s.items.filter((i) => i.roles.includes(user.role)) })).filter((s) => s.items.length);

  return (
    <div className="min-h-screen">
      <TopProgress />
      {/* Desktop sidebar */}
      <aside className={cx("fixed inset-y-0 left-0 z-30 hidden flex-col bg-brand-900 transition-[width] duration-300 ease-[var(--ease-out-quart)] lg:flex",
        collapsed ? "w-[72px]" : "w-64")}>
        <Sidebar sections={sections} collapsed={collapsed} />
      </aside>

      {/* Mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/50 animate-fade-in" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-brand-900 shadow-2xl animate-slide-in-left">
            <button onClick={() => setDrawer(false)} className="absolute right-3 top-5 rounded p-1 text-white/70 hover:bg-white/10 hover:text-white" aria-label="Close menu"><X size={18} /></button>
            <Sidebar sections={sections} collapsed={false} />
          </aside>
        </div>
      )}

      <div className={cx("flex min-h-screen flex-col transition-[padding] duration-300 ease-[var(--ease-out-quart)]", collapsed ? "lg:pl-[72px]" : "lg:pl-64")}>
        <Topbar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} onMenu={() => setDrawer(true)} />
        <main className="flex-1 px-4 py-6 md:px-6 lg:px-8">
          <div key={location.pathname} className="page-enter mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
        <footer className="border-t border-slate-200/70 bg-white px-6 py-4 text-center text-xs text-muted">
          © {new Date().getFullYear()} JusticeFlow TZ · Case-delay decision support · Read-only overlay: never writes to JoT-eCMS or JSDS2
        </footer>
      </div>
    </div>
  );
}

function Sidebar({ sections, collapsed }: { sections: { section: string; items: NavItem[] }[]; collapsed: boolean }) {
  const { pathname } = useLocation();
  const navRef = useRef<HTMLElement>(null);
  const [marker, setMarker] = useState<{ top: number; height: number } | null>(null);

  // One highlight that glides to whichever item is active. Measured from the
  // rendered position, and measured again once the items' entrance animation ends.
  const measure = () => {
    const nav = navRef.current;
    const active = nav?.querySelector<HTMLElement>('a[aria-current="page"]');
    if (!nav || !active) { setMarker(null); return; }
    const n = nav.getBoundingClientRect(), a = active.getBoundingClientRect();
    setMarker({ top: a.top - n.top + nav.scrollTop, height: a.height });
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(measure, [pathname, collapsed, sections.length]);

  return (
    <>
      <Link to="/" className="logo-hover flex h-16 shrink-0 items-center gap-3 border-b border-white/10 px-4">
        <Logo size={38} motion="hover" className="shrink-0 drop-shadow" />
        <div className={cx("min-w-0 transition-opacity duration-200", collapsed && "pointer-events-none opacity-0")}>
          <div className="truncate text-[15px] font-medium tracking-wide text-white">JusticeFlow TZ</div>
          <div className="truncate text-[11px] text-white/50">Case-flow decision support</div>
        </div>
      </Link>
      <nav ref={navRef} onAnimationEnd={measure} className="scroll-thin relative flex-1 overflow-y-auto overflow-x-hidden py-4" aria-label="Main">
        {marker && (
          <div aria-hidden="true" className="pointer-events-none absolute left-3 right-3 rounded-md bg-white/10 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition-[top,height] duration-500 ease-[var(--ease-spring)]"
            style={{ top: marker.top, height: marker.height }}>
            <span className="absolute left-[-12px] top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-r bg-brand-500 shadow-[0_0_10px_2px_rgba(64,144,203,0.6)]" />
          </div>
        )}
        {sections.map((s) => (
          <div key={s.section} className="mb-4">
            <div className={cx("mb-1 px-6 text-[11px] font-medium uppercase tracking-[0.12em] text-white/35 transition-opacity duration-200", collapsed && "opacity-0")}>
              {s.section}
            </div>
            <ul className="stagger space-y-0.5 px-3">
              {s.items.map((n) => (
                <li key={n.to}>
                  <NavLink
                    to={n.to}
                    title={collapsed ? n.label : undefined}
                    className={({ isActive }) => cx(
                      "group relative flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors duration-200",
                      isActive ? "text-white" : "text-white/60 hover:bg-white/5 hover:text-white",
                    )}
                  >
                    {({ isActive }) => (
                      <>
                        <n.icon size={18} className={cx("shrink-0 transition-colors duration-300", n.motion, isActive && "text-brand-300")} />
                        <span className={cx("truncate whitespace-nowrap transition-opacity duration-200", collapsed && "opacity-0")}>{n.label}</span>
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </>
  );
}

function Topbar({ collapsed, onToggle, onMenu }: { collapsed: boolean; onToggle: () => void; onMenu: () => void }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [menu, setMenu] = useState(false);
  const [escalations, setEscalations] = useState<number | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const oversight = user && ["registrar", "management", "admin"].includes(user.role);
  const canSearch = user && user.role !== "magistrate";

  useEffect(() => {
    if (!oversight) return;
    api.get<unknown[]>("/escalations").then((e) => setEscalations(e.length)).catch(() => setEscalations(null));
  }, [oversight]);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenu(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  if (!user) return null;
  const initials = user.full_name.split(" ").map((w) => w[0]).filter((c) => /[A-Za-z]/.test(c)).slice(0, 2).join("").toUpperCase();

  const search = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) nav(`/cases?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200/70 bg-white/90 px-4 backdrop-blur md:px-6">
      <button onClick={onMenu} className="rounded-md p-2 text-muted transition hover:bg-slate-100 hover:text-ink lg:hidden" aria-label="Open menu"><Menu size={20} /></button>
      <button onClick={onToggle} className="hidden rounded-md p-2 text-muted transition hover:bg-slate-100 hover:text-ink lg:block" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
        {collapsed ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}
      </button>

      {canSearch && (
        <form onSubmit={search} className="relative hidden max-w-xs flex-1 sm:block">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search case number…" aria-label="Search case number"
            className="w-full rounded-full border border-transparent bg-canvas py-2 pl-9 pr-4 text-sm text-ink transition duration-200 placeholder:text-slate-400 focus:w-full focus:border-brand-300 focus:bg-white focus:outline-none focus:ring-3 focus:ring-brand-500/15" />
        </form>
      )}

      <div className="ml-auto flex items-center gap-1">
        {oversight && (
          <Link to="/escalations" className="group relative rounded-md p-2 text-muted transition hover:bg-slate-100 hover:text-ink" aria-label={`${escalations ?? 0} open escalations`}>
            <Bell size={20} className={cx("ic-wiggle", escalations ? "origin-top animate-[wiggle_1s_ease-in-out_1]" : "")} />
            {!!escalations && (
              <span className="absolute right-0.5 top-0.5 grid min-w-[18px] place-items-center rounded-full bg-danger px-1 text-[10px] font-medium leading-[18px] text-white ring-2 ring-white animate-scale-in">
                {escalations > 99 ? "99+" : escalations}
              </span>
            )}
          </Link>
        )}

        <div ref={menuRef} className="relative">
          <button onClick={() => setMenu((m) => !m)} className="flex items-center gap-2 rounded-md py-1.5 pl-1.5 pr-2 transition hover:bg-slate-100" aria-expanded={menu} aria-haspopup="menu">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-linear-to-br from-brand-500 to-brand-900 text-xs font-medium text-white">{initials}</span>
            <span className="hidden text-left leading-tight md:block">
              <span className="block text-sm font-medium text-ink">{user.full_name}</span>
              <span className="block text-xs text-muted">{ROLE_LABEL[user.role]}</span>
            </span>
            <ChevronDown size={16} className={cx("text-muted transition-transform duration-200", menu && "rotate-180")} />
          </button>
          {menu && (
            <div role="menu" className="absolute right-0 mt-2 w-56 origin-top-right rounded-md bg-white py-1 shadow-xl ring-1 ring-slate-900/5 animate-scale-in">
              <div className="border-b border-slate-100 px-4 py-3">
                <div className="text-sm font-medium text-ink">{user.full_name}</div>
                <div className="text-xs text-muted">@{user.username} · {ROLE_LABEL[user.role]}</div>
              </div>
              <button role="menuitem" onClick={logout} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-danger transition hover:bg-danger/5">
                <LogOut size={16} /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
