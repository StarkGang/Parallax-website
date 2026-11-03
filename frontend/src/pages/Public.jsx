import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Boxes,
  CalendarDays,
  Check,
  Clock3,
  Code2,
  Cpu,
  Mail,
  MapPin,
  Navigation,
  PenTool,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Ticket,
  Users,
  Zap,
} from 'lucide-react';
import { publicApi } from '../lib/api.js';
import { useSite } from '../lib/site.jsx';
import {
  date,
  dateRange,
  dayLabel,
  money,
  time,
  weekday,
} from '../lib/format.js';
import {
  Badge,
  Button,
  Empty,
  ErrorBox,
  Eyebrow,
  Field,
  Loading,
  PageTitle,
  Panel,
  SectionHead,
  Stat,
  useAsync,
  useDebounced,
} from '../components/ui.jsx';

const LOGO = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.png`;
const GLOBE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/modified assets/globe.svg`;
const NSSCE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/NSSCE-Palakkad-Logo.webp`;
const ISTE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/ISTE LOGO NO  BG PNG.png`;

function CategoryIcon({ category, size = 30 }) {
  const cat = (category || '').toLowerCase();
  if (cat.includes('comp') || cat.includes('code') || cat.includes('hack') || cat.includes('data')) {
    return <Code2 size={size} strokeWidth={1.5} />;
  }
  if (cat.includes('elect') || cat.includes('circuit') || cat.includes('solder')) {
    return <Zap size={size} strokeWidth={1.5} />;
  }
  if (cat.includes('robot') || cat.includes('line') || cat.includes('maze')) {
    return <Bot size={size} strokeWidth={1.5} />;
  }
  if (cat.includes('desig') || cat.includes('cad')) {
    return <PenTool size={size} strokeWidth={1.5} />;
  }
  if (cat.includes('engin') || cat.includes('proj')) {
    return <Boxes size={size} strokeWidth={1.5} />;
  }
  return <Sparkles size={size} strokeWidth={1.5} />;
}

export function EventCard({ event, index = 0 }) {
  const capacity =
    event.seatsLeft === null || event.seatsLeft === undefined
      ? 'Open capacity'
      : `${event.seatsLeft} of ${event.capacity} left`;
  return (
    <Link
      to={`/events/${event.slug}`}
      className={`event-card accent-${event.accent || 'cyan'} rise`}
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <div className="card-top">
        <span>{String(index + 1).padStart(2, '0')}</span>
        <ArrowUpRight size={18} strokeWidth={1.4} />
      </div>
      <div className="event-symbol">
        {event.iconId ? (
          <img
            src={publicApi.iconUrl(event.iconId)}
            alt=""
            className="event-icon-img"
            loading="lazy"
          />
        ) : (
          <CategoryIcon category={event.categorySlug || event.categoryName} />
        )}
      </div>
      <div className="event-meta">
        {event.categoryName} <span>·</span> {event.format}
      </div>
      <h3>{event.title}</h3>
      <p>{event.summary}</p>
      <div className="card-bottom">
        <span>
          Included value <b>{money(event.baseValuePaise)}</b>
        </span>
        <span>
          Add-on <b>{money(event.addonPricePaise)}</b>
        </span>
      </div>
      <div className="card-foot">
        <span className="card-cap">{capacity}</span>
        <span className={`card-status-pill ${event.registrationOpen ? 'is-open' : 'is-closed'}`}>
          {event.registrationOpen ? 'Registration open' : 'Registration closed'}
        </span>
      </div>
    </Link>
  );
}

export function Home() {
  const { edition, policy, config } = useSite();
  const slug = edition?.slug;
  const featured = useAsync(
    () => publicApi.events(slug, { featured: true, pageSize: 6 }),
    [slug],
    { enabled: Boolean(slug) },
  );
  const fallbackEvents = useAsync(
    () => publicApi.events(slug, { pageSize: 6 }),
    [slug],
    {
      enabled: Boolean(
        slug &&
          featured.data !== null &&
          Array.isArray(featured.data?.data) &&
          featured.data.data.length === 0,
      ),
    },
  );
  const news = useAsync(() => publicApi.announcements(slug, { pageSize: 2 }), [slug], {
    enabled: Boolean(slug),
  });

  if (!edition) return null;
  const events =
    featured.data?.data && featured.data.data.length > 0
      ? featured.data.data
      : fallbackEvents.data?.data || [];
  const announcements = news.data?.data || [];
  const days = Math.max(
    1,
    Math.round(
      (new Date(edition.endsAt).setHours(23, 59) - new Date(edition.startsAt).setHours(0, 0)) /
        86_400_000,
    ),
  );

  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <div className="hero-brand-lockup">
            <h1 className="hero-logo-wrapper">
              <img src={LOGO} alt={`${edition.name} logo`} className="hero-main-logo" />
            </h1>
          </div>
          <Eyebrow>
            ISTE Student Chapter · NSSCE Palakkad
          </Eyebrow>
          <h2>
            {edition.tagline?.toLowerCase().includes('argued in public') ? (
              <>
                Two days of engineering,
                <br />
                <em>argued in public.</em>
              </>
            ) : (
              edition.tagline || edition.name
            )}
          </h2>
          <p className="hero-description">
            A single convention pass for all {days} days. Full floor access to every keynote,
            challenge, and workshop with zero gated tracks.
          </p>
          <div className="hero-actions">
            <Button to="/events" icon={ArrowRight}>
              Explore events
            </Button>
            <Button to="/pass" variant="ghost" icon={ArrowUpRight}>
              Understand the pass
            </Button>
          </div>
          <div className="hero-note">
            <span className={`hero-status-tag ${edition.registrationOpen ? 'is-open' : 'is-closed'}`}>
              {edition.registrationOpen ? 'Registration open' : 'Registration closed'}
            </span>
            <Link to="/portal" className="hero-portal-link">
              Participant portal <ArrowUpRight size={13} strokeWidth={1.5} />
            </Link>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit orbit-three" />
          <img src={GLOBE} alt="" />
          <div className="art-label">
            <span>{dateRange(edition.startsAt, edition.endsAt)}</span>
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
            <MapPin size={15} strokeWidth={1.5} /> {edition.host}
          </span>
          <span>
            <CalendarDays size={15} strokeWidth={1.5} />{' '}
            {dateRange(edition.startsAt, edition.endsAt)}
          </span>
          <span>
            <Users size={15} strokeWidth={1.5} /> {edition.city}
          </span>
        </div>
      </section>

      <section className="intro section">
        <div>
          <Eyebrow>The Convention</Eyebrow>
          <h2>
            One gathering.
            <br />
            <em>Many perspectives.</em>
          </h2>
        </div>
        <div className="intro-text">
          <p>
            {edition.name} is a {days}-day student convention hosted by {edition.host}. Every
            participant holds a single convention pass, then builds a programme from the published
            catalogue within one transparent allowance.
          </p>
          <Link className="text-link" to="/about">
            Get to know the edition <ArrowRight size={16} strokeWidth={1.5} />
          </Link>
        </div>
      </section>

      <section className="pass-strip">
        <div className="pass-orbit">
          <span>{money(policy?.passPricePaise)}</span>
        </div>
        <div>
          <h2>Your convention starts with one pass.</h2>
          <p>
            The pass includes lunch on {policy?.lunchIncludedDays?.length || 0} days and lets you
            pick {policy?.includedSelectionMode === 'exact' ? 'exactly' : 'up to'}{' '}
            {policy?.includedEventCount} included events within {money(policy?.includedValueCapPaise)} of
            published base value.
          </p>
        </div>
        <Button to="/pass" variant="light" icon={ArrowRight}>
          See how it works
        </Button>
      </section>

      <section className="section event-section">
        <SectionHead
          kicker="The Programme"
          title="Find your kind of challenge"
          action={
            <Link className="text-link" to="/events">
              All events <ArrowRight size={16} strokeWidth={1.5} />
            </Link>
          }
        />
        {(featured.loading && !events.length) || (fallbackEvents.loading && !events.length) ? (
          <Loading label="Loading the programme" rows={2} />
        ) : featured.error && fallbackEvents.error ? (
          <ErrorBox error={featured.error} onRetry={featured.reload} />
        ) : events.length ? (
          <div className="event-grid">
            {events.map((event, index) => (
              <EventCard key={event.id} event={event} index={index} />
            ))}
          </div>
        ) : (
          <Empty title="The programme is being published" desc="Featured events will appear here." />
        )}
      </section>

      <section className="facts section">
        <div className="fact">
          <span>01 / FORMAT</span>
          <b>
            Individual
            <br />& team events
          </b>
        </div>
        <div className="fact">
          <span>02 / DURATION</span>
          <b>
            {days} days
            <br />
            together
          </b>
        </div>
        <div className="fact">
          <span>03 / WHEN</span>
          <b>
            {date(edition.startsAt)}
            <br />
            {date(edition.endsAt)}
          </b>
        </div>
        <div className="fact">
          <span>04 / WHERE</span>
          <b>
            {edition.venue}
            <br />
            {edition.city}
          </b>
        </div>
      </section>

      {announcements.length ? (
        <section className="section news-section">
          <SectionHead kicker="Bulletin" title="From the organisers" />
          <div className="news-grid">
            {announcements.map((item, index) => (
              <Panel key={item.id} className="news-card rise" style={{ animationDelay: `${index * 80}ms` }}>
                <span className="mono-note">{date(item.publishedAt)}</span>
                <h3>{item.title}</h3>
                <div
                  className="rich-text"
                  dangerouslySetInnerHTML={{ __html: item.bodyHtml || item.bodyMd }}
                />
              </Panel>
            ))}
          </div>
        </section>
      ) : null}

      <section className="cta section">
        <div className="cta-mark" aria-hidden="true">
          <img src={LOGO} alt="" className="cta-logo-mark" />
        </div>
        <Eyebrow>Your Next Perspective</Eyebrow>
        <h2>
          Make room for
          <br />
          <em>what’s next.</em>
        </h2>
        <p className="cta-copy">
          {config?.paymentsEnabled
            ? 'Pay securely, choose your included events, and collect your entry ticket in the participant portal.'
            : 'Register online, select your events, and collect your verified convention entry ticket.'}
        </p>
        <Button to="/portal" icon={ArrowRight}>
          Enter the participant portal
        </Button>
      </section>
    </>
  );
}

export function About() {
  const { edition, policy } = useSite();
  return (
    <>
      <PageTitle
        kicker="About the Edition"
        title={
          <>
            A different angle
            <br />
            <em>changes everything.</em>
          </>
        }
        desc={`${edition.name} is a ${edition.organizer} convention hosted at ${edition.host}. The programme is published from a single live catalogue.`}
      />
      <section className="section prose-grid">
        <article>
          <Eyebrow>The Idea</Eyebrow>
          <h2>Curiosity brings us together.</h2>
          <p>
            Named for the shift in perspective created by a change in viewpoint, {edition.name}{' '}
            invites students to look at technology and engineering from many angles. The convention
            is planned by the {edition.organizer} and hosted at {edition.host}, {edition.city}.
          </p>
          <p>
            Every event in the catalogue is a real record in the convention database: title,
            category, format, schedule, capacity and fees all come from the same source the
            organisers edit.
          </p>
          <div className="about-facts">
            <div>
              <span>ORGANISER</span>
              <b>{edition.organizer}</b>
            </div>
            <div>
              <span>HOST</span>
              <b>{edition.host}</b>
            </div>
            <div>
              <span>VENUE</span>
              <b>{edition.venue}</b>
            </div>
            <div>
              <span>DATES</span>
              <b>{dateRange(edition.startsAt, edition.endsAt)}</b>
            </div>
          </div>
        </article>
        <article className="host-card">
          <img src={NSSCE} alt={`${edition.host} emblem`} />
          <Eyebrow>Host Institution</Eyebrow>
          <h3>{edition.host}</h3>
          <p>{edition.city}</p>
          <div className="host-rule" />
          <p>
            Convention pass: {money(policy?.passPricePaise)} per participant, including lunch on{' '}
            {policy?.lunchIncludedDays?.length || 0} days.
          </p>
        </article>
      </section>
    </>
  );
}

export function EventsPage() {
  const { edition, slug } = useSite();
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query);
  const [category, setCategory] = useState('');
  const [format, setFormat] = useState('');
  const [page, setPage] = useState(1);

  const categories = useAsync(() => publicApi.categories(slug), [slug], { enabled: Boolean(slug) });
  const list = useAsync(
    () =>
      publicApi.events(slug, {
        q: debounced,
        category,
        format,
        page,
        pageSize: 9,
      }),
    [slug, debounced, category, format, page],
    { enabled: Boolean(slug) },
  );

  useEffect(() => {
    setPage(1);
  }, [debounced, category, format]);

  const events = list.data?.data || [];
  const meta = list.data?.meta || { total: 0, page: 1, pageSize: 9 };
  const lastPage = Math.max(1, Math.ceil((meta.total || 0) / (meta.pageSize || 9)));

  return (
    <>
      <PageTitle
        kicker="Event Directory"
        title={
          <>
            Choose your
            <br />
            <em>next challenge.</em>
          </>
        }
        desc="Search the live catalogue. Fees, formats, capacity and registration state come straight from the convention database."
      />
      <section className="section directory">
        <div className="filters">
          <label className="search">
            <Search size={18} strokeWidth={1.5} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search events"
              aria-label="Search events"
            />
          </label>
          <label className="filter-label">
            <SlidersHorizontal size={16} strokeWidth={1.5} />
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              aria-label="Filter by category"
            >
              <option value="">All categories</option>
              {(categories.data?.data || []).map((item) => (
                <option key={item.id} value={item.slug}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="filter-label">
            <Users size={16} strokeWidth={1.5} />
            <select
              value={format}
              onChange={(event) => setFormat(event.target.value)}
              aria-label="Filter by format"
            >
              <option value="">All formats</option>
              <option value="individual">Individual</option>
              <option value="team">Team</option>
            </select>
          </label>
        </div>
        <div className="results-note">
          {meta.total} {meta.total === 1 ? 'event' : 'events'}
          <span>·</span>
          {edition?.registrationOpen ? 'registration open' : 'registration closed'}
          <span>·</span>
          page {meta.page} of {lastPage}
        </div>
        {list.loading ? (
          <Loading label="Loading the catalogue" rows={2} />
        ) : list.error ? (
          <ErrorBox error={list.error} onRetry={list.reload} />
        ) : events.length ? (
          <>
            <div className="event-grid">
              {events.map((event, index) => (
                <EventCard key={event.id} event={event} index={index} />
              ))}
            </div>
            {lastPage > 1 ? (
              <div className="pager">
                <Button
                  variant="ghost"
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                  disabled={page <= 1}
                >
                  Previous
                </Button>
                <span className="mono-note">
                  {page} / {lastPage}
                </span>
                <Button
                  variant="ghost"
                  onClick={() => setPage((value) => Math.min(lastPage, value + 1))}
                  disabled={page >= lastPage}
                >
                  Next
                </Button>
              </div>
            ) : null}
          </>
        ) : (
          <Empty title="No matching events" desc="Try another search term or filter.">
            <Button
              variant="ghost"
              onClick={() => {
                setQuery('');
                setCategory('');
                setFormat('');
              }}
            >
              Clear filters
            </Button>
          </Empty>
        )}
        <p className="notice">
          <ShieldCheck size={16} strokeWidth={1.5} /> Student eligibility is verified in the
          participant portal, either by roster match, institutional email or a reviewed document.
        </p>
      </section>
    </>
  );
}

export function EventDetail() {
  const { slug } = useSite();
  const { eventSlug } = useParams();
  const detail = useAsync(() => publicApi.event(slug, eventSlug), [slug, eventSlug], {
    enabled: Boolean(slug && eventSlug),
  });

  if (detail.loading) {
    return (
      <section className="section">
        <Loading label="Loading event" rows={3} />
      </section>
    );
  }
  if (detail.error) {
    return (
      <section className="section">
        <ErrorBox error={detail.error} onRetry={detail.reload} title="Event not found" />
        <div className="center-actions">
          <Button to="/events" variant="ghost">
            Back to events
          </Button>
        </div>
      </section>
    );
  }

  const event = detail.data?.data;
  if (!event) {
    return (
      <section className="section not-found">
        <span className="mono-note">404 / OFF THE MAP</span>
        <h1>
          This event is not
          <br />
          <em>in the programme.</em>
        </h1>
        <p>
          The event may have been removed or moved in the catalogue.
        </p>
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

  return (
    <>
      <PageTitle
        kicker={`${event.categoryName.toUpperCase()} · ${event.format.toUpperCase()}`}
        title={event.title}
        desc={event.summary}
        aside={
          <div className="title-badges">
            <Badge tone={event.registrationOpen ? 'good' : 'muted'}>
              {event.registrationOpen ? 'Registration open' : 'Registration closed'}
            </Badge>
            {event.isFeatured ? <Badge tone="accent">Featured</Badge> : null}
          </div>
        }
      />
      <section className="section detail-grid">
        <article className="detail-main">
          <Eyebrow>About this Event</Eyebrow>
          <h2>{event.title}</h2>
          {event.descriptionHtml ? (
            <div className="rich-text" dangerouslySetInnerHTML={{ __html: event.descriptionHtml }} />
          ) : (
            <p>{event.summary}</p>
          )}
          {event.rulesHtml ? (
            <>
              <h3>Requirements & rules</h3>
              <div className="rich-text" dangerouslySetInnerHTML={{ __html: event.rulesHtml }} />
            </>
          ) : null}
          {event.prizesHtml ? (
            <>
              <h3>Prizes</h3>
              <div className="rich-text" dangerouslySetInnerHTML={{ __html: event.prizesHtml }} />
            </>
          ) : null}
          <p className="notice">
            <ShieldCheck size={16} strokeWidth={1.5} /> Eligibility is confirmed through the
            participant portal before a registration is treated as final.
          </p>
        </article>
        <aside className="detail-card">
          <div className="detail-row">
            <span>Format</span>
            <b>{event.format}</b>
          </div>
          {event.format === 'team' ? (
            <div className="detail-row">
              <span>Team size</span>
              <b>
                {event.teamMinSize}-{event.teamMaxSize} members
              </b>
            </div>
          ) : null}
          <div className="detail-row">
            <span>Included base value</span>
            <b>{money(event.baseValuePaise)}</b>
          </div>
          <div className="detail-row">
            <span>Standalone add-on</span>
            <b>{money(event.addonPricePaise)}</b>
          </div>
          <div className="detail-row">
            <span>Capacity</span>
            <b>
              {event.capacity || 'Unlimited'}
              {event.seatsLeft !== null && event.seatsLeft !== undefined
                ? ` · ${event.seatsLeft} left`
                : ''}
            </b>
          </div>
          <div className="detail-row">
            <span>Schedule</span>
            <b>
              {date(event.startsAt)} · {time(event.startsAt)} - {time(event.endsAt)}
            </b>
          </div>
          <div className="detail-row">
            <span>Room</span>
            <b>{event.venueRoom || 'To be announced'}</b>
          </div>
          <div className="detail-row">
            <span>Team fee basis</span>
            <b>{event.teamFeeBasis || event.addonChargeBasis}</b>
          </div>
          <p>
            Every participant still needs the convention pass. Add-on fees never replace it.
          </p>
          <Button to="/portal/select-events" icon={ArrowRight} className="full">
            Plan this in your portal
          </Button>
        </aside>
      </section>
    </>
  );
}

export function PassPage() {
  const { edition, policy } = useSite();
  const mode = policy?.includedSelectionMode === 'exact' ? 'Exactly' : 'Up to';
  return (
    <>
      <PageTitle
        kicker="Convention Pass"
        title={
          <>
            One pass. Two days.
            <br />
            <em>Your event choices.</em>
          </>
        }
        desc="The pass, the included allowance and add-on fees are three separate parts of the pricing model."
      />
      <section className="section pass-layout">
        <article className="price-card">
          <span>MANDATORY · PER PARTICIPANT</span>
          <strong>{money(policy?.passPricePaise)}</strong>
          <p>{edition.name} Convention Pass</p>
          <div className="price-rule" />
          <p>
            <Check size={16} strokeWidth={2} /> Lunch on{' '}
            {(policy?.lunchIncludedDays || []).map(dayLabel).join(' and ') || 'convention days'}
          </p>
          <p>
            <Check size={16} strokeWidth={2} /> {mode} {policy?.includedEventCount} included event
            choices
          </p>
          <p>
            <Check size={16} strokeWidth={2} /> Base value capped at{' '}
            {money(policy?.includedValueCapPaise)}
          </p>
          <p>
            <Check size={16} strokeWidth={2} /> Entry ticket with a scannable token
          </p>
          <Button to="/portal/pass" icon={ArrowRight} className="full">
            Get your pass
          </Button>
          <small>
            {policy?.gstNote || 'Fees are shown in Indian rupees.'} Paid in the participant portal.
          </small>
        </article>
        <article className="pass-copy">
          <Eyebrow>How Pricing Works</Eyebrow>
          <h2>
            Pass first.
            <br />
            <em>Then pick your programme.</em>
          </h2>
          <ol>
            <li>
              <b>Every participant gets one pass.</b>
              <p>
                It includes lunch on{' '}
                {(policy?.lunchIncludedDays || []).map(dayLabel).join(' and ') || 'both days'} and
                is required before any event registration.
              </p>
            </li>
            <li>
              <b>
                Choose {mode.toLowerCase()} {policy?.includedEventCount} eligible events.
              </b>
              <p>
                The sum of their published base values must stay{' '}
                {policy?.capInclusive ? 'at or under' : 'under'}{' '}
                {money(policy?.includedValueCapPaise)}. The pass price is never added to that sum.
              </p>
            </li>
            <li>
              <b>Add extra events separately.</b>
              <p>
                Additional registrations use each event’s published add-on fee and are charged
                after the pass.
              </p>
            </li>
            <li>
              <b>Team members each need a pass.</b>
              <p>
                {policy?.teamMembersRequirePass
                  ? 'Every team member must hold an active pass before the team entry is accepted.'
                  : 'Team entry does not require a separate pass per member in this edition.'}
              </p>
            </li>
          </ol>
          <div className="cap-callout">
            <span>INCLUDED EVENT VALUE CAP</span>
            <b>
              {money(policy?.includedValueCapPaise)}{' '}
              <small>live edition policy</small>
            </b>
            <p>
              Selection locks on {date(policy?.selectionChangeDeadline)}. Unpaid add-on reservations
              expire after {policy?.holdMinutes || 15} minutes.
            </p>
          </div>
        </article>
      </section>
    </>
  );
}

export function SchedulePage() {
  const { slug } = useSite();
  const schedule = useAsync(() => publicApi.schedule(slug), [slug], { enabled: Boolean(slug) });
  const days = schedule.data?.data || [];

  return (
    <>
      <PageTitle
        kicker="The Programme"
        title={
          <>
            Two days of
            <br />
            <em>new perspectives.</em>
          </>
        }
        desc="Every published session, ordered by its live start time and room."
      />
      <section className="section schedule-grid">
        {schedule.loading ? <Loading label="Loading schedule" rows={3} /> : null}
        {schedule.error ? <ErrorBox error={schedule.error} onRetry={schedule.reload} /> : null}
        {!schedule.loading && !schedule.error && !days.length ? (
          <Empty title="The schedule is not published" desc="Sessions will appear here once released." />
        ) : null}
        {days.map((day, index) => (
          <article className="day-card rise" key={day.date} style={{ animationDelay: `${index * 80}ms` }}>
            <span>{`DAY 0${index + 1}`}</span>
            <h2>{day.label}</h2>
            {day.items.map((item) => (
              <div className="schedule-row" key={item.id}>
                <Clock3 size={18} strokeWidth={1.4} />
                <div>
                  <Link to={`/events/${item.slug}`}>
                    <b>{item.title}</b>
                  </Link>
                  <p>
                    {time(item.startsAt)} - {time(item.endsAt)} · {item.room || 'Room to be announced'}
                  </p>
                </div>
                <span className="pill">{item.category}</span>
              </div>
            ))}
            <div className="day-art">0{index + 1}</div>
          </article>
        ))}
      </section>
    </>
  );
}

export function VenuePage() {
  const { edition } = useSite();
  if (!edition) return <Loading label="Loading venue details" rows={2} />;
  return (
    <>
      <PageTitle
        kicker="The Venue"
        title={
          <>
            Meet us at
            <br />
            <em>{edition.city?.split(',')[0] || 'Palakkad'}.</em>
          </>
        }
        desc={`${edition.venue}, hosted by ${edition.host}.`}
      />
      <section className="section venue-grid">
        <article className="venue-map-card">
          <div className="map-toolbar">
            <div className="map-status">
              <MapPin size={14} strokeWidth={1.8} />
              <span>NSS College of Engineering Campus</span>
            </div>
            <a
              href="https://maps.google.com/?q=NSS+College+of+Engineering+Palakkad"
              target="_blank"
              rel="noopener noreferrer"
              className="map-ext-link"
            >
              Open in Google Maps <ArrowUpRight size={14} />
            </a>
          </div>
          <div className="map-frame-wrapper">
            <iframe
              title="Google Map - NSS College of Engineering, Palakkad"
              src="https://maps.google.com/maps?q=NSS+College+of+Engineering+Palakkad&t=&z=16&ie=UTF8&iwloc=&output=embed"
              width="100%"
              height="100%"
              style={{ border: 0 }}
              allowFullScreen=""
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
            />
          </div>
          <div className="map-caption">
            <MapPin size={16} strokeWidth={1.5} />
            <span>NSS Nagar, Akathethara, Palakkad, Kerala 678008</span>
          </div>
        </article>
        <article className="venue-copy">
          <Eyebrow>Host Campus</Eyebrow>
          <h2>{edition.host}</h2>
          <p>{edition.city}</p>
          <p>
            Sessions run across {edition.venue}. Room numbers and lab assignments are published with each session in the
            live schedule; registration check-in opens at the campus main auditorium on both days.
          </p>
          <div className="detail-row">
            <span>Dates</span>
            <b>{dateRange(edition.startsAt, edition.endsAt)}</b>
          </div>
          <div className="detail-row">
            <span>Venue</span>
            <b>{edition.venue}</b>
          </div>
          <div className="detail-row">
            <span>City</span>
            <b>{edition.city}</b>
          </div>
          <div className="detail-row">
            <span>Transit Access</span>
            <b>Palakkad Junction (PGT) ~ 7 km · Coimbatore Airport (CJB) ~ 65 km</b>
          </div>
          <div className="venue-actions">
            <Button to="/schedule" variant="light" icon={ArrowRight}>
              Browse the schedule
            </Button>
            <Button
              href="https://maps.google.com/?q=NSS+College+of+Engineering+Palakkad"
              target="_blank"
              rel="noopener noreferrer"
              variant="ghost"
              icon={Navigation}
            >
              Get directions
            </Button>
          </div>
        </article>
      </section>
    </>
  );
}

export function FAQPage() {
  const { policy, edition } = useSite();
  const mode = policy?.includedSelectionMode === 'exact' ? 'exactly' : 'up to';
  const rows = [
    [
      'Is the convention pass mandatory?',
      `Yes. Every participant needs their own ${money(policy?.passPricePaise)} pass. Event add-on fees never replace it.`,
    ],
    [
      'What does the pass include?',
      `Lunch on ${(policy?.lunchIncludedDays || []).map(dayLabel).join(' and ') || 'the convention days'}, entry, and an included-event allowance.`,
    ],
    [
      'How many included events can I select?',
      `${mode} ${policy?.includedEventCount} eligible events, with a base-value cap of ${money(policy?.includedValueCapPaise)}.`,
    ],
    [
      'Can I change my included selections?',
      `Until ${date(policy?.selectionChangeDeadline)}. After that the selection locks and the portal disables edits.`,
    ],
    [
      'Can I register for more events?',
      policy?.addonRequiresPass
        ? 'Yes, after the pass. Extra events use their published add-on fee.'
        : 'Yes. Add-on events can be purchased separately.',
    ],
    [
      'How does the team rule work?',
      policy?.teamMembersRequirePass
        ? 'Each team member must hold an active pass before the team entry can be confirmed.'
        : 'Team entry is available without a separate pass for each member in this edition.',
    ],
    [
      'How is student eligibility verified?',
      'By roster match, institutional email confirmation, or a reviewed student document in the portal.',
    ],
    [
      'What happens after payment?',
      'The pass activates immediately, included registrations are created, and an entry ticket with a scannable token is issued.',
    ],
    [
      'Can I get a refund?',
      'Refunds are handled by the finance team against a paid order. Ask the organisers through the contact address.',
    ],
    [
      'Where do I get help?',
      `Write to ${edition?.contactEmail || 'the organisers'}.`,
    ],
  ];
  return (
    <>
      <PageTitle
        kicker="Good to Know"
        title={
          <>
            Questions, meet
            <br />
            <em>clear answers.</em>
          </>
        }
        desc="Answers reflect the live edition policy, not a prototype script."
      />
      <section className="section faq-list">
        {rows.map(([question, answer], index) => (
          <details key={question}>
            <summary>
              <span>{`0${index + 1}`.slice(-2)}</span>
              {question}
            </summary>
            <p>{answer}</p>
          </details>
        ))}
      </section>
    </>
  );
}

export function ContactPage() {
  const { edition } = useSite();
  const email = edition?.contactEmail;
  return (
    <>
      <PageTitle
        kicker="Contact"
        title={
          <>
            Let’s get
            <br />
            <em>in touch.</em>
          </>
        }
        desc="The organising team answers from the official convention address."
      />
      <section className="section contact-card">
        <Mail size={24} strokeWidth={1.4} />
        <div>
          <span>OFFICIAL CONVENTION EMAIL</span>
          {email ? (
            <h2>
              <a href={`mailto:${email}`}>{email}</a>
            </h2>
          ) : (
            <h2>Contact address pending</h2>
          )}
          <p>
            {edition?.organizer || 'ISTE'} · {edition?.host || 'NSS College of Engineering'}, {edition?.city || 'Palakkad'}
          </p>
        </div>
        {email ? (
          <Button href={`mailto:${email}`} variant="ghost" icon={ArrowUpRight}>
            Write to the team
          </Button>
        ) : null}
      </section>
      <section className="section center-actions">
        <Button to="/portal" variant="ghost" icon={ArrowRight}>
          Open the participant portal
        </Button>
      </section>
    </>
  );
}

export function Footer() {
  const { edition } = useSite();
  if (!edition) return null;
  return (
    <footer className="footer">
      <div className="footer-top">
        <Link to="/" className="footer-brand" aria-label={`${edition.name} home`}>
          <img src={LOGO} alt={edition.name} className="footer-logo" />
        </Link>
        <p>
          A shift in perspective.
          <br />A leap in innovation.
        </p>
        <div className="footer-host">
          <img src={ISTE} alt={`${edition.organizer} emblem`} />
          <span>
            Hosted by {edition.host}
            <br />
            {edition.city}
          </span>
        </div>
      </div>
      <div className="footer-links">
        {[
          ['About', '/about'],
          ['Events', '/events'],
          ['Convention pass', '/pass'],
          ['Schedule', '/schedule'],
          ['Venue', '/venue'],
          ['FAQ', '/faq'],
          ['Contact', '/contact'],
          ['Portal', '/portal'],
        ].map(([label, to]) => (
          <Link key={to} to={to}>
            {label}
          </Link>
        ))}
      </div>
      <div className="footer-bottom">
        <span>
          © {new Date().getFullYear()} {edition.name} · {edition.organizer}
        </span>
        <span>{dateRange(edition.startsAt, edition.endsAt)}</span>
        <span className="social">
          <Ticket size={16} strokeWidth={1.4} /> Live convention platform
        </span>
      </div>
    </footer>
  );
}

export { ISTE, LOGO, NSSCE, GLOBE };
