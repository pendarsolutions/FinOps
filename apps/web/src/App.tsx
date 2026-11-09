import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactElement } from "react";
import { Layout } from "./components/Layout";
import { useSession } from "./lib/session";
import { LoginPage } from "./pages/Login";
import { ForgotPasswordPage, ResetPasswordPage } from "./pages/PasswordReset";
import { OverviewPage } from "./pages/Overview";
import { InfrastructurePage } from "./pages/Infrastructure";
import { ServersPage } from "./pages/Servers";
import { HowItWorksContent } from "./pages/HowItWorks";
import { CostsPage } from "./pages/Costs";
import { OpportunitiesPage } from "./pages/Opportunities";
import { ComparePage } from "./pages/Compare";
import { ReportsPage } from "./pages/Reports";
import { CatalogPage } from "./pages/Catalog";
import { IntegrationsPage } from "./pages/Integrations";
import { SettingsPage } from "./pages/Settings";

/** Signed-out visitors go to sign-in, which sends a fresh installation on to creating its first account. */
function RequireAuth({ children }: { children: ReactElement }) {
  const { session } = useSession();
  const loc = useLocation();
  if (!session) {
    const from = loc.pathname === "/" ? undefined : { from: loc.pathname + loc.search };
    return <Navigate to="/login" replace state={from} />;
  }
  return children;
}

/**
 * The dashboard an installation serves. The public website (landing page, install command) is a separate project in
 * site/, so a server never shows marketing pages.
 */
export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage mode="login" />} />
      <Route path="/register" element={<LoginPage mode="register" />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      {/* addresses from 0.2.0 and earlier, which had a landing page */}
      <Route path="/welcome" element={<Navigate to="/" replace />} />
      <Route path="/how-it-works" element={<Navigate to="/guide" replace />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="infrastructure" element={<InfrastructurePage />} />
        <Route path="costs" element={<CostsPage />} />
        <Route path="opportunities" element={<OpportunitiesPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="integrations" element={<IntegrationsPage />} />
        <Route path="guide" element={<HowItWorksContent />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
