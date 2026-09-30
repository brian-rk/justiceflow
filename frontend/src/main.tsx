import { StrictMode, Suspense, lazy, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, HOME, useAuth } from "./auth";
import Layout from "./components/Layout";
import { ToastProvider } from "./components/motion";
import { Loading } from "./components/ui";
import "./index.css";
import type { Role } from "./types";
import CaseDetail from "./pages/CaseDetail";
import Cases from "./pages/Cases";
import CauseList from "./pages/CauseList";
import ClerkEntry from "./pages/ClerkEntry";
import Dashboard from "./pages/Dashboard";
import Escalations from "./pages/Escalations";
import Fairness from "./pages/Fairness";
import Login from "./pages/Login";
import MySchedule from "./pages/MySchedule";
import ReviewQueue from "./pages/ReviewQueue";
import Settings from "./pages/Settings";

// Charts are heavy; load the Reports page only when opened.
const Reports = lazy(() => import("./pages/Reports"));

function Guard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) return <Navigate to={HOME[user.role]} replace />;
  return <>{children}</>;
}

function App() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  const all: Role[] = ["clerk", "registrar", "magistrate", "management", "admin"];
  const oversight: Role[] = ["registrar", "management", "admin"];
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to={HOME[user.role]} replace /> : <Login />} />
      <Route element={<Guard roles={all}><Layout /></Guard>}>
        <Route path="/dashboard" element={<Guard roles={oversight}><Dashboard /></Guard>} />
        <Route path="/entry" element={<Guard roles={["clerk"]}><ClerkEntry /></Guard>} />
        <Route path="/review" element={<Guard roles={["registrar"]}><ReviewQueue /></Guard>} />
        <Route path="/cause-list" element={<Guard roles={oversight}><CauseList /></Guard>} />
        <Route path="/cause-list/:cycleId" element={<Guard roles={oversight}><CauseList /></Guard>} />
        <Route path="/cases" element={<Guard roles={["clerk", ...oversight]}><Cases /></Guard>} />
        <Route path="/cases/:caseId" element={<Guard roles={["clerk", ...oversight]}><CaseDetail /></Guard>} />
        <Route path="/my-schedule" element={<Guard roles={["magistrate"]}><MySchedule /></Guard>} />
        <Route path="/escalations" element={<Guard roles={oversight}><Escalations /></Guard>} />
        <Route path="/reports" element={<Guard roles={["management", "admin"]}><Suspense fallback={<Loading />}><Reports /></Suspense></Guard>} />
        <Route path="/fairness" element={<Guard roles={["management", "admin"]}><Fairness /></Guard>} />
        <Route path="/settings" element={<Guard roles={["admin"]}><Settings /></Guard>} />
      </Route>
      <Route path="*" element={<Navigate to={user ? HOME[user.role] : "/login"} replace />} />
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
