import { useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { ArrowUpRight, Menu, X } from 'lucide-react';
import { useAuth } from './lib/auth.jsx';
import { useSite } from './lib/site.jsx';
import { ThemeCustomizer } from './lib/theme.jsx';
import { AppErrorBoundary, Button, ErrorBox, Loading } from './components/ui.jsx';
import { initSmoothScroll, gsap } from './lib/motion.js';
import { SamaritanBootLoader } from './components/SamaritanBootLoader.jsx';
import {
  About,
  ContactPage,
  EventDetail,
  EventsPage,
  FAQPage,
  Footer,
  Home,
  PassPage,
  SchedulePage,
  TeamPage,
  VenuePage,
} from './pages/Public.jsx';
import {
  PortalLayout,
  PortalOverview,
  PortalPass,
  PortalProfile,
  PortalRegistrations,
  PortalSelectEvents,
  PortalTeams,
  PortalTickets,
  PortalVerification,
} from './pages/Portal.jsx';
import {
  AdminAnnouncements,
  AdminAttendance,
  AdminAudit,
  AdminCheckin,
  AdminEvents,
  AdminLayout,
  AdminOverview,
  AdminPayments,
  AdminPolicy,
  AdminRegistrations,
  AdminSettings,
  AdminUsers,
  AdminVerifications,
} from './pages/Admin.jsx';
import Login from './pages/Login.jsx';

const PUBLIC_NAV = [
  ['About', '/about'],
  ['Events', '/events'],
  ['Pass', '/pass'],
  ['Schedule', '/schedule'],
  ['Venue', '/venue'],
  ['FAQ', '/faq'],
  ['Contact', '/contact'],
  ['Meet the Team', '/team'],
];

const LOGO = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.png`;
const ISTE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/ISTE LOGO NO  BG PNG.png`;

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [pathname]);
  return null;
}

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading label="Checking your session" rows={0} />;
  if (!user) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  }
  return children;
}

function RequireStaff({ children }) {
  const { user, loading, isStaff } = useAuth();
  const location = useLocation();
  if (loading) return <Loading label="Checking your role" rows={0} />;
  if (!user) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  }
  if (!isStaff) return <Navigate to="/portal" replace />;
  return children;
}

function NotFound() {
  return (
    <section className="section not-found">
      <span className="mono-note">404 / OFF THE MAP</span>
      <h1>
        This page is not
        <br />
        <em>in the programme.</em>
      </h1>
      <p>The link may be old, or the event may have moved in the catalogue.</p>
      <div className="hero-actions">
        <Button to="/" icon={ArrowUpRight}>
          Back to the convention
        </Button>
        <Button to="/events" variant="ghost">
          Browse events
        </Button>
      </div>
    </section>
  );
}

export default function App() {
  const { user, isStaff, loading: authLoading } = useAuth();
  const site = useSite();
  const [menu, setMenu] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const destroyLenis = initSmoothScroll();
    return () => {
      if (typeof destroyLenis === 'function') destroyLenis();
    };
  }, []);

  useEffect(() => {
    setMenu(false);
  }, [location.pathname]);

  const chromeHidden = location.pathname.startsWith('/manage') || location.pathname === '/login';
  const [booted, setBooted] = useState(() => {
    try {
      return Boolean(sessionStorage.getItem('px_booted'));
    } catch {
      return false;
    }
  });

  const isReady = Boolean(!site.loading && site.edition);

  if (!booted && location.pathname === '/') {
    return (
      <SamaritanBootLoader
        isReady={isReady}
        onComplete={() => {
          try { sessionStorage.setItem('px_booted', '1'); } catch {}
          setBooted(true);
        }}
      />
    );
  }

  // The boot animation already waits for isReady before completing.
  // On inner-page navigations we still need to wait for the site data.
  if (site.loading && !site.edition) {
    return <Loading label="Connecting to Parallax convention…" rows={0} />;
  }

  if (site.error && !site.edition) {
    return (
      <div className="boot boot-error">
        <img src={LOGO} alt="Parallax" />
        <ErrorBox
          error={site.error}
          title="The convention service is not reachable"
          onRetry={site.refresh}
        />
        <p className="muted">
          Please check your connection and retry. The site needs the
          edition record before it can render.
        </p>
      </div>
    );
  }

  return (
    <>
      <ScrollToTop />
      
      <a className="skip" href="#main">
        Skip to content
      </a>
      {!chromeHidden ? (
        <header className="nav">
          <Link to="/" className="brand" aria-label={`${site.edition?.name || 'Parallax 2026'} home`}>
            <img src={ISTE} alt="ISTE" className="brand-logo-iste" />
            <span className="brand-divider" aria-hidden="true">|</span>
            <img src={LOGO} alt={site.edition?.name || 'Parallax 2026'} className="brand-logo" />
          </Link>
          <button
            className="menu-toggle"
            onClick={() => setMenu((value) => !value)}
            aria-label={menu ? 'Close navigation' : 'Open navigation'}
            aria-expanded={menu}
          >
            {menu ? <X size={20} strokeWidth={1.6} /> : <Menu size={20} strokeWidth={1.6} />}
          </button>
          <nav className={menu ? 'links open' : 'links'} aria-label="Main navigation">
            {PUBLIC_NAV.map(([label, to]) => (
              <Link
                key={to}
                to={to}
                className={location.pathname === to || location.pathname.startsWith(`${to}/`) ? 'active' : ''}
              >
                {label}
              </Link>
            ))}
            <Link className="portal-link" to={user ? (isStaff ? '/manage' : '/portal') : '/login'}>
              <span>{authLoading ? 'Portal' : user ? (isStaff ? 'Console' : 'My portal') : 'Sign in'}</span>
              <span className="portal-link-icon"><ArrowUpRight size={13} strokeWidth={2.4} /></span>
            </Link>
          </nav>
        </header>
      ) : null}

      <main id="main">
        <AppErrorBoundary key={location.pathname}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/about" element={<About />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/events/:eventSlug" element={<EventDetail />} />
          <Route path="/pass" element={<PassPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/venue" element={<VenuePage />} />
          <Route path="/faq" element={<FAQPage />} />
          <Route path="/contact" element={<ContactPage />} />
          <Route path="/team" element={<TeamPage />} />

          <Route path="/login" element={<Login />} />

          <Route
            path="/portal"
            element={
              <RequireAuth>
                <PortalLayout />
              </RequireAuth>
            }
          >
            <Route index element={<PortalOverview />} />
            <Route path="pass" element={<PortalPass />} />
            <Route path="select-events" element={<PortalSelectEvents />} />
            <Route path="registrations" element={<PortalRegistrations />} />
            <Route path="tickets" element={<PortalTickets />} />
            <Route path="teams" element={<PortalTeams />} />
            <Route path="verification" element={<PortalVerification />} />
            <Route path="profile" element={<PortalProfile />} />
          </Route>

          <Route
            path="/manage"
            element={
              <RequireStaff>
                <AdminLayout />
              </RequireStaff>
            }
          >
            <Route index element={<AdminOverview />} />
            <Route path="events" element={<AdminEvents />} />
            <Route path="registrations" element={<AdminRegistrations />} />
            <Route path="attendance" element={<AdminAttendance />} />
            <Route path="check-in" element={<AdminCheckin />} />
            <Route path="checkin" element={<AdminCheckin />} />
            <Route path="policy" element={<AdminPolicy />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="verifications" element={<AdminVerifications />} />
            <Route path="payments" element={<AdminPayments />} />
            <Route path="announcements" element={<AdminAnnouncements />} />
            <Route path="audit" element={<AdminAudit />} />
            <Route path="settings" element={<AdminSettings />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
        </AppErrorBoundary>
      </main>

      {!chromeHidden ? <Footer edition={site.edition} /> : null}
      <ThemeCustomizer />
    </>
  );
}
