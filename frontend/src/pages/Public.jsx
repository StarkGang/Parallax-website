import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Boxes,
  Building2,
  CalendarDays,
  Check,
  ChevronDown,
  Clock3,
  Code2,
  Gamepad2,
  HelpCircle,
  Layers,
  Mail,
  MapPin,
  Navigation,
  PenTool,
  Phone,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Ticket,
  Users,
  Zap,
} from 'lucide-react';
import { publicApi } from '../lib/api.js';
import { gsap, ScrollTrigger, useCardTilt } from '../lib/motion.js';

import { useSite } from '../lib/site.jsx';
import { date, dateRange, dayLabel, money, time, weekday } from '../lib/format.js';
import { eventListPricePaise } from '../lib/pricing.js';
import {
  Badge,
  Button,
  Empty,
  ErrorBox,
  Eyebrow,
  Loading,
  PageTitle,
  Panel,
  SectionHead,
  useAsync,
  useDebounced,
} from '../components/ui.jsx';
import HolographicTicket from '../components/HolographicTicket.jsx';
import HudFrame from '../components/HudFrame.jsx';
import ScheduleBoard from './ScheduleBoard.jsx';
import './EventCard.css';
import './HomePreview.css';
import './TeamFrame.css';
import HeroOdyssey from '../components/HeroOdyssey.jsx';
import PageScene from '../components/PageScene.jsx';
import { MascotEasterEggBubble, useMascotEasterEgg } from '../components/MascotEasterEgg.jsx';
import { mascotSay } from '../components/mascot/mascotSay.js';

const TIER_SHORT_LABELS = {
  iste_member: 'ISTE',
  non_iste: 'Non-ISTE',
  polytechnic: 'Polytechnic',
};

const LOGO = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp`;
const GLOBE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/modified assets/globe.svg`;
const NSSCE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/NSSCE-Palakkad-Logo.webp`;
const ISTE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/Iste_logo.png`;
// Served straight from public/ so dev and production resolve the same vector.
const PARALLAX_MARK = `${import.meta.env.BASE_URL}images/parallax-vector.svg`;
const TEAM_PLACEHOLDER = `${import.meta.env.BASE_URL}images/team/placeholder.svg`;
const VENUE_ADDRESS = 'NSS Nagar, Akathethara, Palakkad, Kerala 678008';

function teamImageFallback(event) {
  const img = event.currentTarget;
  if (img.src.endsWith('/placeholder.svg')) return;
  img.src = TEAM_PLACEHOLDER;
}

// High-fidelity architectural parallax depth backplates & vector assets
const PARALLAX_BG_VAULT = `${import.meta.env.BASE_URL}images/parallax-bg-vault.webp`;
const PARALLAX_BG_CORE = `${import.meta.env.BASE_URL}images/parallax-bg-core.webp`;
const PARALLAX_BG_PEDESTAL = `${import.meta.env.BASE_URL}images/parallax-bg-pedestal.webp`;
const PARALLAX_DEPTH_BG = `${import.meta.env.BASE_URL}images/parallax-depth-bg.webp`;
const PARALLAX_VECTOR = `${import.meta.env.BASE_URL}images/parallax-vector.svg`;
const PARALLAX_LOGO_ASSET = `${import.meta.env.BASE_URL}images/parallax-logo.webp`;

// Techfest-style frame shells used by the homepage preview cards and the
// framed event catalogue. Both PNGs are transparent cut-outs.
const MAIN_FRAME = `${import.meta.env.BASE_URL}images/main_frame.png`;
const EVENT_FRAME = `${import.meta.env.BASE_URL}images/event_frame.png`;
const PASS_CARD_ART = `${import.meta.env.BASE_URL}images/pass-card.jpg`;
const EVENTS_ART = `${import.meta.env.BASE_URL}images/events-card.jpg`;
const ABOUT_ART = `${import.meta.env.BASE_URL}images/about-card.jpg`;

// Homepage scene: the animated rooftop backdrop and the character that stands
// at the base of the three framed cards.
const SCENE_BG = `${import.meta.env.BASE_URL}images/bg.gif`;
// Static art on the homepage stage: the animated GIF pulled focus away from the
// three entry cards, so the mascot now sits still and only drifts on hover.
const SCENE_MASCOT = `${import.meta.env.BASE_URL}images/mascot.png`;

// Inner page scenes: the events catalogue uses the arena with the event
// character, the remaining pages share the valley backdrop and mascot.
const ARENA_ART = `${import.meta.env.BASE_URL}images/arena.png`;
const EVENT_SCENE_ART = `${import.meta.env.BASE_URL}images/event.png`;
const BACKGROUND_ART = `${import.meta.env.BASE_URL}images/background.png`;
const MASCOT_ART = `${import.meta.env.BASE_URL}images/mascot.png`;
const CONTACT_MASCOT_ART = `${import.meta.env.BASE_URL}images/contact-mascot.png`;

function CategoryIcon({ category, size = 30 }) {
  const cat = (category || '').toLowerCase();
  if (
    cat.includes('comp') ||
    cat.includes('code') ||
    cat.includes('hack') ||
    cat.includes('data')
  ) {
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
  return <Layers size={size} strokeWidth={1.5} />;
}

function EventIcon({ iconId, category, size = 22 }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  return (
    <>
      {(!loaded || failed || !iconId) && <CategoryIcon category={category} size={size} />}
      {iconId && !failed && (
        <img
          src={publicApi.iconUrl(iconId)}
          alt=""
          className="pro-event-icon-img"
          style={loaded ? undefined : { display: 'none' }}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
      )}
    </>
  );
}

function getEventAccent(event) {
  if (event.accent && typeof event.accent === 'string') {
    const raw = event.accent.toLowerCase().trim();
    if (raw) return raw;
  }
  const cat = (event.categorySlug || event.categoryName || '').toLowerCase();
  if (cat.includes('electr')) return 'orange';
  if (cat.includes('engin')) return 'amber';
  if (cat.includes('robot')) return 'lime';
  if (cat.includes('design')) return 'violet';
  if (cat.includes('comput') || cat.includes('code')) return 'cyan';
  return 'cyan';
}

const IST_ZONE = 'Asia/Kolkata';

// Convention days are grouped in the edition's timezone so an event that
// starts after midnight UTC still belongs to its local convention day.
const dayKeyOf = (iso) => {
  if (!iso) return 'tba';
  try {
    return new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      timeZone: IST_ZONE,
    }).format(new Date(iso));
  } catch {
    return 'tba';
  }
};

const dayLabelOf = (iso) => {
  if (!iso) return 'Date to be announced';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      weekday: 'long',
      day: '2-digit',
      month: 'long',
      timeZone: IST_ZONE,
    })
      .format(new Date(iso))
      .toUpperCase();
  } catch {
    return 'Date to be announced';
  }
};

/** Groups a chronological event list into convention-day runs. */
function groupEventsByDay(events) {
  const groups = [];
  events.forEach((event) => {
    const key = dayKeyOf(event.startsAt);
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.events.push(event);
      return;
    }
    groups.push({ key, label: dayLabelOf(event.startsAt), events: [event] });
  });
  return groups;
}

// Poster backdrops rotate through the supplied corridors so a catalogue page
// does not repeat one image twelve times. Event banners always win.
function posterBackdrop(event) {
  const cat = `${event.categorySlug || ''} ${event.categoryName || ''}`.toLowerCase();
  if (cat.includes('comput') || cat.includes('code')) return PARALLAX_BG_CORE;
  if (cat.includes('electr')) return PARALLAX_BG_VAULT;
  if (cat.includes('robot') || cat.includes('engin')) return PARALLAX_BG_PEDESTAL;
  if (cat.includes('design')) return PARALLAX_BG_VAULT;
  return PARALLAX_DEPTH_BG;
}

export function EventCard({ event, index = 0 }) {
  const navigate = useNavigate();
  const isTeam = event.format === 'team';
  const accent = getEventAccent(event);
  const formatLabel = isTeam
    ? `Team ${event.teamMinSize || 2}–${event.teamMaxSize || 4}`
    : 'Individual';
  const title = event.title || 'Untitled event';
  const detailPath = `/events/${event.slug}`;
  const feeLabel =
    event.addonPricePaise > 0 ? `Add-on ${money(event.addonPricePaise)}` : 'Included with pass';
  const listFeePaise = eventListPricePaise(event.addonPricePaise, event.slug);
  const mascotHover = `${title}: ${event.categoryName || 'competition'}, ${formatLabel.toLowerCase()}, ${feeLabel.toLowerCase()}. ${isTeam ? 'Grab your crew.' : 'Solo run, bold.'}`;
  const whenLabel = event.startsAt
    ? `${new Date(event.startsAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} · ${time(event.startsAt)}`
    : 'Schedule TBA';
  const venueLabel = (event.venue || event.room || '').trim();

  // The whole card opens its detail page; the Explore and Register links keep
  // their own targets. Modified clicks are left to the browser.
  const handleCardClick = (clickEvent) => {
    if (clickEvent.defaultPrevented) return;
    if (clickEvent.button !== 0) return;
    if (clickEvent.metaKey || clickEvent.ctrlKey || clickEvent.shiftKey || clickEvent.altKey)
      return;
    if (clickEvent.target.closest('a, button')) return;
    navigate(detailPath);
  };

  return (
    <article
      className={`exc${event.registrationOpen ? '' : ' is-closed'}`}
      data-accent={accent}
      data-reveal=""
      onClick={handleCardClick}
      data-mascot-target={`event-${event.slug}`}
      data-mascot-label={title}
      data-mascot-hover={mascotHover}
      data-mascot-featured={event.isFeatured ? 'true' : undefined}
    >
      <div className="exc-poster">
        {event.bannerUrl ? (
          <img
            src={event.bannerUrl}
            alt=""
            className="exc-poster-img"
            loading="lazy"
            decoding="async"
            width={480}
            height={320}
          />
        ) : (
          <div className="exc-poster-fallback">
            <img
              src={posterBackdrop(event)}
              alt=""
              className="exc-poster-bg"
              loading="lazy"
              decoding="async"
            />
            <div className="exc-poster-tint" />
            <div className="exc-poster-glyph">
              <EventIcon
                iconId={event.iconId}
                category={event.categorySlug || event.categoryName}
                size={42}
              />
            </div>
          </div>
        )}

        <div className="exc-hud-top">
          <span className="exc-hud-chip is-time">{whenLabel}</span>
          <span className={`exc-hud-chip${event.registrationOpen ? ' is-open' : ' is-closed'}`}>
            {event.registrationOpen ? 'Open' : 'Closed'}
          </span>
        </div>

        {venueLabel || event.prizePoolPaise > 0 ? (
          <div className="exc-hud-bottom">
            {venueLabel ? <span className="exc-hud-venue">{venueLabel}</span> : null}
            {event.prizePoolPaise > 0 ? (
              <span className="exc-hud-prize">Prize {money(event.prizePoolPaise)}</span>
            ) : null}
          </div>
        ) : null}
      </div>

      <img
        className="exc-frame"
        src={EVENT_FRAME}
        alt=""
        aria-hidden="true"
        draggable="false"
        decoding="async"
      />

      <div className="exc-panel">
        <p className="exc-eyebrow">
          <span className="exc-dot" aria-hidden="true" />
          <span>{event.categoryName || 'Event'}</span>
          <span className="exc-sep" aria-hidden="true">
            /
          </span>
          <span>{formatLabel}</span>
        </p>
        <h3 className={`exc-title${title.length > 20 ? ' is-long' : ''}`}>{title}</h3>
      </div>

      <div className="exc-actions">
        <Link
          className="exc-action"
          to={detailPath}
          aria-label={`Explore ${title}`}
          onPointerEnter={() => mascotSay(`Want the full story on ${title}? Click in.`)}
        >
          <span>Explore</span>
          <ArrowUpRight size={11} strokeWidth={2.2} aria-hidden="true" />
        </Link>
        {event.registrationOpen ? (
          <Link
            className="exc-action is-primary"
            to={isTeam ? '/portal/teams' : '/portal/events'}
            aria-label={isTeam ? `Create or join team for ${title}` : `Register for ${title}`}
            onPointerEnter={() =>
              mascotSay(
                isTeam
                  ? `Round up your squad for ${title}, slots go fast.`
                  : `Ready to lock in ${title}? This is the button.`,
              )
            }
          >
            <span>{isTeam ? 'Join team' : 'Register'}</span>
            <ArrowRight size={11} strokeWidth={2.4} aria-hidden="true" />
          </Link>
        ) : (
          <span className="exc-action is-disabled" aria-disabled="true">
            <span>Closed</span>
          </span>
        )}
      </div>

      <p className="exc-plaque">
        <b>
          {event.addonPricePaise > 0 ? (
            <>
              <s className="exc-was">{money(listFeePaise)}</s>
              {money(event.addonPricePaise)}
            </>
          ) : (
            'Included with pass'
          )}
        </b>
        <span aria-hidden="true">·</span>
        {event.registrationOpen ? (
          <span className="exc-open">Open</span>
        ) : (
          <span className="exc-closed">Registration closed</span>
        )}
      </p>
    </article>
  );
}

function PreviewCard({
  kicker,
  title,
  copy,
  meta,
  cta,
  to,
  image,
  eager = false,
  mascotTarget,
  mascotHover,
  icon: Icon,
}) {
  const cardRef = useRef(null);

  useEffect(() => {
    const el = cardRef.current;
    if (!el) return undefined;
    let raf = null;

    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      el.classList.add('is-tracking');
      el.style.setProperty('--mx', `${(x + 0.5) * 100}%`);
      el.style.setProperty('--my', `${(y + 0.5) * 100}%`);
      el.style.setProperty('--tx', `${-y * 10}deg`);
      el.style.setProperty('--ty', `${x * 10}deg`);
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => el.classList.remove('is-tracking'));
    };

    const onLeave = () => {
      el.classList.remove('is-tracking');
      el.style.setProperty('--tx', '0deg');
      el.style.setProperty('--ty', '0deg');
    };

    el.addEventListener('mousemove', onMove);
    el.addEventListener('mouseleave', onLeave);
    return () => {
      el.removeEventListener('mousemove', onMove);
      el.removeEventListener('mouseleave', onLeave);
    };
  }, []);

  return (
    <Link
      className="px-card"
      ref={cardRef}
      to={to}
      data-reveal=""
      data-mascot-target={mascotTarget}
      data-mascot-label={title}
      data-mascot-hover={mascotHover}
    >
      <div className="px-card-media">
        <img src={image} alt="" loading={eager ? 'eager' : 'lazy'} decoding="async" />
      </div>
      <div className="px-card-scrim" aria-hidden="true" />
      <img
        className="px-card-frame"
        src={MAIN_FRAME}
        alt=""
        aria-hidden="true"
        draggable="false"
        decoding="async"
      />
      <div className="px-card-body">
        {kicker ? (
          <span className="px-card-kicker">
            {Icon ? <Icon size="1.1em" strokeWidth={2.2} aria-hidden="true" /> : null}
            {kicker}
          </span>
        ) : null}
        <h3 className="px-card-title">{title}</h3>
        <p className="px-card-copy">{copy}</p>
        {meta ? <span className="px-card-meta">{meta}</span> : null}
        <span className="px-card-cta">
          <span>{cta}</span>
          <ArrowUpRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </span>
      </div>
    </Link>
  );
}

const TOTAL_HERO_FRAMES = 192;

function HeroParallax({ edition, days }) {
  const trackRef = useRef(null);
  const stageRef = useRef(null);
  const canvasRef = useRef(null);
  const scrollPromptRef = useRef(null);

  const imagesRef = useRef([]);
  const currentFrameRef = useRef(0);
  const [framesLoaded, setFramesLoaded] = useState(false);

  const renderFrame = (frameIdx) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const img = imagesRef.current[frameIdx];
    if (!img || !img.complete || img.naturalWidth === 0) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;

    if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    const iw = img.naturalWidth || 1280;
    const ih = img.naturalHeight || 720;
    const scale = Math.max(w / iw, h / ih);
    const ox = (w - iw * scale) / 2;
    const oy = (h - ih * scale) / 2;

    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(img, ox, oy, iw * scale, ih * scale);
    ctx.restore();
  };

  // Preload image sequence progressively: eager first batch for instant 60fps scrub,
  // then background idle batches to keep initial network waterfall pristine
  useEffect(() => {
    let active = true;
    const loadedImages = new Array(TOTAL_HERO_FRAMES);
    const baseUrl = import.meta.env.BASE_URL;
    let loadedCount = 0;

    const loadFrame = (index) => {
      if (!active || loadedImages[index]) return;
      const img = new window.Image();
      const num = String(index + 1).padStart(3, '0');
      img.src = `${baseUrl}anim/sequence/frame_${num}.webp`;
      img.onload = () => {
        if (!active) return;
        loadedCount++;
        if (index === 0) {
          renderFrame(0);
        }
        if (loadedCount >= Math.min(20, TOTAL_HERO_FRAMES)) {
          setFramesLoaded(true);
        }
      };
      loadedImages[index] = img;
    };

    // Priority 1: First frame immediately
    loadFrame(0);

    // Priority 2: Next 24 frames for instant initial scroll responsiveness
    for (let i = 1; i < Math.min(24, TOTAL_HERO_FRAMES); i++) {
      loadFrame(i);
    }

    // Priority 3: Remainder in idle batches of 12 to avoid network congestion
    let nextBatchStart = 24;
    const loadNextBatch = () => {
      if (!active || nextBatchStart >= TOTAL_HERO_FRAMES) return;
      const end = Math.min(nextBatchStart + 12, TOTAL_HERO_FRAMES);
      for (let i = nextBatchStart; i < end; i++) {
        loadFrame(i);
      }
      nextBatchStart = end;
      if (nextBatchStart < TOTAL_HERO_FRAMES) {
        if (typeof window.requestIdleCallback === 'function') {
          window.requestIdleCallback(loadNextBatch, { timeout: 200 });
        } else {
          setTimeout(loadNextBatch, 80);
        }
      }
    };

    const idleTimer = setTimeout(loadNextBatch, 150);
    imagesRef.current = loadedImages;

    const onResize = () => {
      renderFrame(currentFrameRef.current);
    };
    window.addEventListener('resize', onResize);

    return () => {
      active = false;
      clearTimeout(idleTimer);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  // Subtle pointer parallax tilt
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return undefined;

    const onMouseMove = (e) => {
      const rect = stage.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;

      stage.style.setProperty('--mouse-x', `${(x + 0.5) * 100}%`);
      stage.style.setProperty('--mouse-y', `${(y + 0.5) * 100}%`);

      if (canvasRef.current) {
        gsap.to(canvasRef.current, {
          rotateY: x * 3,
          rotateX: -y * 3,
          scale: 1.01,
          transformPerspective: 1200,
          ease: 'power1.out',
          duration: 0.35,
        });
      }
    };

    const onMouseLeave = () => {
      if (canvasRef.current) {
        gsap.to(canvasRef.current, {
          rotateX: 0,
          rotateY: 0,
          scale: 1,
          ease: 'power2.out',
          duration: 0.6,
        });
      }
    };

    stage.addEventListener('mousemove', onMouseMove);
    stage.addEventListener('mouseleave', onMouseLeave);

    return () => {
      stage.removeEventListener('mousemove', onMouseMove);
      stage.removeEventListener('mouseleave', onMouseLeave);
    };
  }, []);

  // GSAP ScrollTrigger Sequence Scrubbing with Hero Logo Fly-Through
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return undefined;

    const isReduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (isReduced) {
      renderFrame(TOTAL_HERO_FRAMES - 1);
      return undefined;
    }

    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: track,
        start: 'top top',
        end: 'bottom bottom',
        scrub: 0.65,
        onUpdate: (self) => {
          const progress = self.progress;
          const targetFrame = Math.min(
            TOTAL_HERO_FRAMES - 1,
            Math.max(0, Math.floor(progress * (TOTAL_HERO_FRAMES - 1))),
          );
          currentFrameRef.current = targetFrame;
          renderFrame(targetFrame);

          if (scrollPromptRef.current) {
            scrollPromptRef.current.style.opacity = progress > 0.05 ? '0' : '1';
            scrollPromptRef.current.style.pointerEvents = progress > 0.05 ? 'none' : 'auto';
          }
        },
      });
    }, track);

    return () => ctx.revert();
  }, []);

  return (
    <section className="hero-scroll-track" ref={trackRef}>
      <div className="hero-sticky-stage" ref={stageRef}>
        {/* Full-bleed 3D canvas stage */}
        <canvas className="hero-scroll-canvas" ref={canvasRef} />

        {/* Dynamic vignette and specular glare overlay */}
        <div className="hero-atmosphere-vignette" aria-hidden="true" />
        <div className="hero-specular-glare" aria-hidden="true" />

        {/* Minimal Lusion-style Scroll Cue */}
        <div
          className="lusion-hero-scroll-cue"
          ref={scrollPromptRef}
          onPointerEnter={() => mascotSay('Scroll to explore, the good stuff is just below.')}
        >
          <div className="lusion-mouse-indicator">
            <span className="lusion-mouse-dot" />
          </div>
          <span className="lusion-cue-text">Scroll to explore</span>
        </div>
      </div>
    </section>
  );
}

function useParallaxScroll() {
  useEffect(() => {
    const isReduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (isReduced) return undefined;

    const layers = document.querySelectorAll('[data-parallax-speed]');
    if (!layers.length) return undefined;

    const ctx = gsap.context(() => {
      layers.forEach((layer) => {
        const speed = parseFloat(layer.getAttribute('data-parallax-speed')) || 0.2;
        const parent = layer.closest('section') || layer.parentElement;
        gsap.fromTo(
          layer,
          { yPercent: -speed * 45, force3D: true },
          {
            yPercent: speed * 45,
            force3D: true,
            ease: 'none',
            scrollTrigger: {
              trigger: parent,
              start: 'top bottom',
              end: 'bottom top',
              scrub: 1.0,
            },
          },
        );
      });
    });

    return () => ctx.revert();
  }, []);
}

function PassHighlightSection({ policy }) {
  const { edition, slug } = useSite();
  const tiers = useAsync(() => publicApi.registrationCategories(slug), [slug], {
    enabled: Boolean(slug),
  });
  const registrationTiers = tiers.data?.data || [];
  const tierFor = (code) => registrationTiers.find((tier) => tier.code === code);
  const isteTier = tierFor('iste_member');
  const nonIsteTier = tierFor('non_iste');
  const polytechnicTier = tierFor('polytechnic');
  const cheapestTier = registrationTiers.reduce(
    (cheapest, tier) => (!cheapest || tier.feePaise < cheapest.feePaise ? tier : cheapest),
    null,
  );
  const fromPrice = cheapestTier ? money(cheapestTier.feePaise) : '';
  const btechPerks = [
    isteTier ? `B.Tech ISTE ${money(isteTier.feePaise)}` : null,
    nonIsteTier ? `B.Tech Non-ISTE ${money(nonIsteTier.feePaise)}` : null,
  ].filter(Boolean);
  const tierPerks = [
    polytechnicTier ? `Polytechnic ${money(polytechnicTier.feePaise)}` : null,
    btechPerks.length ? btechPerks.join(' · ') : null,
  ].filter(Boolean);
  const tiltRef = useCardTilt({ maxTilt: 2.5, scale: 1.01 });
  const lunchDays = policy?.lunchIncludedDays?.length || 2;
  const includedCount = policy?.includedEventCount ?? 3;
  // A null cap means "no value cap", so it must not fall back to a number.
  const valueCap = policy?.includedValueCapPaise != null ? money(policy.includedValueCapPaise) : null;
  const sceneRef = useRef(null);

  // The pass sits inside a scene like the sections above it: artwork behind,
  // the ticket in front, both scrubbing at different speeds.
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return undefined;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;

    const ctx = gsap.context(() => {
      const trigger = { trigger: scene, start: 'top bottom', end: 'bottom top', scrub: true };
      gsap.fromTo(
        '.pass-scene-bg',
        { yPercent: -7 },
        { yPercent: 7, ease: 'none', scrollTrigger: trigger },
      );
      gsap.fromTo(
        '.pass-scene-card',
        { yPercent: 5 },
        { yPercent: -5, ease: 'none', scrollTrigger: trigger },
      );
    }, scene);

    return () => ctx.revert();
  }, []);

  return (
    <section
      className="apple-pass-section pass-scene"
      ref={sceneRef}
      onPointerEnter={() => mascotSay('The pass, in all its shiny two-day glory.', 5200, 'wave')}
    >
      <div className="pass-scene-bg" aria-hidden="true">
        <img src={PARALLAX_BG_VAULT} alt="" decoding="async" />
      </div>
      <div className="pass-scene-veil" aria-hidden="true" />
      <div className="pass-scene-floor" aria-hidden="true" />
      <div className="pass-scene-card">
        <HolographicTicket
          stubText={fromPrice ? `FROM ${fromPrice}` : 'GET PASS'}
          dates={dateRange(edition?.startsAt, edition?.endsAt).toUpperCase()}
          city={edition?.city || 'Palakkad'}
          perks={[
            `Lunch on ${lunchDays === 2 ? 'both days' : 'selected day'}`,
            ...tierPerks,
            'Unrestricted access to all exhibitions & talks',
          ]}
        />
      </div>
    </section>
  );
}

export function Home() {
  const { edition, policy, config } = useSite();
  const heroStackRef = useRef(null);
  const odysseyRef = useRef(null);
  const slug = edition?.slug;
  // The homepage previews the convention rather than listing the whole
  // catalogue: totals and the timeline come from the same public API.
  const catalogue = useAsync(() => publicApi.events(slug, { pageSize: 1 }), [slug], {
    enabled: Boolean(slug),
  });
  const categories = useAsync(() => publicApi.categories(slug), [slug], {
    enabled: Boolean(slug),
  });
  const news = useAsync(() => publicApi.announcements(slug, { pageSize: 2 }), [slug], {
    enabled: Boolean(slug),
  });

  if (!edition) return null;
  const announcements = news.data?.data || [];
  const eventTotal = catalogue.data?.meta?.total ?? null;
  const categoryTotal = categories.data?.data?.length ?? null;
  const days = Math.max(
    1,
    Math.round(
      (new Date(edition.endsAt).setHours(23, 59) - new Date(edition.startsAt).setHours(0, 0)) /
        86_400_000,
    ),
  );

  const { message: eggMessage, onMascotTap } = useMascotEasterEgg();

  // Initialize hardware-accelerated parallax layer scrub down the page
  useParallaxScroll();

  useEffect(() => {
    const stack = heroStackRef.current;
    const odyssey = odysseyRef.current;
    if (!stack || !odyssey) return undefined;

    const reducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (reducedMotion) {
      gsap.set(odyssey, { yPercent: -100 });
      return undefined;
    }

    const ctx = gsap.context(() => {
      gsap.fromTo(
        odyssey,
        { yPercent: 0 },
        {
          yPercent: -100,
          ease: 'none',
          scrollTrigger: {
            trigger: stack,
            start: 'top top',
            end: 'top+=1000vh top',
            scrub: true,
          },
        },
      );
    }, stack);

    return () => ctx.revert();
  }, []);

  useEffect(() => {
    let lastStage = 'hero';
    const onScroll = () => {
      const y = window.scrollY || 0;
      const vh = window.innerHeight || 800;
      const discoverEl = document.getElementById('discover');
      const discoverTop = discoverEl ? discoverEl.getBoundingClientRect().top : Infinity;

      let stage = 'hero';
      if (discoverTop < vh * 0.72) {
        stage = 'discover';
      } else if (y > vh * 0.35) {
        stage = 'frames';
      }

      if (stage !== lastStage) {
        lastStage = stage;
        if (stage === 'hero') {
          mascotSay('Scroll down, the real show starts just below!');
        } else if (stage === 'frames') {
          mascotSay('Keep scrolling… almost there!');
        } else if (stage === 'discover') {
          mascotSay("Oh, that's me staring at those 3! What would you choose?");
        }
      }
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <>
      <div className="home-hero-stack" ref={heroStackRef}>
        {/* The parallax sequence stays pinned beneath the opening panel. */}
        <HeroParallax edition={edition} days={days} />
        <div className="home-odyssey-panel" ref={odysseyRef}>
          <HeroOdyssey
            title={edition.name}
            subtitle="ISTE state student convention"
            description="One pass gets you into both days."
            facts={[
              `${days} days`,
              dateRange(edition.startsAt, edition.endsAt),
              placeLabel(edition.venue, edition.city),
            ]}
          />
        </div>
      </div>
      {/* Three framed entry points into the convention. The full catalogue
          lives on /events so the homepage stays a preview. */}
      <section
        className="px-preview"
        id="discover"
        aria-labelledby="px-preview-title"
        onPointerEnter={() =>
          mascotSay("Oh, that's me staring at those 3! What would you choose?", 5200, 'wave')
        }
      >
        <div className="px-stage-bg" aria-hidden="true">
          <img src={SCENE_BG} alt="" decoding="async" />
        </div>
        <div className="px-stage-veil" aria-hidden="true" />
        <img
          className="px-stage-mascot"
          src={SCENE_MASCOT}
          alt=""
          onClick={onMascotTap}
          draggable="false"
          decoding="async"
        />
        <MascotEasterEggBubble message={eggMessage} />

        <div className="px-stage-inner">
          <header className="px-preview-head">
            <span className="px-preview-kicker">{edition.name}</span>
            <h2 id="px-preview-title">
              Pick your <em>path.</em>
            </h2>
          </header>

          <div className="px-grid">
            <PreviewCard
              mascotTarget="home-edition"
              mascotHover="New here? The About card is your best first click."
              kicker="01 / The Edition"
              title="About Parallax"
              icon={CalendarDays}
              copy={`${edition.name} is the ${edition.organizer || 'ISTE'} convention hosted at ${edition.host || 'NSSCE'}.`}
              cta="Read more"
              to="/about"
              image={ABOUT_ART}
            />
            <PreviewCard
              mascotTarget="home-pass"
              mascotHover="One pass, both days, lunch sorted. Not a bad deal."
              kicker="02 / The Pass"
              title="Convention Pass"
              icon={Ticket}
              copy="Full access across both days with lunch and up to three included events."
              cta="Get your pass"
              to="/pass"
              image={PASS_CARD_ART}
            />
            <PreviewCard
              mascotTarget="home-events"
              mascotHover="Hackathons, builds, sprints, go on, pick a fight."
              kicker="03 / The Competitions"
              title="Events"
              icon={Gamepad2}
              copy="Hackathons, hardware builds, design sprints and paper sessions."
              meta={`${eventTotal ?? 0} events · ${categoryTotal ?? 0} categories`}
              cta="See all events"
              to="/events"
              image={EVENTS_ART}
            />
          </div>
        </div>
      </section>

      {announcements.length ? (
        <section
          className="section news-section"
          onPointerEnter={() => mascotSay('Fresh from the organisers, worth a skim.')}
        >
          <SectionHead kicker="Bulletin" title="From the organisers" />
          <div className="news-grid">
            {announcements.map((item, index) => (
              <Panel
                key={item.id}
                className="news-card rise"
                style={{ animationDelay: `${index * 80}ms` }}
              >
                <span className="mono-note">{date(item.publishedAt)}</span>
                <h3>{item.title}</h3>
                <div
                  className="rich-text"
                  dangerouslySetInnerHTML={{
                    __html: item.bodyHtml || item.bodyMd,
                  }}
                />
              </Panel>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}

function placeLabel(...parts) {
  const seen = new Set();
  return parts
    .filter(Boolean)
    .join(', ')
    .split(',')
    .map((part) => part.trim())
    .filter((part) => {
      if (!part) return false;
      const key = part.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .join(', ');
}

function useCountdown(targetIso) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!targetIso) return undefined;
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, [targetIso]);

  if (!targetIso) return null;
  const target = new Date(targetIso).getTime();
  if (!Number.isFinite(target)) return null;

  const remaining = target - now;
  if (remaining <= 0) return { live: true };

  return {
    live: false,
    days: Math.floor(remaining / 86_400_000),
    hours: Math.floor((remaining % 86_400_000) / 3_600_000),
    minutes: Math.floor((remaining % 3_600_000) / 60_000),
  };
}

export function About() {
  const { edition, policy, slug } = useSite();
  const countdown = useCountdown(edition?.startsAt);
  const catalogue = useAsync(() => publicApi.events(slug, { pageSize: 1 }), [slug], {
    enabled: Boolean(slug),
  });
  const eventTotal = catalogue.data?.meta?.total;
  const dayCount =
    edition?.startsAt && edition?.endsAt
      ? Math.max(
          1,
          Math.round(
            (new Date(edition.endsAt).setHours(23, 59) -
              new Date(edition.startsAt).setHours(0, 0)) /
              86_400_000,
          ),
        )
      : 2;

  const countdownLabel = countdown
    ? countdown.live
      ? 'Live this weekend'
      : `${countdown.days}d ${String(countdown.hours).padStart(2, '0')}h ${String(countdown.minutes).padStart(2, '0')}m`
    : dateRange(edition?.startsAt, edition?.endsAt);

  const ABOUT_VISUAL = `${import.meta.env.BASE_URL}images/nssce-main-campus.jpg`;

  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
        <PageTitle
          kicker="About"
          title={
            <>
              About
              <br />
              <em>{edition?.name || 'Parallax 2027'}.</em>
            </>
          }
          desc={`${edition?.organizer || 'ISTE'} brings the convention to ${placeLabel(edition?.host, edition?.city) || 'NSS College of Engineering, Palakkad'}. Two days, one campus.`}
        />
      </PageScene>

      {/* Band 1: Unboxed editorial heading + counter row */}
      <section
        className="px-about-intro-band"
        onPointerEnter={() => mascotSay('Two days, one campus, the whole thing in a nutshell.')}
      >
        <div className="px-about-container">
          <div className="px-about-intro-head">
            <h2>TWO DAYS OF STUDENT ENGINEERING ON ONE CAMPUS</h2>
            <p>
              {edition?.name || 'Parallax 2027'} is organised by {edition?.organizer || 'ISTE'} at{' '}
              {placeLabel(edition?.host, edition?.city) || 'NSS College of Engineering, Palakkad'}.
              Every workshop, competition, room assignment, and fee on this site comes straight from
              the live organiser catalogue.
            </p>
          </div>

          <div
            className="px-about-counter-row"
            aria-label="Convention at a glance"
            onPointerEnter={() => mascotSay('Two days, one campus, trust me, it goes by fast.')}
          >
            <div className="px-about-counter-item">
              <CalendarDays className="px-about-counter-icon" size={18} strokeWidth={2.1} aria-hidden="true" />
              <b>{dayCount}</b>
              <span>Days on campus</span>
            </div>
            <div className="px-about-counter-item">
              <Boxes className="px-about-counter-icon" size={18} strokeWidth={2.1} aria-hidden="true" />
              <b>{catalogue.loading ? '...' : eventTotal ?? '...'}</b>
              <span>Live events</span>
            </div>
            <div className="px-about-counter-item">
              <Ticket className="px-about-counter-icon" size={18} strokeWidth={2.1} aria-hidden="true" />
              <b>{policy?.includedEventCount ?? 3}</b>
              <span>Included with pass</span>
            </div>
            <div className="px-about-counter-item">
              <Clock3 className="px-about-counter-icon" size={18} strokeWidth={2.1} aria-hidden="true" />
              <b className="is-clock">{countdownLabel}</b>
              <span>{countdown?.live ? 'Convention status' : 'Doors open in'}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Band 2: Square-cornered campus visual + Host Institution dossier */}
      <section className="px-about-visual-band" aria-label="Host institution showcase">
        <div className="px-about-container px-about-visual-grid">
          <div
            className="px-about-visual-media"
            onPointerEnter={() => mascotSay('That is NSSCE right there. Pretty neat, huh?')}
          >
            <img
              src={ABOUT_VISUAL}
              alt={`${edition?.name || 'Parallax 2027'} at ${edition?.host || 'NSS College of Engineering'}`}
              loading="lazy"
            />
          </div>

          <div className="px-about-visual-copy">
            <div className="px-about-visual-brand">
              <img src={NSSCE} alt={`${edition?.host || 'NSSCE'} emblem`} />
              <div>
                <span className="px-about-acid-tag">HOST INSTITUTION</span>
                <h3>{edition?.host || 'NSS College of Engineering'}</h3>
              </div>
            </div>

            <div className="px-about-visual-facts">
              <div>
                <span>Organiser</span>
                <b>{edition?.organizer || 'ISTE Student Chapter'}</b>
              </div>
              <div>
                <span>Dates</span>
                <b>{dateRange(edition?.startsAt, edition?.endsAt)}</b>
              </div>
              <div>
                <span>Location</span>
                <b>{placeLabel(edition?.venue, edition?.city) || 'NSSCE Campus, Palakkad'}</b>
              </div>
            </div>

            <div className="px-about-row-actions">
              <Link
                className="px-about-pill-btn"
                to="/pass"
                data-mascot-target="about-pass"
                data-mascot-label="Get your pass"
                data-mascot-hover="Get your pass, future you says thanks."
              >
                Get your pass
              </Link>
              <Link
                className="px-about-inline-link"
                to="/venue"
                data-mascot-target="about-venue"
                data-mascot-label="Campus directions"
                data-mascot-hover="Campus directions, I know the way."
              >
                Campus directions <ArrowUpRight size={14} strokeWidth={2} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section
        className="px-about-colophon"
        aria-label="Site credits"
        onPointerEnter={() => mascotSay('Designed and engineered by one very busy student.')}
      >
        <div className="px-about-container px-about-colophon-inner">
          <div className="px-about-colophon-copy">
            <span className="px-about-acid-tag">PLATFORM &amp; DESIGN</span>
            <p>
              This site was designed and engineered by{' '}
              <a
                href="https://midhunkm.pages.dev"
                target="_blank"
                rel="noopener noreferrer"
                className="px-about-inline-link"
              >
                Midhun K M <ArrowUpRight size={13} strokeWidth={2} />
              </a>
            </p>
          </div>
          <Link
            className="px-about-inline-link"
            to="/team"
            data-mascot-target="about-team"
            data-mascot-label="Meet the team"
            data-mascot-hover="Meet the crew who pulled this off."
          >
            Meet the team <ArrowRight size={14} strokeWidth={2} />
          </Link>
        </div>
      </section>
    </div>
  );
}

export function EventsPage() {
  const { edition, slug } = useSite();
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query);
  const [category, setCategory] = useState('');
  const [format, setFormat] = useState('');
  const [page, setPage] = useState(1);

  const categories = useAsync(() => publicApi.categories(slug), [slug], {
    enabled: Boolean(slug),
  });
  const list = useAsync(
    () =>
      publicApi.events(slug, {
        q: debounced,
        category,
        format,
        page,
        pageSize: 12,
        sort: 'date',
      }),
    [slug, debounced, category, format, page],
    { enabled: Boolean(slug) },
  );

  useEffect(() => {
    setPage(1);
  }, [debounced, category, format]);

  const events = list.data?.data || [];
  const meta = list.data?.meta || { total: 0, page: 1, pageSize: 12 };
  const lastPage = Math.max(1, Math.ceil((meta.total || 0) / (meta.pageSize || 12)));
  const dayGroups = groupEventsByDay(events);

  return (
    <div className="page-scene-page">
      <PageScene bg={ARENA_ART} mascot={EVENT_SCENE_ART} wide>
        <PageTitle
          kicker="Events"
          title={
            <>
              All
              <br />
              <em>events.</em>
            </>
          }
          desc="Search by name, category or format."
        />
      </PageScene>
      <div className="exc-shell">
        <section
          className="section directory exc-catalogue"
          onPointerEnter={() => mascotSay('The whole catalogue, hover a card for the scoop.')}
        >
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
            <span className="results-summary">
              {meta.total} {meta.total === 1 ? 'event' : 'events'}
              <span>·</span>
              {edition?.registrationOpen ? 'registration open' : 'registration closed'}
              <span>·</span>
              page {meta.page} of {lastPage}
            </span>
            <span className="results-sort">
              <Clock3 size={12} strokeWidth={1.8} aria-hidden="true" />
              Programme order
            </span>
          </div>
          {list.loading ? (
            <Loading label="Loading the catalogue" rows={2} />
          ) : list.error ? (
            <ErrorBox error={list.error} onRetry={list.reload} />
          ) : events.length ? (
            <>
              {dayGroups.map((group, groupIndex) => (
                <section
                  className="exc-day"
                  key={group.key}
                  aria-labelledby={`exc-day-${group.key}`}
                  onPointerEnter={() =>
                    mascotSay(`${group.label}, ${group.events.length} events to wrestle with.`)
                  }
                >
                  <header className="exc-day-head">
                    <span className="exc-day-index">Day {groupIndex + 1}</span>
                    <h2 className="exc-day-title" id={`exc-day-${group.key}`}>
                      {group.label}
                    </h2>
                    <span className="exc-day-count">
                      {group.events.length} {group.events.length === 1 ? 'event' : 'events'}
                    </span>
                  </header>
                  <div className="exc-grid">
                    {group.events.map((event, index) => (
                      <EventCard key={event.id} event={event} index={index} />
                    ))}
                  </div>
                </section>
              ))}
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
                onPointerEnter={() => mascotSay('No luck? Clear the filters and start fresh.')}
              >
                Clear filters
              </Button>
            </Empty>
          )}
        </section>
      </div>
    </div>
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
        <div className="center-actions" style={{ marginTop: '24px' }}>
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
        <p>The event may have been removed or moved in the catalogue.</p>
        <div className="hero-actions">
          <Button
            to="/"
            icon={ArrowUpRight}
            onPointerEnter={() => mascotSay('Wrong turn, let us head back.', 5200, 'jump')}
          >
            Back to the convention
          </Button>
          <Button
            to="/events"
            variant="ghost"
            onPointerEnter={() => mascotSay('Browse events, the real ones are waiting.', 5200, 'wave')}
          >
            Browse events
          </Button>
        </div>
      </section>
    );
  }

  const isTeam = event.format === 'team';
  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
        <PageTitle
          kicker={event.categoryName || 'Event'}
          title={<>{event.title}</>}
          desc={event.summary}
        />
      </PageScene>

      <section
        className="px-about-intro-band px-event-intro"
        aria-label="Event at a glance"
        onPointerEnter={() => mascotSay('The quick rundown, format, seats, and the fee.')}
      >
        <div className="px-about-container">
          <div className="px-about-intro-head">
            <h2>{isTeam ? 'BUILD THE ROSTER, SHARE THE ENTRY' : 'ONE ENTRANT, ONE SEAT'}</h2>
            <p>
              {isTeam
                ? 'Registering adds one seat for you. A team is optional: create one or join with a link any time, and the price never changes.'
                : 'Registering adds one seat for you. Your pass allowance decides whether it is included, free, or paid; nothing else is required.'}
            </p>
          </div>
          <div className="px-about-counter-row">
            <div className="px-about-counter-item">
              <b>{isTeam ? `${event.teamMinSize || 2}–${event.teamMaxSize || 4}` : 'Solo'}</b>
              <span>{isTeam ? 'Team size' : 'Format'}</span>
            </div>
            <div className="px-about-counter-item">
              <b>{event.startsAt ? date(event.startsAt) : 'TBA'}</b>
              <span>Date</span>
            </div>
            <div className="px-about-counter-item is-wide">
              <b className="is-compact" title={event.venueRoom || 'To be announced'}>
                {event.venueRoom || 'To be announced'}
              </b>
              <span>Venue</span>
            </div>
            <div className="px-about-counter-item">
              <b>{event.capacity || 'Open'}</b>
              <span>{event.capacity ? 'Capacity' : 'No cap'}</span>
            </div>
          </div>
        </div>
      </section>

      <section
        className="px-about-visual-band px-event-visual"
        aria-label="Event dossier"
        onPointerEnter={() => mascotSay('This is the one you came for. Make it count.')}
      >
        <div className="px-about-container px-about-visual-grid">
          <div className="px-about-visual-media">
            <img
              src={event.bannerUrl || PARALLAX_BG_VAULT}
              alt={`${event.title} banner`}
              loading="lazy"
            />
          </div>
          <div className="px-about-visual-copy">
            <div className="px-about-visual-brand">
              <img
                src={event.iconId ? publicApi.iconUrl(event.iconId) : PARALLAX_BG_VAULT}
                alt=""
                loading="lazy"
              />
              <div>
                <span className="px-about-acid-tag">EVENT DOSSIER</span>
                <h3>{event.title}</h3>
              </div>
            </div>

            <div className="px-about-visual-facts">
              <div>
                <span>Included value</span>
                <b>{money(event.baseValuePaise || 0)}</b>
              </div>
              <div>
                <span>Add-on fee</span>
                <b>
                  {event.addonPricePaise ? (
                    <>
                      <s className="exc-was">
                        {money(eventListPricePaise(event.addonPricePaise, event.slug))}
                      </s>
                      {money(event.addonPricePaise)}
                    </>
                  ) : (
                    'Free'
                  )}
                </b>
              </div>
              <div>
                <span>Fee basis</span>
                <b>
                  {event.teamFeeBasis === 'per_team'
                    ? 'Once per team'
                    : event.teamFeeBasis === 'per_participant'
                      ? 'Per participant'
                      : 'Set by the pass'}
                </b>
              </div>
              <div>
                <span>Registration</span>
                <b>
                  {event.registrationOpen
                    ? event.registrationClosesAt
                      ? `Closes ${date(event.registrationClosesAt)}`
                      : 'Open'
                    : 'Closed'}
                </b>
              </div>
            </div>

            <div className="px-about-row-actions">
              <Link
                className="px-about-pill-btn"
                to={isTeam ? '/portal/teams' : `/portal/events/${event.slug}`}
                data-mascot-target="event-plan"
                data-mascot-label={isTeam ? 'Create or join team' : 'Plan this event'}
                data-mascot-hover={
                  isTeam
                    ? 'Round up your squad before slots fill up!'
                    : 'Ready to lock this one in?'
                }
              >
                {isTeam ? 'Create or join team' : 'Plan this event'}
              </Link>
              <Link
                to="/events"
                className="px-about-inline-link"
                data-mascot-target="event-back"
                data-mascot-label="All events"
                data-mascot-hover="Back to the full lineup?"
              >
                All events <ArrowUpRight size={14} strokeWidth={2} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section
        className="px-about-intro-band px-event-brief-band"
        aria-label="Event details"
        onPointerEnter={() => mascotSay('The brief, rules, prizes, and the fine print.')}
      >
        <div className="px-about-container">
          <div className="px-about-intro-head">
            <h2>THE BRIEF</h2>
            <p>
              Read the format, the rules and the prizes before you spend a seat. Eligibility is
              confirmed through the participant portal.
            </p>
          </div>

          <div className="px-event-brief">
            <div className="px-event-brief-main">
              {event.descriptionHtml ? (
                <div
                  className="rich-text"
                  dangerouslySetInnerHTML={{ __html: event.descriptionHtml }}
                />
              ) : (
                <p>{event.summary}</p>
              )}

          {isTeam || event.soloGuideHtml ? (
            <div className="px-event-guide-grid">
              {event.soloGuideHtml ? (
                <div className="px-event-guide">
                  <span className="px-about-acid-tag">SOLO ENTRY</span>
                  <div
                    className="rich-text"
                    dangerouslySetInnerHTML={{ __html: event.soloGuideHtml }}
                  />
                </div>
              ) : null}
              {isTeam && event.teamGuideHtml ? (
                <div className="px-event-guide">
                  <span className="px-about-acid-tag">TEAM ENTRY</span>
                  <div
                    className="rich-text"
                    dangerouslySetInnerHTML={{ __html: event.teamGuideHtml }}
                  />
                </div>
              ) : null}
            </div>
          ) : null}

            </div>

            <aside className="px-event-brief-side">
              <span className="px-about-acid-tag">PRIZES</span>
              {event.prizesHtml ? (
                <div
                  className="rich-text"
                  dangerouslySetInnerHTML={{ __html: event.prizesHtml }}
                />
              ) : (
                <p className="px-event-side-empty">To be announced.</p>
              )}

              {event.rulesHtml ? (
                <>
                  <h3 className="px-event-subhead">Requirements &amp; rules</h3>
                  <div
                    className="rich-text"
                    dangerouslySetInnerHTML={{ __html: event.rulesHtml }}
                  />
                </>
              ) : null}

              <p className="notice">
                <ShieldCheck size={16} strokeWidth={1.5} /> Eligibility is confirmed through the
                participant portal before a registration is treated as final.
              </p>
            </aside>
          </div>
        </div>
      </section>
    </div>
  );
}

export function PassPage() {
  const { policy, slug } = useSite();
  const tiers = useAsync(() => publicApi.registrationCategories(slug), [slug], {
    enabled: Boolean(slug),
  });
  const registrationTiers = tiers.data?.data || [];
  const mode = policy?.includedSelectionMode === 'exact' ? 'Exactly' : 'Up to';
  const lunchDays = policy?.lunchIncludedDays?.length || 2;
  const includedCount = policy?.includedEventCount ?? 3;
  const valueCap = policy?.includedValueCapPaise != null ? money(policy.includedValueCapPaise) : null;

  const SAMPLE_PASS_IMG = `${import.meta.env.BASE_URL}images/sample-pass.png`;

  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
        <PageTitle
          kicker="Pass"
          title={
            <>
              One pass.
              <br />
              <em>Both days.</em>
            </>
          }
          desc="Lunch included. Pick your events, add more if you want."
        />
      </PageScene>

      {/* Band 1: Sample Pass Showcase matching /about visual split */}
      <section className="px-pass-showcase" aria-label="Convention pass overview">
        <div className="px-about-container px-about-visual-grid">
          <div
            className="px-about-visual-media"
            onPointerEnter={() => mascotSay('Clean pass, right? Covers both days.')}
          >
            <img
              src={SAMPLE_PASS_IMG}
              alt="Sample Parallax 2027 digital and physical convention pass"
              loading="lazy"
            />
          </div>

          <div className="px-about-visual-copy">
            <div className="px-pass-showcase-head">
              <span className="px-about-acid-tag">ALL-ACCESS CREDENTIAL</span>
              <h2>Parallax 2027 Convention Pass</h2>
            </div>

            <div className="px-about-visual-facts">
              <div>
                <span>Validity</span>
                <b>{lunchDays} Days (Full Campus Access)</b>
              </div>
              <div>
                <span>Included Events</span>
                <b>
                  {mode} {includedCount} Events ({valueCap || 'No cap'})
                </b>
              </div>
              <div>
                <span>Meals &amp; Check-in</span>
                <b>Lunch ({lunchDays} Days) + Digital QR</b>
              </div>
            </div>

            <div className="px-about-row-actions">
              <Link
                className="px-about-pill-btn"
                to="/portal/registration"
                data-mascot-target="pass-get"
                data-mascot-label="Get your pass"
                data-mascot-hover="Get it now, one pass covers both days!"
              >
                Get your pass
              </Link>
              <Link
                className="px-about-inline-link"
                to="/faq"
                data-mascot-target="pass-faq"
                data-mascot-label="Read FAQ"
                data-mascot-hover="Got doubts? The FAQ has receipts."
              >
                Read FAQ <ArrowUpRight size={14} strokeWidth={2} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Band 2: Clean architectural tier ledger (replaces 3 cheap dark boxes) */}
      {registrationTiers.length ? (
        <section className="px-pass-tiers-band" id="registration">
          <div className="px-about-container">
            <div className="px-about-intro-head px-pass-intro-head">
              <h2>PICK YOUR CONVENTION CATEGORY</h2>
              <p>
                Fees depend on your college and ISTE membership, verified live at the registration
                desk.
              </p>
            </div>

            <div className="px-pass-tier-columns">
              {registrationTiers.map((tier) => {
                const isFeatured = tier.code === 'iste_member';
                return (
                  <article
                    className={`px-pass-tier-col${isFeatured ? ' is-featured' : ''}`}
                    key={tier.id}
                    onPointerEnter={() =>
                      mascotSay(
                        tier.code === 'iste_member'
                          ? 'Make sure you have your ISTE membership btw!'
                          : tier.code === 'polytechnic'
                            ? "Polytechnic student? Didn't expect that one!"
                            : 'Get it now, full two-day pass, no membership needed!',
                      )
                    }
                  >
                    <div className="px-pass-tier-col-top">
                      <span className={`px-pass-tier-pill${isFeatured ? ' is-gold' : ''}`}>
                        {isFeatured
                          ? 'ISTE verified'
                          : tier.code === 'polytechnic'
                            ? 'Polytechnic'
                            : 'College ID'}
                      </span>
                      <h3>{tier.name}</h3>
                    </div>

                    <div className="px-pass-tier-col-price">
                      <strong>{money(tier.feePaise)}</strong>
                      <span>/ pass</span>
                    </div>

                    <p className="px-pass-tier-col-desc">{tier.description}</p>

                    <ul className="px-pass-tier-doc-list">
                      {(tier.requiredDocuments || []).map((doc) => (
                        <li key={doc.type}>
                          <Check size={14} strokeWidth={2.2} aria-hidden="true" />
                          <span>
                            {doc.label}
                            {!doc.required ? ' (Optional)' : ''}
                          </span>
                        </li>
                      ))}
                    </ul>

                    <Link
                      className={`px-pass-tier-col-cta${isFeatured ? ' is-featured' : ''}`}
                      to="/portal/registration"
                      data-mascot-target={`pass-tier-${tier.code}`}
                      data-mascot-label={tier.name}
                      data-mascot-hover={`Going with ${tier.name}? Nice.`}
                    >
                      <span>Select Category</span>
                      <ArrowRight size={14} strokeWidth={2.2} />
                    </Link>
                  </article>
                );
              })}
            </div>
          </div>
        </section>
      ) : null}

      <section
        className="section px-pass-rules"
        aria-label="How the convention pass works"
        onPointerEnter={() => mascotSay('Pass first, then pick your programme. Simple as that.')}
      >
        <div className="px-pass-rules-head">
          <div>
            <h2>Pass first. Then pick your programme.</h2>
            <p>
              Lunch on both days ({lunchDays} days) and verified digital QR entry are included with
              every category above.
            </p>
          </div>
          <div className="px-pass-rules-meta">
            <span>
              <small>Included value cap</small>
              <b>{valueCap || 'No cap'}</b>
            </span>
            <span>
              <small>Selection locks</small>
              <b>{policy?.selectionChangeDeadline ? date(policy.selectionChangeDeadline) : 'TBA'}</b>
            </span>
            <span>
              <small>Add-on hold</small>
              <b>{policy?.holdMinutes || 15} min</b>
            </span>
          </div>
        </div>

        <ol className="px-pass-statements">
          <li>
            <span>01</span>
            <div>
              <h3>Every participant gets one pass</h3>
              <p>
                Includes lunch on both convention days and is required before reserving any event
                in the catalogue.
              </p>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <h3>
                Choose {mode.toLowerCase()} {includedCount} eligible events
              </h3>
              <p>
                {valueCap
                  ? `Their combined published base values stay within the ${valueCap} allowance. Your pass fee is never deducted from that sum.`
                  : 'Reserve eligible events directly from your participant portal.'}
              </p>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <h3>Add extra events separately</h3>
              <p>
                Additional challenge registrations use each event&apos;s published add-on fee and
                can be reserved after your pass.
              </p>
            </div>
          </li>
          <li>
            <span>04</span>
            <div>
              <h3>Team members each hold a pass</h3>
              <p>
                {policy?.teamMembersRequirePass
                  ? 'Every team member must hold an active pass before the team entry is confirmed.'
                  : 'Team entry is available without a separate pass per member in this edition.'}
              </p>
            </div>
          </li>
        </ol>

        <div className="px-pass-rules-foot">
          <Button
            to="/portal/registration"
            variant="primary"
            icon={ArrowRight}
            data-mascot-target="pass-start"
            data-mascot-label="Start registration"
            data-mascot-hover="Start registration, let us make it official."
          >
            Start registration
          </Button>
          <Link
            className="px-about-inline-link"
            to="/faq"
            data-mascot-target="pass-rules-faq"
            data-mascot-label="Read the FAQ"
            data-mascot-hover="Read the FAQ first if you are the careful type."
          >
            Read the FAQ <ArrowUpRight size={14} strokeWidth={2} />
          </Link>
        </div>
      </section>
    </div>
  );
}

export function SchedulePage() {
  const { slug } = useSite();
  const schedule = useAsync(() => publicApi.schedule(slug), [slug], {
    enabled: Boolean(slug),
  });
  const days = schedule.data?.data || [];

  const formatTimeSlot = (startIso, endIso) => {
    if (!startIso) return 'TBA';
    const s = time(startIso);
    const e = time(endIso);
    if (!e) return s;
    const sNum = s.replace(/\s*[ap]m/i, '').trim();
    const eClean = e.toUpperCase().trim();
    return `${sNum} – ${eClean}`;
  };

  const totalSessions = days.reduce((sum, d) => sum + (d.items?.length || 0), 0);

  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
        <PageTitle
          kicker="Schedule"
          title={
            <>
              The
              <br />
              <em>schedule.</em>
            </>
          }
          desc="Every session in order, with times and rooms."
          aside={
            totalSessions > 0 ? (
              <div className="schedule-stat-pill">
                <span className="schedule-stat-num">{totalSessions}</span>
                <span className="schedule-stat-label">sessions scheduled</span>
              </div>
            ) : null
          }
        />
      </PageScene>
      <section
        className="section apple-schedule-section"
        onPointerEnter={() => mascotSay('Every session in order, hover one and I will judge your timing.')}
      >
        {schedule.error ? <ErrorBox error={schedule.error} onRetry={schedule.reload} /> : null}
        {!schedule.loading && !schedule.error && !days.length ? (
          <Empty
            title="The schedule is not published"
            desc="Sessions will appear here once released."
          />
        ) : null}
        <ScheduleBoard days={days} loading={schedule.loading} />
      </section>
    </div>
  );
}

export function VenuePage() {
  const { edition } = useSite();
  if (!edition) return <Loading label="Loading venue details" rows={2} />;

  const randomKm = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

  const CAMPUS_IMG = `${import.meta.env.BASE_URL}images/nssce-main-campus.jpg`;
  const PGT_IMG = `${import.meta.env.BASE_URL}images/pgt-station.jpg`;
  const KSRTC_IMG = `${import.meta.env.BASE_URL}images/pgt-ksrtc.jpg`;
  const CJB_IMG = `${import.meta.env.BASE_URL}images/cjb-airport.jpg`;
  const mapsUrl = 'https://maps.google.com/?q=NSS+College+of+Engineering+Palakkad';

  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
        <PageTitle
          kicker="Venue"
          title={
            <>
              Meet us at
              <br />
              <em>{edition?.city?.split(',')[0] || 'Palakkad'}.</em>
            </>
          }
          desc={`${placeLabel(edition?.venue, edition?.city) || 'NSSCE Campus, Palakkad'}.`}
        />
      </PageScene>

      {/* Band 1: Campus Visual Split matching /about */}
      <section
        className="px-venue-campus-band"
        aria-label="Host institution"
        onPointerEnter={() => mascotSay('Oh, I actually study here!')}
      >
        <div className="px-about-container px-about-visual-grid">
          <div
            className="px-about-visual-media"
            onPointerEnter={() => mascotSay('That is NSSCE right there. Pretty neat, huh?')}
          >
            <img
              src={CAMPUS_IMG}
              alt="NSS College of Engineering main campus, Akathethara, Palakkad"
              loading="lazy"
            />
          </div>

          <div className="px-about-visual-copy">
            <div className="px-about-visual-brand">
              <img src={NSSCE} alt={`${edition?.host || 'NSSCE'} emblem`} />
              <div>
                <span className="px-about-acid-tag">HOST INSTITUTION • EST. 1960</span>
                <h2>{edition?.host || 'NSS College of Engineering, Palakkad'}</h2>
              </div>
            </div>

            <p className="px-venue-lead">
              Established in 1960 by the Nair Service Society and affiliated to APJ Abdul Kalam
              Technological University (KTU), NSSCE spans a 125-acre campus in NSS Nagar,
              Akathethara near the Western Ghats foothills.
            </p>

            <div className="px-about-visual-facts">
              <div>
                <span>Dates</span>
                <b>{dateRange(edition?.startsAt, edition?.endsAt)}</b>
              </div>
              <div>
                <span>Accreditation</span>
                <b>AICTE Approved • NBA &amp; NAAC</b>
              </div>
              <div>
                <span>Check-in Desk</span>
                <b>Main Auditorium (08:30 IST)</b>
              </div>
            </div>

            <div className="px-about-row-actions">
              <a
                className="px-about-pill-btn"
                href={mapsUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-mascot-target="venue-directions"
                data-mascot-label="Get directions"
                data-mascot-hover="Get directions, I will ride shotgun."
              >
                Get directions
              </a>
              <Link
                className="px-about-inline-link"
                to="/schedule"
                data-mascot-target="venue-schedule"
                data-mascot-label="Browse schedule"
                data-mascot-hover="Browse the schedule while you plan the trip."
              >
                Browse schedule <ArrowUpRight size={14} strokeWidth={2} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Band 2: Interactive Google Map Split */}
      <section
        className="px-venue-map-band"
        aria-label="Campus map and coordinates"
        onPointerEnter={() => mascotSay('Here is exactly where to show up. No excuses.')}
      >
        <div className="px-about-container px-venue-map-grid">
          <div className="px-venue-map-copy">
            <span className="px-about-acid-tag">CAMPUS LOCATION</span>
            <h2>NSS Nagar, Akathethara</h2>
            <p className="px-venue-lead">{VENUE_ADDRESS}</p>

            <div className="px-about-visual-facts">
              <div>
                <span>Area</span>
                <b>Akathethara (Near Malampuzha Rd)</b>
              </div>
              <div>
                <span>Town Center</span>
                <b>Palakkad Town (~9 km)</b>
              </div>
              <div>
                <span>Official Site</span>
                <b>nssce.ac.in</b>
              </div>
            </div>

            <div className="px-about-row-actions">
              <a
                className="px-about-inline-link"
                href={mapsUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-mascot-target="venue-gmaps"
                data-mascot-label="Open in Google Maps"
                data-mascot-hover="Open it in Google Maps, I already did."
              >
                Open in Google Maps <ArrowUpRight size={14} strokeWidth={2} />
              </a>
            </div>
          </div>

          <div
            className="px-venue-map-embed"
            onPointerEnter={() => mascotSay('Let me check my maps for the location…')}
          >
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
        </div>
      </section>

      {/* Band 3: Nearest Railway & Airport with real photos */}
      <section
        className="px-venue-transit-band"
        aria-label="Nearest railway and airport"
        onPointerEnter={() => mascotSay('Getting here? Train, bus, or plane, your call.')}
      >
        <div className="px-about-container">
          <div className="px-about-intro-head px-venue-transit-head">
            <h2>NEAREST RAIL &amp; AIR TRANSIT</h2>
            <p>Direct rail and highway access to Akathethara from major hubs across Kerala and Tamil Nadu.</p>
          </div>

          <div className="px-venue-transit-grid">
            <article
              className="px-venue-transit-card"
              onPointerEnter={() =>
                mascotSay(`Palakkad Junction (PGT)? About ${randomKm(4, 7)} km from here.`)
              }
            >
              <div className="px-venue-transit-img">
                <img
                  src={PGT_IMG}
                  alt="Palakkad Junction Railway Station (PGT)"
                  loading="lazy"
                />
              </div>
              <div className="px-venue-transit-body">
                <span className="px-about-acid-tag">RAILWAY • ~4–7 KM</span>
                <h3>Palakkad Junction (PGT)</h3>
                <p>
                  Direct rail links from Kochi, Thrissur, Kozhikode, Coimbatore, and
                  Thiruvananthapuram. About 15 minutes from campus via Olavakkode / Malampuzha
                  Road.
                </p>
              </div>
            </article>

            <article
              className="px-venue-transit-card"
              onPointerEnter={() =>
                mascotSay(`KSRTC Bus Stand? Roughly ${randomKm(9, 12)} km, give or take.`)
              }
            >
              <div className="px-venue-transit-img">
                <img
                  src={KSRTC_IMG}
                  alt="KSRTC Bus Terminal Palakkad"
                  loading="lazy"
                />
              </div>
              <div className="px-venue-transit-body">
                <span className="px-about-acid-tag">BUS • ~9-10 KM</span>
                <h3>KSRTC Bus Stand, Palakkad</h3>
                <p>
                  Intercity KSRTC buses from across Kerala. About 20 to 30 minutes to NSSCE
                  Akathethara via local Malampuzha or Olavakkode buses and autos.
                </p>
              </div>
            </article>

            <article
              className="px-venue-transit-card"
              onPointerEnter={() =>
                mascotSay(
                  `Coimbatore Airport (CJB)? That's a solid ${randomKm(60, 70)} km haul.`,
                  5200,
                  'jump',
                )
              }
            >
              <div className="px-venue-transit-img">
                <img
                  src={CJB_IMG}
                  alt="Coimbatore International Airport (CJB)"
                  loading="lazy"
                />
              </div>
              <div className="px-venue-transit-body">
                <span className="px-about-acid-tag">AIRPORT • ~65 KM</span>
                <h3>Coimbatore International Airport (CJB)</h3>
                <p>
                  Nearest commercial airport (~1 hr 30 min via NH-544). Prepaid airport cabs and
                  frequent intercity buses connect directly to Palakkad.
                </p>
              </div>
            </article>
          </div>
        </div>
      </section>
    </div>
  );
}

export function FAQPage() {
  const { policy, edition, slug } = useSite();
  const [activeGroup, setActiveGroup] = useState('all');
  const [query, setQuery] = useState('');
  const mode = policy?.includedSelectionMode === 'exact' ? 'Exactly' : 'Up to';
  // Attendees pay their registration tier, not the policy's fallback price.
  // Quoting the fallback as "the pass price" contradicted the pass page.
  const tiers = useAsync(() => publicApi.registrationCategories(slug), [slug], {
    enabled: Boolean(slug),
  });
  const registrationTiers = tiers.data?.data || [];
  const cheapestTier = registrationTiers.reduce(
    (cheapest, tier) => (!cheapest || tier.feePaise < cheapest.feePaise ? tier : cheapest),
    null,
  );
  const passPriceAnswer = cheapestTier
    ? `Yes. Every participant needs their own pass, from ${money(cheapestTier.feePaise)} (${registrationTiers
        .map((tier) => `${tier.name} ${money(tier.feePaise)}`)
        .join(' / ')}). Event add-on fees never replace it.`
    : `Yes. Every participant needs their own ${money(policy?.passPricePaise)} pass. Event add-on fees never replace it.`;

  const rows = [
    {
      group: 'passes',
      q: 'Is the convention pass mandatory?',
      a: passPriceAnswer,
    },
    {
      group: 'passes',
      q: 'What does the pass include?',
      a: `Lunch on ${(policy?.lunchIncludedDays || []).map(dayLabel).join(' and ') || 'both convention days'}, full floor access, and an included event allowance.`,
    },
    {
      group: 'events',
      q: 'How many included events can I select?',
      a:
        policy?.includedValueCapPaise != null
          ? `${mode} ${policy?.includedEventCount ?? 3} eligible events, with a base-value cap of ${money(policy.includedValueCapPaise)}.`
          : `${mode} ${policy?.includedEventCount ?? 3} eligible events, with no base-value cap.`,
    },
    {
      group: 'events',
      q: 'Can I change my included selections?',
      a: `Until ${date(policy?.selectionChangeDeadline)}. After that the selection locks and the portal disables edits.`,
    },
    {
      group: 'events',
      q: 'Can I register for more events?',
      a: policy?.addonRequiresPass
        ? 'Yes, after the pass. Extra events use their published add-on fee.'
        : 'Yes. Add-on events can be reserved separately.',
    },
    {
      group: 'events',
      q: 'How does the team rule work?',
      a: policy?.teamMembersRequirePass
        ? 'Each team member must hold an active pass before the team entry can be confirmed.'
        : 'Team entry is available without a separate pass for each member in this edition.',
    },
    {
      group: 'support',
      q: 'How is student eligibility verified?',
      a: 'Upload your college ID card and passport photo with your registration. The registration desk reviews them and approves your pass tier before your pass activates.',
    },
    {
      group: 'passes',
      q: 'What happens after payment?',
      a: 'The pass activates immediately, included registrations are created, and an entry ticket with a scannable token is issued.',
    },
    {
      group: 'support',
      q: 'Can I get a refund?',
      a: 'Refunds are handled by the finance team against a paid order. Ask the organisers through the contact page.',
    },
    {
      group: 'support',
      q: 'Where do I get help?',
      a: `Write to ${edition?.contactEmail || 'iste@nssce.ac.in'} or visit the Main Auditorium desk at NSS College of Engineering.`,
    },
  ];

  const groups = [
    { id: 'all', label: 'All Topics' },
    { id: 'passes', label: 'Passes & Pricing' },
    { id: 'events', label: 'Events & Teams' },
    { id: 'support', label: 'Verification & Support' },
  ];

  const needle = query.trim().toLowerCase();
  const visibleRows = rows.filter((item) => {
    const groupOk = activeGroup === 'all' || item.group === activeGroup;
    const queryOk =
      !needle || item.q.toLowerCase().includes(needle) || item.a.toLowerCase().includes(needle);
    return groupOk && queryOk;
  });

  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
        <PageTitle
          kicker="FAQ"
          title={
            <>
              Common
              <br />
              <em>questions.</em>
            </>
          }
          desc="Passes, events, verification and refunds."
        />
      </PageScene>

      <section
        className="px-faq-band"
        aria-label="Frequently asked questions"
        onPointerEnter={() => mascotSay('Plan it yourself, everything you need is right here.')}
      >
        <div className="px-about-container px-faq-grid">
          <aside className="px-faq-aside">
            <span className="px-about-acid-tag">BEFORE YOU ASK</span>
            <h2>
              Clear answers.
              <br />
              No fine print.
            </h2>
            <p>
              Passes, event choices, verification, and refunds. Every operational rule for Parallax
              2027 in one place.
            </p>

            <div className="px-about-visual-facts">
              <div>
                <span>Starting Pass</span>
                <b>
                  {cheapestTier
                    ? `From ${money(cheapestTier.feePaise)}`
                    : money(policy?.passPricePaise)}
                </b>
              </div>
              <div>
                <span>Included Events</span>
                <b>{policy?.includedEventCount ?? 3}</b>
              </div>
              <div>
                <span>Campus Lunch</span>
                <b>{(policy?.lunchIncludedDays || []).length || 2} Days</b>
              </div>
              <div>
                <span>Selection Lock</span>
                <b>{date(policy?.selectionChangeDeadline) || 'Convention Eve'}</b>
              </div>
            </div>

            <div className="px-about-row-actions">
              <Link
                className="px-about-pill-btn"
                to="/pass"
                data-mascot-target="faq-pass"
                data-mascot-label="See pass options"
                data-mascot-hover="See the pass options, no fine print, promise."
              >
                See pass options
              </Link>
              <Link
                className="px-about-inline-link"
                to="/contact"
                data-mascot-target="faq-contact"
                data-mascot-label="Talk to the desk"
                data-mascot-hover="Talk to the desk, real humans, I swear."
              >
                Talk to the desk <ArrowRight size={14} strokeWidth={2} />
              </Link>
            </div>
          </aside>

          <div className="px-faq-main">
            <div className="px-faq-controls">
              <div className="contact-topic-chips" role="tablist" aria-label="FAQ topics">
                {groups.map((g) => (
                  <button
                    key={g.id}
                    type="button"
                    role="tab"
                    aria-selected={activeGroup === g.id}
                    className={`px-contact-chip${activeGroup === g.id ? ' is-active' : ''}`}
                    onClick={() => setActiveGroup(g.id)}
                    onPointerEnter={() => mascotSay(`Browsing ${g.label}? Solid place to start.`)}
                  >
                    {g.label}
                  </button>
                ))}
              </div>

              <input
                type="search"
                className="px-contact-input px-faq-search"
                placeholder="Filter questions (e.g. lunch, refund, team, ID)..."
                aria-label="Filter FAQ questions"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => mascotSay('Type a keyword, I will help you dig.')}
              />
            </div>

            <div className="px-faq-list">
              {visibleRows.length ? (
                visibleRows.map((item, idx) => (
                  <details className="px-faq-item" key={item.q}>
                    <summary className="px-faq-summary">
                      <span className="px-faq-num">{String(idx + 1).padStart(2, '0')}</span>
                      <span className="px-faq-question">{item.q}</span>
                      <span className="px-faq-chevron" aria-hidden="true">
                        <ChevronDown size={18} strokeWidth={2} />
                      </span>
                    </summary>
                    <div className="px-faq-answer">
                      <p>{item.a}</p>
                    </div>
                  </details>
                ))
              ) : (
                <div className="px-faq-empty">
                  <p>No matching questions found for "{query}".</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="px-contact-faq-band" aria-label="Contact support">
        <div className="px-about-container">
          <div className="px-contact-faq-strip">
            <div className="px-contact-faq-copy">
              <HelpCircle size={20} strokeWidth={1.8} className="px-contact-channel-icon" />
              <div>
                <h3>Still have a specific question?</h3>
                <p>Send a direct inquiry to the organising desk or check your portal status.</p>
              </div>
            </div>
            <Link
              to="/contact"
              className="px-about-inline-link"
              data-mascot-target="faq-contact-desk"
              data-mascot-label="Contact the desk"
              data-mascot-hover="Still stuck? The desk has your back."
            >
              <span>Contact the desk</span>
              <ArrowRight size={14} strokeWidth={2} />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

const TEAM_GROUPS = [
  {
    title: 'Faculty Leadership',
    description: 'Faculty guiding the convention.',
    members: [
      {
        name: 'Dr. Sudeep U',
        role: 'Faculty Chairperson',
        image: 'faculty-chairperson.jpg',
      },
      {
        name: 'Dr. Praseeda K I',
        role: 'Faculty Secretary',
        image: 'faculty-secretary.jpg',
      },
    ],
  },
  {
    title: 'Student Leadership',
    description: 'Student leads.',
    members: [
      {
        name: 'Kaladharan Lal',
        role: 'Chairperson',
        image: 'chairperson.jpg',
      },
      {
        name: 'Sandra',
        role: 'Secretary',
        image: 'secretary.jpg',
      },
    ],
  },
  {
    title: 'Web-Dev Team',
    description: 'Built the site.',
    members: [
      {
        name: 'Midhun K M',
        role: 'Frontend & Backend',
        image: 'Midhunkm.jpg',
        featured: true,
        link: 'https://midhunkm.pages.dev/',
      },
      {
        name: 'Arjun M L',
        role: 'Frontend',
        image: 'frontend.jpg',
        featured: true,
        link: 'https://arjc.github.io/',
      },
      {
        name: 'Kaladharan Lal',
        role: 'System Design',
        image: 'chairperson.jpg',
        featured: true,
      },
    ],
  },
  {
    title: 'Core Organising Team',
    description: 'Events, design, publicity and finance.',
    members: [
      {
        name: 'Athira Haridas K V',
        role: 'Events Coordinator',
        image: 'events-coordinator.jpg',
      },
      {
        name: 'Mofaq Asfar A',
        role: 'Events Coordinator',
        image: 'events-coordinator2.jpg',
      },
      {
        name: 'Anagha K',
        role: 'Design Coordinator',
        image: 'design-coordinator.jpg',
      },
      {
        name: 'Jishnu J',
        role: 'Publicity Coordinator',
        image: 'publicity-coordinator.jpg',
      },
      {
        name: 'Amjum Shareef A S',
        role: 'Publicity Coordinator',
        image: 'publicity-coordinator2.jpg',
      },
      {
        name: 'Anirudh R',
        role: 'Finance Coordinator',
        image: 'finance-coordinator.jpeg',
      },
      {
        name: 'Sandra H Menon',
        role: 'Finance Coordinator',
        image: 'finance-coordinator2.jpg',
      },
      {
        name: 'Sreenath K',
        role: 'Technical Coordinator',
        image: 'technical-coordinator.jpg',
      },
    ],
  },
];

const MIDHUN_NUDGES = [
  'Quietly behind most of what you are clicking right now.',
  'If something here looks smooth, yeah, that was him.',
  'Runs the whole thing, then leaves me to handle you.',
];

const GENERIC_TEAM_LINES = [
  'Part of the crew behind the weekend, go say hi.',
  'One of the familiar faces you will bump into on campus.',
  'On the team making all of this actually happen.',
];

function teamSlug(name = '') {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

let midhunNudgeIdx = 0;

function TeamMemberCard({ member }) {
  const imageUrl = `${import.meta.env.BASE_URL}images/team/${member.image}`;
  const isMidhun = /midhun/i.test(member.name);
  const mascotProps = {
    'data-mascot-target': `team-${teamSlug(member.name)}`,
    'data-mascot-label': member.name,
    'data-mascot-hover': isMidhun
      ? MIDHUN_NUDGES[0]
      : `${member.name}, ${member.role}.`,
    onPointerEnter: () => {
      if (isMidhun) {
        const line = MIDHUN_NUDGES[midhunNudgeIdx % MIDHUN_NUDGES.length];
        midhunNudgeIdx += 1;
        mascotSay(line);
      } else {
        const idx = member.name.length % GENERIC_TEAM_LINES.length;
        mascotSay(`${member.name}? ${GENERIC_TEAM_LINES[idx]}`);
      }
    },
  };

  if (member.featured) {
    const CardTag = member.link ? 'a' : 'article';
    const cardProps = member.link
      ? {
          href: member.link,
          target: '_blank',
          rel: 'noopener noreferrer',
          title: `${member.name}, personal site`,
        }
      : {};

    return (
      <CardTag
        className={`team-member-card is-featured${member.link ? ' is-linked' : ''}`}
        {...cardProps}
        {...mascotProps}
      >
        <div className="tm-frame">
          <div
            className="tm-frame-media"
            data-initials={member.name
              .split(' ')
              .filter(Boolean)
              .slice(0, 2)
              .map((part) => part[0])
              .join('')}
          >
            <img
              src={member.image ? imageUrl : TEAM_PLACEHOLDER}
              alt={member.name}
              loading="lazy"
              onError={teamImageFallback}
            />
          </div>

          <div className="tm-frame-scrim" />

          <img className="tm-frame-art" src={MAIN_FRAME} alt="" aria-hidden="true" />

          <div className="tm-frame-body">
            <span className="tm-frame-kicker">Web Team</span>
            <h3>{member.name}</h3>
            <span>{member.role}</span>
            {member.link ? (
              <span className="tm-frame-link">
                Visit site <ArrowUpRight size={11} strokeWidth={2} />
              </span>
            ) : null}
          </div>
        </div>
      </CardTag>
    );
  }

  return (
    <article className="team-member-card" {...mascotProps}>
      <div className="team-member-image">
        <img
          src={member.image ? imageUrl : TEAM_PLACEHOLDER}
          alt={member.name}
          loading="lazy"
          onError={teamImageFallback}
        />
      </div>

      <div className="team-member-info">
        <h3>{member.name}</h3>
        <span>{member.role}</span>
      </div>
    </article>
  );
}

export function TeamPage() {
  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
        <PageTitle
          kicker="Team"
          title={
            <>
              The
              <br />
              <em>Team.</em>
            </>
          }
          desc="Faculty, student leads and the web team."
        />
      </PageScene>

      <section
        className="px-team-band"
        aria-label="Convention organising team"
        onPointerEnter={() => mascotSay('The crew behind the chaos, hover a face to meet them.')}
      >
        <div className="px-about-container">
          {TEAM_GROUPS.map((group, idx) => (
            <section
              className="px-team-group"
              key={group.title}
              onPointerEnter={() => mascotSay(`${group.title}, the people who make it happen.`)}
            >
              <div className="px-team-group-head">
                <div>
                  <span className="px-about-acid-tag">
                    {String(idx + 1).padStart(2, '0')} / {group.title.toUpperCase()}
                  </span>
                  <h2>{group.title}</h2>
                  <p>{group.description}</p>
                </div>
                <span className="px-team-count">{group.members.length} MEMBERS</span>
              </div>

              <div className={`team-grid${group.title === 'Web-Dev Team' ? ' is-webdev' : ''}`}>
                {group.members.map((member) => (
                  <TeamMemberCard key={member.name} member={member} />
                ))}
              </div>
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}

export function ContactPage() {
  const { edition } = useSite();
  const email = edition?.contactEmail || 'iste@nssce.ac.in';
  const rawHelpdeskPhone = (edition?.helpdeskPhone || edition?.contactPhone || '').trim();
  const hasHelpdeskPhone = Boolean(rawHelpdeskPhone) && !/00000/.test(rawHelpdeskPhone);
  const [topic, setTopic] = useState('general');
  const [name, setName] = useState('');
  const [senderEmail, setSenderEmail] = useState('');
  const [message, setMessage] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const topics = [
    { id: 'pass', label: 'Pass & Pricing' },
    { id: 'events', label: 'Event Rules & Registration' },
    { id: 'teams', label: 'Team Coordination' },
    { id: 'travel', label: 'Travel & Accommodation' },
    { id: 'general', label: 'General Inquiries' },
  ];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setFeedback(null);
    const topicLabel = topics.find((t) => t.id === topic)?.label || 'General Inquiries';

    try {
      await publicApi.submitInquiry({
        name: name.trim(),
        email: senderEmail.trim(),
        category: topicLabel,
        message: message.trim(),
      });
      setFeedback({
        tone: 'good',
        text: `Thank you ${name.trim()}! Your message was dispatched directly to the organizing desk via Telegram. We will email you at ${senderEmail.trim()} shortly.`,
      });
      setMessage('');
      setSent(true);
      mascotSay('Whoa, message sent! Now all you have to do is wait.', 6000, 'wave');
    } catch (err) {
      // Fallback: mailto if network fails
      const subject = encodeURIComponent(`[Parallax 2027] Inquiry: ${topicLabel}`);
      const body = encodeURIComponent(
        `Name: ${name || 'Participant'}\nEmail: ${senderEmail || 'Not provided'}\nCategory: ${topicLabel}\n\nMessage:\n${message}\n\n--\nSent via Parallax 2027 Portal`,
      );
      window.location.href = `mailto:${email}?subject=${subject}&body=${body}`;
      setFeedback({
        tone: 'good',
        text: `Inquiry opened in your email client as fallback to ${email}.`,
      });
      setSent(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={CONTACT_MASCOT_ART}>
        <PageTitle
          kicker="Contact"
          title={
            <>
              Talk to
              <br />
              <em>the team.</em>
            </>
          }
          desc="Direct support for convention passes, event rules, team entries, and campus travel."
        />
      </PageScene>

      {/* Band 1: 3-column hairline channel ledger (matching /about & /pass) */}
      <section
        className="px-contact-channels-band"
        aria-label="Contact channels"
        onPointerEnter={() => mascotSay('Three ways to reach us, pick your favourite.')}
      >
        <div className="px-about-container">
          <div className="px-contact-channel-cols">
            <article className="px-contact-channel-col is-featured">
              <div className="px-contact-channel-top">
                <span className="px-about-acid-tag">01 / DIRECT EMAIL</span>
                <Mail size={18} strokeWidth={1.8} className="px-contact-channel-icon" />
              </div>
              <h3>Email the organisers</h3>
              <p>Pass verification, team entries, certificates, and institutional queries.</p>
              <a
                href={`mailto:${email}`}
                className="px-contact-channel-link"
                data-mascot-target="contact-email"
                data-mascot-label="Email the organisers"
                data-mascot-hover="Email the organisers, the direct line."
              >
                <span>{email}</span>
                <ArrowUpRight size={14} strokeWidth={2} />
              </a>
              {hasHelpdeskPhone ? (
                <a
                  href={`tel:${rawHelpdeskPhone.replace(/[^\d+]/g, '')}`}
                  className="px-contact-channel-link"
                  style={{ marginTop: 8 }}
                >
                  <Phone size={13} strokeWidth={2} />
                  <span>{rawHelpdeskPhone}</span>
                  <ArrowUpRight size={14} strokeWidth={2} />
                </a>
              ) : null}
            </article>

            <article className="px-contact-channel-col">
              <div className="px-contact-channel-top">
                <span className="px-about-acid-tag">02 / CAMPUS DESK</span>
                <Building2 size={18} strokeWidth={1.8} className="px-contact-channel-icon" />
              </div>
              <h3>Host campus</h3>
              <p>
                {placeLabel(edition?.host, edition?.city) || 'NSS College of Engineering, Palakkad'}.
                Registration desk at the main auditorium.
              </p>
              <Link
                to="/venue"
                className="px-contact-channel-link"
                data-mascot-target="contact-venue"
                data-mascot-label="Campus location"
                data-mascot-hover="Campus location & directions, I know the shortcuts."
              >
                <span>Campus Location &amp; Directions</span>
                <ArrowRight size={14} strokeWidth={2} />
              </Link>
            </article>

            <article className="px-contact-channel-col">
              <div className="px-contact-channel-top">
                <span className="px-about-acid-tag">03 / SELF-SERVICE</span>
                <ShieldCheck size={18} strokeWidth={1.8} className="px-contact-channel-icon" />
              </div>
              <h3>Student portal</h3>
              <p>View your reserved sessions, team roster, digital QR pass, and verification state.</p>
              <Link
                to="/portal"
                className="px-contact-channel-link"
                data-mascot-target="contact-portal"
                data-mascot-label="Open Student Portal"
                data-mascot-hover="Student portal, that one is all yours, not mine."
              >
                <span>Open Student Portal</span>
                <ArrowRight size={14} strokeWidth={2} />
              </Link>
            </article>
          </div>
        </div>
      </section>

      {/* Band 2: Contact Mascot visual split + Direct Dispatch Form */}
      <section
        className="px-contact-dispatch-band"
        aria-label="Send a message"
        onPointerEnter={() => mascotSay('Leave a message, I will make sure it lands.')}
      >
        <div className="px-about-container px-contact-dispatch-grid">
          <div className="px-contact-desk-aside">
            <div className="px-contact-mascot-stage">
              <img
                src={CONTACT_MASCOT_ART}
                alt="Parallax 2027 support desk mascot"
                loading="lazy"
              />
            </div>
          </div>

          <div className="px-contact-form-panel">
            <div className="px-contact-form-head">
              <span className="px-about-acid-tag">DIRECT DISPATCH</span>
              <h2>Send a message</h2>
              <p>
                Pick a category and write below. Your message routes directly to the organising
                desk.
              </p>
            </div>

            <form className="px-contact-form" onSubmit={handleSubmit}>
              <div className="contact-topic-selector">
                <span className="px-contact-field-label">Select Inquiry Category</span>
                <div
                  className="contact-topic-chips"
                  data-mascot-target="contact-topics"
                  data-mascot-label="inquiry category selector"
                >
                  {topics.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      className={`px-contact-chip${topic === t.id ? ' is-active' : ''}`}
                      onClick={() => setTopic(t.id)}
                      onPointerEnter={() => mascotSay(`${t.label}? On it.`)}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="contact-form-grid">
                <div className="contact-form-group">
                  <label className="px-contact-field-label" htmlFor="contact-name">
                    Your Full Name
                  </label>
                  <input
                    id="contact-name"
                    type="text"
                    className="px-contact-input"
                    placeholder="e.g. Warner Stark"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onBlur={() => {
                      if (name.trim()) mascotSay(`Ohh, your name's ${name.trim()}? Wow.`, 5200, 'wave');
                    }}
                    required
                    data-mascot-target="contact-name"
                    data-mascot-label="your full name"
                    data-mascot-hover="Your name goes here, I will read it out."
                  />
                </div>

                <div className="contact-form-group">
                  <label className="px-contact-field-label" htmlFor="contact-email">
                    Your Email Address
                  </label>
                  <input
                    id="contact-email"
                    type="email"
                    className="px-contact-input"
                    placeholder="e.g. warner@college.ac.in"
                    value={senderEmail}
                    onChange={(e) => setSenderEmail(e.target.value)}
                    onBlur={() => {
                      if (senderEmail.trim()) mascotSay("Ohh, surely didn't see that one coming…");
                    }}
                    required
                  />
                </div>
              </div>

              <div className="contact-form-group">
                <label className="px-contact-field-label" htmlFor="contact-message">
                  Your Message or Question
                </label>
                <textarea
                  id="contact-message"
                  className="px-contact-textarea"
                  rows={5}
                  placeholder="Describe your question, event name, or registration token..."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  required
                  data-mascot-target="contact-message"
                  data-mascot-label="your message"
                  data-mascot-hover="Spill it, the whole question, I am listening."
                />
              </div>

              <div className="px-contact-form-footer">
                <button
                  type="submit"
                  className="px-about-pill-btn"
                  disabled={busy}
                  data-mascot-target="contact-submit"
                  data-mascot-label="send message"
                  data-mascot-hover="Send it and I will do my little wave."
                >
                  {busy ? (
                    <>
                      <RefreshCw size={15} className="is-spinning" />
                      <span>Transmitting...</span>
                    </>
                  ) : (
                    <>
                      <span>Send message</span>
                      <Send size={15} strokeWidth={2} />
                    </>
                  )}
                </button>
              </div>

              {feedback && (
                <div className="px-contact-sent-notice">
                  <Check size={16} strokeWidth={2.4} />
                  <span>{feedback.text}</span>
                </div>
              )}
            </form>
          </div>
        </div>
      </section>

      {/* Band 3: Hairline FAQ handoff */}
      <section className="px-contact-faq-band" aria-label="Frequently asked questions">
        <div className="px-about-container">
          <div className="px-contact-faq-strip">
            <div className="px-contact-faq-copy">
              <HelpCircle size={20} strokeWidth={1.8} className="px-contact-channel-icon" />
              <div>
                <h3>Most answers are already written</h3>
                <p>Pass validity, campus lunch, team size rules, and cancellations.</p>
              </div>
            </div>
            <Link
              to="/faq"
              className="px-about-inline-link"
              data-mascot-target="contact-faq"
              data-mascot-label="Read FAQ"
              data-mascot-hover="Read the FAQ, the answer is probably in there."
            >
              <span>Read FAQ</span>
              <ArrowRight size={14} strokeWidth={2} />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

export function Footer() {
  const { edition } = useSite();
  const [openSection, setOpenSection] = useState('learn');
  const email = edition?.contactEmail || 'iste@nssce.ac.in';
  const hostShort = (edition?.host || 'NSS College of Engineering').split(',')[0];
  const cityLabel = edition?.city || 'Palakkad, Kerala';
  const year = new Date().getFullYear();

  return (
    <footer className="footer px-footer">
      <div className="px-footer-inner">
        <div className="px-footer-grid">
          <div className="px-footer-brand-col">
            <div className="px-footer-lockup">
              <Link
                to="/"
                className="px-footer-mark"
                aria-label={`${edition?.name || 'Parallax 2027'} home`}
              >
                <img
                  src={PARALLAX_MARK}
                  alt={edition?.name || 'Parallax'}
                  className="px-footer-mark-img"
                />
              </Link>

              <div className="px-footer-edition-meta">
                <div className="px-footer-slash-row">
                  <span className="px-footer-slash-label">DATES</span>
                  <span className="px-footer-slash" aria-hidden="true">/</span>
                  <div className="px-footer-slash-val">
                    <b>{dateRange(edition?.startsAt, edition?.endsAt)}</b>
                    <span>TWO DAYS, ONE CAMPUS</span>
                  </div>
                </div>
                <div className="px-footer-slash-row">
                  <span className="px-footer-slash-label">VENUE</span>
                  <span className="px-footer-slash" aria-hidden="true">/</span>
                  <div className="px-footer-slash-val">
                    <b>{hostShort.toUpperCase()}</b>
                    <span>{cityLabel.toUpperCase()}</span>
                  </div>
                </div>
              </div>
            </div>

            <Link
              to="/pass"
              className="px-footer-cta-pill"
              data-mascot-target="footer-pass"
              data-mascot-label="Get your pass"
              data-mascot-hover="Last stop before the footer, grab your pass!"
            >
              <span>GET YOUR PASS</span>
              <span className="px-footer-cta-circle" aria-hidden="true">
                <ArrowRight size={13} strokeWidth={2.4} />
              </span>
            </Link>

            <div className="px-footer-hours">
              <span className="px-footer-hashtag">#PARALLAX2027</span>
              <strong>{edition?.organizer || 'ISTE Student Chapter'}</strong>
              <p>{placeLabel(edition?.host, edition?.city) || 'NSS College of Engineering, Palakkad, Kerala'}</p>
            </div>
          </div>

          <div className="px-footer-col">
            <h3 className="px-footer-col-title">Get Involved</h3>
            <ul className="px-footer-link-list">
              <li><Link to="/pass">Get Your Pass</Link></li>
              <li><Link to="/events">Explore Events</Link></li>
              <li><Link to="/schedule">View Schedule</Link></li>
              <li><Link to="/portal">Participant Portal</Link></li>
              <li><Link to="/venue">Campus &amp; Directions</Link></li>
            </ul>
          </div>

          <div className="px-footer-col">
            <div className="px-footer-accordion">
              <button
                type="button"
                className={`px-footer-acc-btn${openSection === 'learn' ? ' is-open' : ''}`}
                aria-expanded={openSection === 'learn'}
                onClick={() => setOpenSection((prev) => (prev === 'learn' ? '' : 'learn'))}
                data-mascot-target="footer-learn"
                data-mascot-label="Learn"
                data-mascot-hover="Learn, about, team, and the rulebook."
              >
                <span>Learn</span>
                <ChevronDown size={15} strokeWidth={2} />
              </button>
              {openSection === 'learn' && (
                <ul className="px-footer-link-list">
                  <li><Link to="/about">About Parallax</Link></li>
                  <li><Link to="/team">Meet the Team</Link></li>
                  <li><Link to="/faq">FAQ &amp; Rules</Link></li>
                </ul>
              )}
            </div>

            <div className="px-footer-accordion">
              <button
                type="button"
                className={`px-footer-acc-btn${openSection === 'universe' ? ' is-open' : ''}`}
                aria-expanded={openSection === 'universe'}
                onClick={() => setOpenSection((prev) => (prev === 'universe' ? '' : 'universe'))}
                data-mascot-target="footer-universe"
                data-mascot-label="Parallax Universe"
                data-mascot-hover="Parallax Universe, everything that is not a rule."
              >
                <span>Parallax Universe</span>
                <ChevronDown size={15} strokeWidth={2} />
              </button>
              {openSection === 'universe' && (
                <ul className="px-footer-link-list">
                  <li><Link to="/events">All Competitions &amp; Labs</Link></li>
                  <li><Link to="/portal">Student Registration</Link></li>
                  <li><Link to="/contact">Organiser Desk</Link></li>
                </ul>
              )}
            </div>
          </div>

          <div className="px-footer-col">
            <h3 className="px-footer-col-title">Let&apos;s Talk</h3>
            <div className="px-footer-contact-list">
              <div>
                <span>General Inquiry</span>
                <a href={`mailto:${email}`}>{email}</a>
              </div>
              <div>
                <span>Pass &amp; Registration</span>
                <Link to="/contact">Message the Organising Desk</Link>
              </div>
              <div>
                <span>Host Institution</span>
                <Link to="/venue">{hostShort}, {cityLabel}</Link>
              </div>
              <div>
                <span>Convention Support</span>
                <Link to="/faq">Rules, Refunds &amp; Check-in</Link>
              </div>
            </div>
          </div>
        </div>

        <div className="px-footer-bottom">
          <div className="px-footer-hosted">
            <span>Hosted by</span>
            <img src={ISTE} alt={edition?.organizer || 'ISTE'} className="px-footer-host-logo" />
            <img src={NSSCE} alt="NSSCE emblem" className="px-footer-host-logo" />
            <strong>{edition?.organizer || 'ISTE'} • {hostShort}</strong>
          </div>

          <div className="px-footer-legal">
            <Link to="/faq">Rules &amp; Policy</Link>
            <Link to="/contact">Support</Link>
            <span className="px-footer-credits">
              Built by{' '}
              <a href="https://midhunkm.pages.dev/" target="_blank" rel="noopener noreferrer">
                Midhun K M
              </a>
              {' with '}
              <a href="https://arjc.github.io/" target="_blank" rel="noopener noreferrer">
                Arjun M L
              </a>
              <span className="px-footer-credit-tail">
                {' & '}
                <Link to="/team">Kaladharan Lal</Link>
              </span>
            </span>
            <span>&copy; Copyright {year} Parallax</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

export { ISTE, LOGO, NSSCE, GLOBE, PARALLAX_MARK };
