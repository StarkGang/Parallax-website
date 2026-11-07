import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { ArrowUpRight, LogIn, Menu, X } from 'lucide-react';
import { useAuth } from './lib/auth.jsx';
import { useSite } from './lib/site.jsx';
import { AppErrorBoundary, Button, ErrorBox, Loading } from './components/ui.jsx';
import { initSmoothScroll, gsap } from './lib/motion.js';
import { SamaritanBootLoader } from './components/SamaritanBootLoader.jsx';
import MascotProvider from './components/mascot/MascotProvider.jsx';
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

const LOGO = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp`;
const ISTE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/Iste_logo.png`;

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

/**
 * Notched metal strip that runs under the link bar: two fixed corner hooks
 * plus a stretched middle segment, so the steps keep their depth while the
 * run scales with the bar.
 */
function NavStrip({ className = 'nav-strip' }) {
  return (
    <span className={className} aria-hidden="true">
      <svg
        className="nav-strip-corner is-left"
        viewBox="0 0 34 24"
        preserveAspectRatio="xMinYMid meet"
        focusable="false"
      >
        <path d="M0 0h7v6h27v8H7v8H0z" fill="currentColor" />
      </svg>
      <svg
        className="nav-strip-mid"
        viewBox="0 0 800 24"
        preserveAspectRatio="none"
        focusable="false"
      >
        <path
          d="M0 6h800v8H720v4H640v-4H560v4H480v-4H400v4H320v-4H240v4H160v-4H80v4H0z"
          fill="currentColor"
        />
      </svg>
      <svg
        className="nav-strip-corner is-right"
        viewBox="0 0 34 24"
        preserveAspectRatio="xMinYMid meet"
        focusable="false"
      >
        <path d="M0 0h7v6h27v8H7v8H0z" fill="currentColor" />
      </svg>
    </span>
  );
}

export default function App() {
  const { user, isStaff, loading: authLoading } = useAuth();
  const site = useSite();
  const [menu, setMenu] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const navSentinelRef = useRef(null);
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

  // The site scrolls through Lenis, so a sentinel (not window.scrollY) tells
  // us when the page has moved past the top 40px.
  useEffect(() => {
    const node = navSentinelRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(([entry]) => setScrolled(!entry.isIntersecting), {
      threshold: 0,
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!menu) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') setMenu(false);
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [menu]);

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
        <header className={`nav${scrolled ? ' is-scrolled' : ''}`}>
          <Link
            to="/"
            className="nav-logo"
            aria-label={`${site.edition?.name || 'Parallax 2026'} home`}
          >
            <img src={LOGO} alt={site.edition?.name || 'Parallax 2026'} />
          </Link>

          <nav className="nav-bar" aria-label="Main navigation">
            <span className="nav-fill" aria-hidden="true" />
            <span className="nav-wing is-left" aria-hidden="true" />
            <span className="nav-wing is-right" aria-hidden="true" />
            <ul className="nav-links">
              {PUBLIC_NAV.map(([label, to]) => {
                const isActive =
                  location.pathname === to || location.pathname.startsWith(`${to}/`);
                return (
                  <li key={to}>
                    <Link to={to} aria-current={isActive ? 'page' : undefined}>
                      {to === '/pass' ? <span className="nav-tag">One pass</span> : null}
                      <span>{label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
            <NavStrip />
          </nav>

          <Link
            className="nav-cta nav-cta-signin"
            to={user ? (isStaff ? '/manage' : '/portal') : '/login'}
          >
            <LogIn size={16} strokeWidth={1.8} aria-hidden="true" />
            <span>
              {authLoading ? 'Portal' : user ? (isStaff ? 'Console' : 'My portal') : 'Sign in'}
            </span>
          </Link>

          <Link className="nav-cta nav-cta-pass" to="/pass">
            <span>Get pass</span>
          </Link>

          <button
            type="button"
            className="nav-burger"
            onClick={() => setMenu((value) => !value)}
            aria-label={menu ? 'Close navigation' : 'Open navigation'}
            aria-expanded={menu}
            aria-controls="nav-overlay"
          >
            {menu ? <X size={20} strokeWidth={1.7} /> : <Menu size={20} strokeWidth={1.7} />}
          </button>
        </header>
      ) : null}

      {!chromeHidden ? (
        <span ref={navSentinelRef} className="nav-sentinel" aria-hidden="true" />
      ) : null}

      {!chromeHidden ? (
        <div className="nav-overlay" id="nav-overlay" hidden={!menu}>
          <div className="nav-overlay-head">
            <Link to="/" className="nav-logo" aria-label="Parallax 2026 home">
              <img src={LOGO} alt={site.edition?.name || 'Parallax 2026'} />
            </Link>
            <button
              type="button"
              className="nav-overlay-close"
              onClick={() => setMenu(false)}
              aria-label="Close navigation"
            >
              <X size={20} strokeWidth={1.7} />
            </button>
          </div>

          <NavStrip className="nav-overlay-strip" />

          <nav aria-label="Mobile navigation">
            <ul className="nav-overlay-links">
              {PUBLIC_NAV.map(([label, to]) => {
                const isActive =
                  location.pathname === to || location.pathname.startsWith(`${to}/`);
                return (
                  <li key={to}>
                    <Link
                      to={to}
                      aria-current={isActive ? 'page' : undefined}
                      onClick={() => setMenu(false)}
                    >
                      {label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          <Link
            className="nav-overlay-cta"
            to={user ? (isStaff ? '/manage' : '/portal') : '/login'}
            onClick={() => setMenu(false)}
          >
            <span>{user ? (isStaff ? 'Open console' : 'My portal') : 'Sign in'}</span>
            <ArrowUpRight size={16} strokeWidth={2} aria-hidden="true" />
          </Link>
        </div>
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
      <MascotProvider />
    </>
  );
}
