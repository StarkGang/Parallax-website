import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter, Link, useLocation, useParams } from 'react-router-dom';
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  Menu,
  X,
  MapPin,
  CalendarDays,
  Users,
  Ticket,
  Search,
  SlidersHorizontal,
  Clock3,
  ShieldCheck,
  Mail,
  Camera,
  AtSign,
  Plus,
  RotateCcw,
} from 'lucide-react';
import { convention as c } from './config/convention.config.js';
import { events } from './data/events.js';
import { publicNavigation, portalNavigation } from './data/navigation.js';
import { formatPrice, checkIncludedSelection, addonTotal } from './utils/pricing.js';
import { canIncludeEvent } from './utils/eventEligibility.js';
import './style.css';
function App() {
  const [menu, setMenu] = useState(false),
    [modal, setModal] = useState('');
  const loc = useLocation();
  useEffect(() => {
    setMenu(false);
    window.scrollTo(0, 0);
  }, [loc.pathname]);
  const path = loc.pathname;
  const action = (s) => setModal(s);
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="nav">
        <Link to="/" className="brand">
          <img
            src={`${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/Parallax Logo.png`}
            alt="PARALLAX"
          />
          <span>ISTE STATE STUDENT CONVENTION</span>
        </Link>
        <button
          className="menu-toggle"
          onClick={() => setMenu(!menu)}
          aria-label={menu ? 'Close navigation' : 'Open navigation'}
          aria-expanded={menu}
        >
          {menu ? <X /> : <Menu />}
        </button>
        <nav className={menu ? 'links open' : 'links'} aria-label="Main navigation">
          {publicNavigation.map(([n, p]) => (
            <Link className={path === p ? 'active' : ''} key={p} to={p}>
              {n}
            </Link>
          ))}
          <Link className="portal-link" to="/portal">
            Participant portal <ArrowUpRight size={15} />
          </Link>
        </nav>
      </header>
      <main id="main">
        {path === '/' ? (
          <Home action={action} />
        ) : path === '/about' ? (
          <About />
        ) : path === '/events' ? (
          <EventsPage />
        ) : path.startsWith('/events/') ? (
          <EventDetail />
        ) : path === '/pass' ? (
          <PassPage />
        ) : path === '/schedule' ? (
          <Schedule />
        ) : path === '/venue' ? (
          <Venue action={action} />
        ) : path === '/faq' ? (
          <FAQ />
        ) : path === '/contact' ? (
          <Contact action={action} />
        ) : path === '/portal' ? (
          <Portal />
        ) : path === '/portal/select-events' ? (
          <SelectEvents action={action} />
        ) : path === '/portal/registrations' ? (
          <Registrations />
        ) : path === '/portal/profile' ? (
          <Profile action={action} />
        ) : path === '/manage' ? (
          <Manage action={action} />
        ) : (
          <Home action={action} />
        )}
      </main>
      <Footer />
      <Modal message={modal} close={() => setModal('')} />
    </>
  );
}
function Eyebrow({ children }) {
  return (
    <div className="eyebrow">
      <span />
      {children}
    </div>
  );
}
function Title({ kicker, title, desc }) {
  return (
    <section className="page-title">
      <Eyebrow>{kicker}</Eyebrow>
      <h1>{title}</h1>
      {desc && <p>{desc}</p>}
    </section>
  );
}
function Home({ action }) {
  return (
    <>
      <section className="hero">
        <div className="hero-grid" />
        <div className="hero-copy">
          <Eyebrow>ISTE STATE STUDENT CONVENTION · {c.city.toUpperCase()}</Eyebrow>
          <h1>
            PARA<span>LL</span>AX<span className="period">.</span>
          </h1>
          <h2>{c.tagline}</h2>
          <p className="hero-description">
            Two days of ideas, making and new perspectives. Join the student community at NSS
            College of Engineering, Palakkad.
          </p>
          <div className="hero-actions">
            <Link className="button primary" to="/events">
              Explore events <ArrowRight size={17} />
            </Link>
            <Link className="button ghost" to="/pass">
              Understand the pass <ArrowDownRight size={16} />
            </Link>
          </div>
          <div className="hero-note">
            <span className="pulse" /> {c.taglineStatus}
          </div>
        </div>
        <div className="hero-art">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit orbit-three" />
          <img
            src={`${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/modified assets/globe.svg`}
            alt=""
          />
          <div className="art-label">
            <span>01 / 02</span>
            <b>
              SEE BEYOND
              <br />
              THE OBVIOUS
            </b>
          </div>
          <span className="art-cross">✳</span>
        </div>
        <div className="hero-foot">
          <span>
            <MapPin size={15} /> NSS College of Engineering
          </span>
          <span>
            <CalendarDays size={15} /> Dates to be announced
          </span>
          <span>
            Scroll to explore <ArrowDownRight size={15} />
          </span>
        </div>
      </section>
      <section className="intro section">
        <div>
          <Eyebrow>THE CONVENTION</Eyebrow>
          <h2>
            One gathering.
            <br />
            <em>Many perspectives.</em>
          </h2>
        </div>
        <div className="intro-text">
          <p>
            PARALLAX is a proposed two-day ISTE state student convention hosted by NSS College of
            Engineering. A place to explore technology, build together and share ideas across
            disciplines.
          </p>
          <Link className="text-link" to="/about">
            Get to know Parallax <ArrowRight size={16} />
          </Link>
        </div>
      </section>
      <section className="pass-strip">
        <div className="pass-orbit">
          ₹<b>500</b>
        </div>
        <div>
          <Eyebrow>ONE PASS · TWO DAYS</Eyebrow>
          <h2>Your convention starts here.</h2>
          <p>
            Every participant needs a ₹500 pass. It includes lunch both days and lets you choose up
            to {c.includedEventCount} eligible events within an illustrative{' '}
            {formatPrice(c.includedEventValueCap)} base-value cap.
          </p>
        </div>
        <Link className="button light" to="/pass">
          See how it works <ArrowRight size={16} />
        </Link>
      </section>
      <section className="section event-section">
        <div className="section-heading">
          <div>
            <Eyebrow>MAKE YOUR MOVE</Eyebrow>
            <h2>Find your kind of challenge.</h2>
          </div>
          <Link className="text-link" to="/events">
            All events <ArrowRight size={16} />
          </Link>
        </div>
        <div className="event-grid">
          {events
            .filter((e) => e.featured)
            .map((e, i) => (
              <EventCard key={e.id} event={e} index={i} />
            ))}
        </div>
      </section>
      <section className="facts section">
        <div className="fact">
          <span>01 — FORMAT</span>
          <b>
            Individual
            <br />& team events
          </b>
        </div>
        <div className="fact">
          <span>02 — DURATION</span>
          <b>
            Two days
            <br />
            together
          </b>
        </div>
        <div className="fact">
          <span>03 — WHEN</span>
          <b>
            Dates to be
            <br />
            announced
          </b>
        </div>
        <div className="fact">
          <span>04 — WHO</span>
          <b>
            Student innovators
            <br />
            across Kerala
          </b>
        </div>
      </section>
      <section className="cta section">
        <div className="cta-mark">
          P<span>.</span>
        </div>
        <Eyebrow>YOUR NEXT PERSPECTIVE</Eyebrow>
        <h2>
          Make room for
          <br />
          <em>what’s next.</em>
        </h2>
        <Link className="button primary" to="/portal">
          Preview participant portal <ArrowRight size={16} />
        </Link>
      </section>
    </>
  );
}
function EventCard({ event, index = 0 }) {
  return (
    <Link to={`/events/${event.slug}`} className="event-card">
      <div className="card-top">
        <span>0{index + 1}</span>
        <ArrowUpRight size={19} />
      </div>
      <div className="event-symbol">
        {event.category === 'Computing'
          ? '⌘'
          : event.category === 'Design'
            ? '◈'
            : event.category === 'Robotics'
              ? '⟲'
              : '✳'}
      </div>
      <div className="event-meta">
        {event.category} <span>·</span> {event.format}
      </div>
      <h3>{event.title}</h3>
      <p>{event.summary}</p>
      <div className="card-bottom">
        <span>
          Included value <b>{formatPrice(event.baseValue)}</b>
        </span>
        <span>
          Add-on <b>{formatPrice(event.addonPrice)}</b>
        </span>
      </div>
    </Link>
  );
}
function About() {
  return (
    <>
      <Title
        kicker="ABOUT PARALLAX"
        title={
          <>
            A different angle
            <br />
            <em>changes everything.</em>
          </>
        }
        desc="PARALLAX is a proposed two-day student convention built around new ideas, shared skills and hands-on exploration."
      />
      <section className="section prose-grid">
        <article>
          <Eyebrow>THE IDEA</Eyebrow>
          <h2>Curiosity brings us together.</h2>
          <p>
            Named for the shift in perspective created by a change in viewpoint, PARALLAX invites
            students to look at technology and engineering from many angles. The convention is
            planned by the ISTE student community and hosted at NSS College of Engineering,
            Palakkad.
          </p>
          <p>
            Its program is being developed. Event details, dates, eligibility and registration
            policies remain subject to organizer approval.
          </p>
        </article>
        <article className="host-card">
          <img
            src={`${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/NSSCE-Palakkad-Logo.webp`}
            alt="NSS College of Engineering emblem"
          />
          <Eyebrow>HOST INSTITUTION</Eyebrow>
          <h3>{c.host}</h3>
          <p>{c.city}</p>
          <div className="host-rule" />
          <p>
            Hosted by the ISTE student community. Official chapter details and approved marks will
            be finalized by organizers.
          </p>
        </article>
      </section>
    </>
  );
}
function EventsPage() {
  const [q, setQ] = useState(''),
    [cat, setCat] = useState('All'),
    [fmt, setFmt] = useState('All');
  const cats = ['All', ...new Set(events.map((e) => e.category))];
  const filtered = events.filter(
    (e) =>
      (cat === 'All' || e.category === cat) &&
      (fmt === 'All' || e.format === fmt) &&
      `${e.title} ${e.summary}`.toLowerCase().includes(q.toLowerCase()),
  );
  return (
    <>
      <Title
        kicker="EVENT DIRECTORY"
        title={
          <>
            Choose your
            <br />
            <em>next challenge.</em>
          </>
        }
        desc="Explore the demo program. All event details and fees are illustrative and need organizer approval."
      />
      <section className="section directory">
        <div className="filters">
          <label className="search">
            <Search size={18} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search events"
              aria-label="Search events"
            />
          </label>
          <label className="filter-label">
            <SlidersHorizontal size={16} />
            <select
              value={cat}
              onChange={(e) => setCat(e.target.value)}
              aria-label="Filter by category"
            >
              {cats.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <label className="filter-label">
            <Users size={16} />
            <select
              value={fmt}
              onChange={(e) => setFmt(e.target.value)}
              aria-label="Filter by format"
            >
              {['All', 'individual', 'team'].map((x) => (
                <option key={x} value={x}>
                  {x === 'All' ? 'All formats' : x}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="results-note">
          {filtered.length} demo events <span>·</span> registration availability is not live
        </div>
        {filtered.length ? (
          <div className="event-grid">
            {filtered.map((e, i) => (
              <EventCard key={e.id} event={e} index={i} />
            ))}
          </div>
        ) : (
          <div className="empty">
            <Search />
            <h3>No matching events</h3>
            <p>Try another search or category.</p>
          </div>
        )}
        <p className="notice">
          <ShieldCheck size={16} /> Student eligibility will be verified in a future registration
          system. This preview does not verify students.
        </p>
      </section>
    </>
  );
}
function EventDetail() {
  const { slug } = useParams(),
    event = events.find((x) => x.slug === slug);
  if (!event) return <Title kicker="EVENT" title="Event not found" />;
  return (
    <>
      <Title
        kicker={`${event.category.toUpperCase()} · ${event.format.toUpperCase()}`}
        title={
          <>
            {event.title}
            <br />
            <em>See what’s possible.</em>
          </>
        }
        desc={event.description}
      />
      <section className="section detail-grid">
        <article className="detail-main">
          <Eyebrow>ABOUT THIS EVENT</Eyebrow>
          <h2>A demo brief, ready for review.</h2>
          <p>{event.description}</p>
          <h3>Requirements & rules</h3>
          <ul>
            {event.rules.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
          <p className="notice">
            <ShieldCheck size={16} />
            {event.eligibility}
          </p>
        </article>
        <aside className="detail-card">
          <div className="detail-row">
            <span>Format</span>
            <b>{event.format}</b>
          </div>
          {event.format === 'team' && (
            <div className="detail-row">
              <span>Team size (demo)</span>
              <b>
                {event.teamMin}–{event.teamMax} members
              </b>
            </div>
          )}
          <div className="detail-row">
            <span>Included base value</span>
            <b>{formatPrice(event.baseValue)}</b>
          </div>
          <div className="detail-row">
            <span>Standalone add-on fee</span>
            <b>{formatPrice(event.addonPrice)}</b>
          </div>
          <div className="detail-row">
            <span>Included selection</span>
            <b>{canIncludeEvent(event, c) ? 'Eligible, subject to cap' : 'Not eligible'}</b>
          </div>
          <div className="detail-row">
            <span>Schedule / venue</span>
            <b>
              {event.schedule} · {event.venue}
            </b>
          </div>
          <p>
            Convention pass of {formatPrice(c.passPrice)} is required independently for every
            participant.
          </p>
          <Link className="button primary full" to="/portal/select-events">
            Preview event selection <ArrowRight size={16} />
          </Link>
        </aside>
      </section>
    </>
  );
}
function PassPage() {
  return (
    <>
      <Title
        kicker="CONVENTION PASS"
        title={
          <>
            One pass. Two days.
            <br />
            <em>Your event choices.</em>
          </>
        }
        desc="The convention pass and event-selection allowance are separate parts of the pricing model."
      />
      <section className="section pass-layout">
        <article className="price-card">
          <span>MANDATORY · PER PARTICIPANT</span>
          <strong>{formatPrice(c.passPrice)}</strong>
          <p>Parallax Convention Pass</p>
          <div className="price-rule" />
          <p>
            <Check /> Lunch on both convention days
          </p>
          <p>
            <Check /> {c.selectionMode === 'exact' ? 'Exactly' : 'Up to'} {c.includedEventCount}{' '}
            eligible event choices
          </p>
          <p>
            <Check /> Subject to the included-event base-value cap
          </p>
          <Link className="button primary full" to="/portal">
            Preview participant portal <ArrowRight size={16} />
          </Link>
          <small>Demo only — payment integration not connected</small>
        </article>
        <article className="pass-copy">
          <Eyebrow>HOW PRICING WORKS</Eyebrow>
          <h2>
            Pass first.
            <br />
            <em>Then pick your program.</em>
          </h2>
          <ol>
            <li>
              <b>Every participant gets a ₹500 pass.</b>
              <p>It is mandatory and includes lunch on both days.</p>
            </li>
            <li>
              <b>
                Choose {c.selectionMode === 'exact' ? 'exactly' : 'up to'} {c.includedEventCount}{' '}
                eligible events.
              </b>
              <p>
                The sum of their published base values must be at or under the configured cap. The
                pass price is not added to this sum.
              </p>
            </li>
            <li>
              <b>Add extra events separately.</b>
              <p>
                Additional event registrations use each event’s standalone add-on fee, after the
                mandatory pass.
              </p>
            </li>
            <li>
              <b>Team members each need a pass.</b>
              <p>
                Every team member must hold their own valid convention pass before a team
                registration can be confirmed.
              </p>
            </li>
          </ol>
          <div className="cap-callout">
            <span>INCLUDED EVENT VALUE CAP</span>
            <b>
              {formatPrice(c.includedEventValueCap)} <small>illustrative only</small>
            </b>
            <p>{c.capStatus}. The planning discussion mentions ₹400 or ₹450.</p>
          </div>
        </article>
      </section>
    </>
  );
}
function Schedule() {
  return (
    <>
      <Title
        kicker="THE PROGRAM"
        title={
          <>
            Two days of
            <br />
            <em>new perspectives.</em>
          </>
        }
        desc="A planning outline only. Dates, session times and rooms are not confirmed."
      />
      <section className="section schedule-grid">
        {[1, 2].map((d) => (
          <article className="day-card" key={d}>
            <span>DAY 0{d}</span>
            <h2>Dates to be announced</h2>
            <div className="schedule-row">
              <Clock3 />
              <div>
                <b>Program schedule</b>
                <p>Session details to be announced</p>
              </div>
            </div>
            <div className="schedule-row">
              <MapPin />
              <div>
                <b>Venue</b>
                <p>{c.host} · room to be announced</p>
              </div>
            </div>
            <div className="day-art">0{d}</div>
          </article>
        ))}
      </section>
    </>
  );
}
function Venue({ action }) {
  return (
    <>
      <Title
        kicker="THE VENUE"
        title={
          <>
            Meet us in
            <br />
            <em>Palakkad.</em>
          </>
        }
        desc="The proposed host venue is NSS College of Engineering, Palakkad, Kerala, India."
      />
      <section className="section venue-grid">
        <article className="venue-visual">
          <div className="map-rings" />
          <MapPin size={40} />
          <span>
            10.8Â° N · 76.6Â° E<br />
            Illustrative map graphic
          </span>
        </article>
        <article className="venue-copy">
          <Eyebrow>HOST CAMPUS</Eyebrow>
          <h2>{c.host}</h2>
          <p>{c.city}</p>
          <p>
            Campus address, access details, accommodation guidance and transport information will be
            published after organizer confirmation. No transport arrangement is confirmed.
          </p>
          <div className="detail-row">
            <span>Dates</span>
            <b>To be announced</b>
          </div>
          <div className="detail-row">
            <span>Rooms</span>
            <b>To be announced</b>
          </div>
          <button
            className="button ghost"
            onClick={() => action('Demo only — an approved venue map link has not been supplied.')}
          >
            Map link pending
          </button>
        </article>
      </section>
    </>
  );
}
function FAQ() {
  const rows = [
    [
      'Is the ₹500 pass mandatory?',
      'Yes. Every participant needs their own convention pass. Event add-on fees do not replace the pass.',
    ],
    [
      'What does the pass include?',
      'Lunch on both days and an included-event selection allowance.',
    ],
    [
      'How many included events can I select?',
      `The demo uses ${c.selectionMode === 'exact' ? 'exactly' : 'up to'} ${c.includedEventCount}. The final count and selection mode are awaiting approval.`,
    ],
    [
      'What is the included-event cap?',
      'The demo illustrates ₹450. This is not final; the current discussion mentions ₹400 or ₹450.',
    ],
    [
      'Can I register for more events?',
      'Yes. Additional events have a separate published add-on fee, after obtaining the convention pass.',
    ],
    [
      'How does the team pass rule work?',
      'Each team member must have their own valid convention pass before the team can be confirmed.',
    ],
    [
      'Does the site verify student status?',
      'No. This prototype shows demo-only verification. Production eligibility checks are not connected.',
    ],
    [
      'Can I pay or request a refund here?',
      'No. Payment is not connected and no financial data is collected. Cancellation and refund policies are awaiting organizer approval.',
    ],
    [
      'Is lunch included?',
      'The proposed ₹500 pass includes lunch on both convention days. Final arrangements await confirmation.',
    ],
  ];
  return (
    <>
      <Title
        kicker="GOOD TO KNOW"
        title={
          <>
            Questions, meet
            <br />
            <em>clear answers.</em>
          </>
        }
        desc="Policies shown here are proposals for committee review, not final terms."
      />
      <section className="section faq-list">
        {rows.map(([q, a], i) => (
          <details key={q}>
            <summary>
              <span>0{i + 1}</span>
              {q}
              <ChevronDown size={19} />
            </summary>
            <p>{a}</p>
          </details>
        ))}
      </section>
    </>
  );
}
function Contact({ action }) {
  return (
    <>
      <Title
        kicker="CONTACT"
        title={
          <>
            Let’s get
            <br />
            <em>in touch.</em>
          </>
        }
        desc="Organizer contact details will be added when confirmed."
      />
      <section className="section contact-card">
        <Mail size={24} />
        <div>
          <span>OFFICIAL ISTE EMAIL</span>
          <h2>{c.officialEmail}</h2>
          <p>Placeholder — not a working contact address.</p>
        </div>
        <button
          className="button ghost"
          onClick={() =>
            action('Demo only — the official ISTE contact address has not been supplied.')
          }
        >
          Contact details pending
        </button>
      </section>
    </>
  );
}
function Portal() {
  return (
    <>
      <Title
        kicker="PARTICIPANT PORTAL · PROTOTYPE PREVIEW"
        title={
          <>
            Your convention,
            <br />
            <em>at a glance.</em>
          </>
        }
        desc="Demo participant · no account, verification or registration is real."
      />
      <section className="section portal-layout">
        <aside className="portal-side">
          <div className="avatar">DP</div>
          <h3>Demo Participant</h3>
          <p>Example Engineering College</p>
          <span className="pill">Demo only · not verified</span>
          <nav>
            {portalNavigation.map(([t, p]) => (
              <Link key={p} to={p}>
                {t}
                <ArrowRight size={15} />
              </Link>
            ))}
            <Link to="/manage">
              Coordinator preview
              <ArrowUpRight size={15} />
            </Link>
          </nav>
        </aside>
        <article className="portal-main">
          <div className="portal-banner">
            <Eyebrow>YOUR PASS</Eyebrow>
            <h2>Not purchased</h2>
            <p>Payment isn’t connected in this prototype.</p>
            <Link className="button primary" to="/pass">
              Explore pass details <ArrowRight size={16} />
            </Link>
          </div>
          <div className="portal-stats">
            <div>
              <span>INCLUDED CHOICES</span>
              <b>0 / {c.includedEventCount}</b>
              <small>Demo selection</small>
            </div>
            <div>
              <span>SELECTED VALUE</span>
              <b>{formatPrice(0)}</b>
              <small>Cap {formatPrice(c.includedEventValueCap)} (illustrative)</small>
            </div>
            <div>
              <span>ADD-ON EVENTS</span>
              <b>0</b>
              <small>Pass required first</small>
            </div>
          </div>
          <div className="next-card">
            <h3>Start exploring</h3>
            <p>Choose demo events and see how the allowance works. Nothing is saved to a server.</p>
            <Link className="text-link" to="/portal/select-events">
              Open event selector <ArrowRight size={16} />
            </Link>
          </div>
        </article>
      </section>
    </>
  );
}
function SelectEvents({ action }) {
  const [selected, setSelected] = useState([]),
    [addons, setAddons] = useState([]);
  const eligible = events.filter((e) => e.baseValue <= c.includedEventValueCap);
  const check = checkIncludedSelection(selected, events);
  const toggle = (id) => {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    const result = checkIncludedSelection(next, events);
    if (result.capExceeded || result.countExceeded) {
      action(
        result.capExceeded
          ? 'That choice would exceed the illustrative included-event value cap.'
          : 'You’ve reached the configured included-event choice count.',
      );
      return;
    }
    setSelected(next);
  };
  return (
    <>
      <Title
        kicker="PARTICIPANT PORTAL · LOCAL DEMO"
        title={
          <>
            Build your
            <br />
            <em>event lineup.</em>
          </>
        }
        desc="Selections stay in this page only; no server saves them. Demo mode does not confirm registration."
      />
      <section className="section selector">
        <div className="selector-note">
          <Ticket />
          <p>
            Convention pass: <b>{formatPrice(c.passPrice)} per participant</b> · required
            independently. Lunch both days included. Cap {formatPrice(c.includedEventValueCap)}{' '}
            (illustrative). {c.selectionMode === 'exact' ? 'Exactly' : 'Up to'}{' '}
            {c.includedEventCount} events.
          </p>
        </div>
        <div className="selector-summary">
          <div>
            <span>INCLUDED SELECTED</span>
            <b>
              {check.count} / {c.includedEventCount}
            </b>
          </div>
          <div>
            <span>BASE VALUE TOTAL</span>
            <b>{formatPrice(check.value)}</b>
          </div>
          <div>
            <span>CAP ROOM</span>
            <b>{formatPrice(Math.max(0, check.remainingValue))}</b>
          </div>
          <button
            className="text-link"
            onClick={() => {
              setSelected([]);
              setAddons([]);
            }}
          >
            <RotateCcw size={15} /> Reset demo
          </button>
        </div>
        <h2>Eligible included events</h2>
        <p className="muted">
          Selection mode: {c.selectionMode === 'exact' ? 'exactly' : 'up to'} the configured count.
          Base values determine cap eligibility; add-on prices are separate.
        </p>
        <div className="choice-list">
          {eligible.map((e) => (
            <label className="choice" key={e.id}>
              <input
                type="checkbox"
                checked={selected.includes(e.id)}
                onChange={() => toggle(e.id)}
              />
              <span className="choice-check">
                {selected.includes(e.id) ? <Check size={15} /> : <Plus size={15} />}
              </span>
              <span className="choice-title">
                <b>{e.title}</b>
                <small>
                  {e.format} · {e.category}
                </small>
              </span>
              <span className="choice-price">
                Base {formatPrice(e.baseValue)}
                <small>Add-on {formatPrice(e.addonPrice)}</small>
              </span>
            </label>
          ))}
        </div>
        <div className="addon-box">
          <h2>Additional paid events</h2>
          <p>
            Each selected add-on is charged at its published event fee after the pass. It never
            replaces the pass.
          </p>
          {events
            .filter((e) => !selected.includes(e.id))
            .slice(0, 4)
            .map((e) => (
              <label key={e.id} className="addon-choice">
                <input
                  type="checkbox"
                  checked={addons.includes(e.id)}
                  onChange={() =>
                    setAddons(
                      addons.includes(e.id) ? addons.filter((x) => x !== e.id) : [...addons, e.id],
                    )
                  }
                />
                {e.title}
                <span>{formatPrice(e.addonPrice)}</span>
              </label>
            ))}
          <div className="addon-total">
            Pass <b>{formatPrice(c.passPrice)}</b>
            <span>+ add-ons</span>
            <b>{formatPrice(addonTotal(addons, events))}</b>
            <strong>Demo total {formatPrice(c.passPrice + addonTotal(addons, events))}</strong>
          </div>
          <p className="demo-label">
            Demo calculation only — payment and registration are not connected.
          </p>
        </div>
        <button
          className="button primary"
          onClick={() =>
            action(
              check.valid
                ? 'Demo only — your event choices are not saved to a server, and registration is not confirmed.'
                : `Select exactly ${c.includedEventCount} included events to continue.`,
            )
          }
        >
          Continue demo <ArrowRight size={16} />
        </button>
      </section>
    </>
  );
}
function Registrations() {
  return (
    <>
      <Title
        kicker="PARTICIPANT PORTAL · DEMO"
        title={
          <>
            My registrations
            <br />
            <em>preview.</em>
          </>
        }
        desc="These sample rows are not real bookings."
      />
      <section className="section registrations">
        {[
          ['Circuit Lab', 'Demo selection', 'Individual'],
          ['Future Builders', 'Draft preview', 'Team · 2–4'],
        ].map((r) => (
          <div className="registration-row" key={r[0]}>
            <span className="event-dot" />
            <div>
              <b>{r[0]}</b>
              <small>{r[2]}</small>
            </div>
            <span className="pill">{r[1]}</span>
          </div>
        ))}
        <p className="notice">No registration has been submitted or confirmed.</p>
      </section>
    </>
  );
}
function Profile({ action }) {
  return (
    <>
      <Title
        kicker="PARTICIPANT PORTAL · DEMO"
        title={
          <>
            Profile
            <br />
            <em>preview.</em>
          </>
        }
        desc="Example fields only. No account, personal information or documents are saved."
      />
      <section className="section profile-form">
        <label>
          Display name
          <input value="Demo Participant" readOnly />
        </label>
        <label>
          College
          <input value="Example Engineering College" readOnly />
        </label>
        <label>
          Student verification
          <input value="Demo only — not verified" readOnly />
        </label>
        <button
          className="button primary"
          onClick={() =>
            action('Demo only — authentication and student verification are not connected.')
          }
        >
          Preview verification <ArrowRight size={16} />
        </button>
      </section>
    </>
  );
}
function Manage({ action }) {
  return (
    <>
      <Title
        kicker="ADMIN / COORDINATOR · DEMO DATA"
        title={
          <>
            A clearer view
            <br />
            <em>of the program.</em>
          </>
        }
        desc="Visual management concept only. No changes persist and there are no real participants."
      />
      <section className="section manage">
        <div className="manage-stats">
          <div>
            <span>PLANNING CAPACITY</span>
            <b>500–1,000</b>
          </div>
          <div>
            <span>DEMO EVENTS</span>
            <b>{events.length}</b>
          </div>
          <div>
            <span>PASS PRICE</span>
            <b>{formatPrice(c.passPrice)}</b>
          </div>
          <div>
            <span>REGISTRATION</span>
            <b>Not connected</b>
          </div>
        </div>
        <h2>Event configuration preview</h2>
        <form
          className="manager-form"
          onSubmit={(e) => {
            e.preventDefault();
            action('Demo only — management changes are not saved.');
          }}
        >
          <label>
            Event name
            <input defaultValue="Circuit Lab" />
          </label>
          <label>
            Format
            <select defaultValue="individual">
              <option>individual</option>
              <option>team</option>
            </select>
          </label>
          <label>
            Category
            <input defaultValue="Engineering" />
          </label>
          <label>
            Base value (₹)
            <input type="number" defaultValue="100" />
          </label>
          <label>
            Additional fee (₹)
            <input type="number" defaultValue="150" />
          </label>
          <label>
            Team size
            <input defaultValue="1–1" />
          </label>
          <label>
            Capacity
            <input defaultValue="To be announced" />
          </label>
          <label>
            Eligibility
            <input defaultValue="Student status — future verification" />
          </label>
          <label>
            Registration status
            <select defaultValue="active">
              <option value="active">Active preview</option>
              <option value="inactive">Inactive preview</option>
            </select>
          </label>
          <button className="button ghost" type="submit">
            Preview save (not persisted)
          </button>
        </form>
        <div className="manage-table">
          <div className="table-head">
            <span>EVENT</span>
            <span>FORMAT / CATEGORY</span>
            <span>BASE / ADD-ON</span>
            <span>TEAM / CAPACITY</span>
            <span>STATUS</span>
            <span />
          </div>
          {events.map((e) => (
            <div className="table-row" key={e.id}>
              <b>{e.title}</b>
              <span>
                {e.format} · {e.category}
              </span>
              <span>
                {formatPrice(e.baseValue)} / {formatPrice(e.addonPrice)}
              </span>
              <span>
                {e.format === 'team' ? `${e.teamMin}–${e.teamMax}` : 'Individual'} · {e.capacity}
              </span>
              <span className="pill">Planning preview</span>
              <button
                aria-label={`Edit ${e.title} demo`}
                onClick={() => action('Demo only — management changes are not saved.')}
              >
                Edit
              </button>
            </div>
          ))}
        </div>
        <button
          className="button primary"
          onClick={() => action('Demo only — new event data is not saved.')}
        >
          Add event <Plus size={16} />
        </button>
      </section>
    </>
  );
}
function Footer() {
  return (
    <footer className="footer">
      <div className="footer-top">
        <Link to="/" className="footer-brand">
          PARALLAX<span>.</span>
        </Link>
        <p>
          A shift in perspective.
          <br />A leap in innovation.
        </p>
        <div className="footer-host">
          <img
            src={`${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/ISTE LOGO NO  BG PNG.png`}
            alt="ISTE emblem"
          />
          <span>
            Hosted by {c.host}
            <br />
            {c.city}
          </span>
        </div>
      </div>
      <div className="footer-links">
        {[...publicNavigation, ['Contact', '/contact'], ['Manage preview', '/manage']].map(
          ([t, p]) => (
            <Link key={p} to={p}>
              {t}
            </Link>
          ),
        )}
      </div>
      <div className="footer-bottom">
        <span>Â© PARALLAX · {c.organizer}</span>
        <span>Prototype only · dates, rules & pricing subject to approval</span>
        <span className="social">
          <span aria-label="Instagram link placeholder">
            <Camera size={16} />
          </span>
          <span aria-label="LinkedIn link placeholder">
            <AtSign size={16} />
          </span>
        </span>
      </div>
    </footer>
  );
}
function Modal({ message, close }) {
  useEffect(() => {
    if (!message) return;
    const fn = (e) => e.key === 'Escape' && close();
    window.addEventListener('keydown', fn);
    return () => window.removeEventListener('keydown', fn);
  }, [message]);
  if (!message) return null;
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <button className="modal-close" onClick={close} aria-label="Close">
          <X />
        </button>
        <Eyebrow>PROTOTYPE NOTICE</Eyebrow>
        <h2 id="modal-title">Demo mode</h2>
        <p>{message}</p>
        <button autoFocus className="button primary" onClick={close}>
          Got it
        </button>
      </section>
    </div>
  );
}
createRoot(document.getElementById('root')).render(
  <HashRouter>
    <App />
  </HashRouter>,
);
