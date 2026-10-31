import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactElement } from "react";
import { Layout } from "./components/Layout";
import { useSession } from "./lib/session";
import { LoginPage } from "./pages/Login";
import { LandingPage } from "./pages/Landing";
import { OverviewPage } from "./pages/Overview";
import { InfrastructurePage } from "./pages/Infrastructure";
import { CostsPage } from "./pages/Costs";
import { OpportunitiesPage } from "./pages/Opportunities";
import { ComparePage } from "./pages/Compare";
import { ReportsPage } from "./pages/Reports";
import { CatalogPage } from "./pages/Catalog";
import { IntegrationsPage } from "./pages/Integrations";
import { SettingsPage } from "./pages/Settings";

function RequireAuth({ children }: { children: ReactElement }) {
  const { session } = useSession();
  const loc = useLocation();
  if (!session) {
    // Visitors hitting the root get the landing page; deep links go straight to sign-in and come back after.
    if (loc.pathname === "/") return <Navigate to="/welcome" replace />;
    return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  }
  return children;
}

export function App() {
  return (
    <Routes>
      <Route path="/welcome" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage mode="login" />} />
      <Route path="/register" element={<LoginPage mode="register" />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="infrastructure" element={<InfrastructurePage />} />
        <Route path="costs" element={<CostsPage />} />
        <Route path="opportunities" element={<OpportunitiesPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="integrations" element={<IntegrationsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
