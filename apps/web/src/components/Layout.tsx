import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useI18n, type TKey } from "../lib/i18n";
import { useSession } from "../lib/session";
import { Advisor } from "./Advisor";
import { Button } from "./ui";
import { localizeDigits } from "../lib/money";
import { TourProvider, useTour } from "./Tour";
import { TooltipLayer } from "./viz";

const NAV: { to: string; key: TKey; tour: string }[] = [
  { to: "/", key: "navOverview", tour: "nav-overview" },
  { to: "/servers", key: "navServers", tour: "nav-servers" },
  { to: "/infrastructure", key: "navInfrastructure", tour: "nav-infrastructure" },
  { to: "/costs", key: "navCosts", tour: "nav-costs" },
  { to: "/opportunities", key: "navOpportunities", tour: "nav-opportunities" },
  { to: "/compare", key: "navCompare", tour: "nav-compare" },
  { to: "/reports", key: "navReports", tour: "nav-reports" },
  { to: "/catalog", key: "navCatalog", tour: "nav-catalog" },
  { to: "/integrations", key: "navIntegrations", tour: "nav-integrations" },
  { to: "/settings", key: "navSettings", tour: "nav-settings" },
];

const INVENTORY_PAGES = ["/", "/infrastructure", "/costs", "/opportunities", "/compare", "/reports"];

export function Layout() {
  const [navOpen, setNavOpen] = useState(false);
  return (
    <TourProvider onNeedNav={setNavOpen}>
      <TooltipLayer>
        <Shell navOpen={navOpen} setNavOpen={setNavOpen} />
      </TooltipLayer>
    </TourProvider>
  );
}

function Shell({ navOpen, setNavOpen }: { navOpen: boolean; setNavOpen: (f: (o: boolean) => boolean) => void }) {
  const { t, lang, setLang } = useI18n();
  const { session, signOut, inventories, activeId, setActiveId } = useSession();
  const tour = useTour();
  useEffect(() => {
    if (session) tour.maybeAutoStart(session.user.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.user.id]);
  const [advisorOpen, setAdvisorOpen] = useState(false);
  const loc = useLocation();
  const onInventoryPage = INVENTORY_PAGES.includes(loc.pathname);

  return (
    <div className="shell">
      <a href="#main" className="skip">
        Skip to content
      </a>
      <header className="topbar">
        <Button variant="ghost" className="nav-toggle" aria-expanded={navOpen} aria-controls="sidenav" onClick={() => setNavOpen((o) => !o)}>
          ☰ <span className="sr-only">{t("menu")}</span>
        </Button>
        <div className="brand">
          <span className="logo" aria-hidden>
            F
          </span>
          <span>{t("appName")}</span>
        </div>
        <div className="topbar-inv" data-tour="inventory">
          <label htmlFor="inv-select" className="sr-only">
            {t("selectInventory")}
          </label>
          <select id="inv-select" value={activeId ?? ""} onChange={(e) => setActiveId(e.target.value || null)} disabled={!inventories?.length}>
            {!inventories?.length && <option value="">{t("noInventory")}</option>}
            {inventories?.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} · {i.status === "confirmed" ? "✓" : "…"} {localizeDigits(i.created_at.slice(0, 10), lang)}
              </option>
            ))}
          </select>
        </div>
        <div className="topbar-actions">
          {onInventoryPage && activeId ? (
            <Button variant="primary" onClick={() => setAdvisorOpen(true)} data-tour="advisor">
              {t("advisor")}
            </Button>
          ) : null}
          <Button variant="ghost" onClick={() => tour.start()} data-tour="help" title={t("tourRestart")}>
            ? <span className="hide-sm">{t("tourHelp")}</span>
          </Button>
          <Button variant="ghost" data-tour="lang" onClick={() => setLang(lang === "fa" ? "en" : "fa")} aria-label={t("language")} lang={lang === "fa" ? "en" : "fa"}>
            {lang === "fa" ? "EN" : "فا"}
          </Button>
          <span className="who" title={session?.user.email}>
            {session?.organization.name} · <small>{session?.role}</small>
          </span>
          <Button variant="ghost" onClick={signOut}>
            {t("logout")}
          </Button>
        </div>
      </header>
      <nav id="sidenav" className={navOpen ? "sidenav open" : "sidenav"} aria-label="Primary">
        <ul>
          {NAV.map((n) => (
            <li key={n.to}>
              <NavLink to={n.to} end={n.to === "/"} onClick={() => setNavOpen(() => false)} data-tour={n.tour}>
                {t(n.key)}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main id="main" className="main">
        <Outlet />
      </main>
      {activeId ? <Advisor open={advisorOpen} onClose={() => setAdvisorOpen(false)} inventoryId={activeId} /> : null}
    </div>
  );
}
