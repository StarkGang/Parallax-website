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
  Cpu,
  HelpCircle,
  Layers,
  Mail,
  MapPin,
  Navigation,
  PenTool,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Users,
  Zap,
} from 'lucide-react';
import { authApi, publicApi } from '../lib/api.js';
import { gsap, ScrollTrigger, useCardTilt } from '../lib/motion.js';

import { useSite } from '../lib/site.jsx';
import { useAuth } from '../lib/auth.jsx';
import { date, dateRange, dayLabel, money, time, weekday } from '../lib/format.js';
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
import HolographicTicket from '../components/HolographicTicket.jsx';
import HudFrame from '../components/HudFrame.jsx';
import ScheduleBoard from './ScheduleBoard.jsx';
import './EventCard.css';
import './HomePreview.css';
import './TeamFrame.css';
import HeroOdyssey from '../components/HeroOdyssey.jsx';
import PageScene from '../components/PageScene.jsx';
import { MascotEasterEggBubble, useMascotEasterEgg } from '../components/MascotEasterEgg.jsx';

const LOGO = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp`;
const GLOBE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/modified assets/globe.svg`;
const NSSCE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/NSSCE-Palakkad-Logo.webp`;
const ISTE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/Iste_logo.png`;

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
const SCHEDULE_ART = `${import.meta.env.BASE_URL}images/schedule_img.webp`;
const EVENTS_ART = `${import.meta.env.BASE_URL}images/event.webp`;
const ABOUT_ART = `${import.meta.env.BASE_URL}images/about.webp`;

// Homepage scene: the animated rooftop backdrop and the character that stands
// at the base of the three framed cards.
const SCENE_BG = `${import.meta.env.BASE_URL}images/bg.gif`;
const SCENE_MASCOT = `${import.meta.env.BASE_URL}images/mascot.gif`;

// Inner page scenes: the events catalogue uses the arena with the event
// character, the remaining pages share the valley backdrop and mascot.
const ARENA_ART = `${import.meta.env.BASE_URL}images/arena.png`;
const EVENT_SCENE_ART = `${import.meta.env.BASE_URL}images/event.png`;
const BACKGROUND_ART = `${import.meta.env.BASE_URL}images/background.png`;
const MASCOT_ART = `${import.meta.env.BASE_URL}images/mascot.png`;

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
const DAY_KEY_FMT = new Intl.DateTimeFormat('en-CA', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  timeZone: IST_ZONE,
});

const DAY_LABEL_FMT = new Intl.DateTimeFormat('en-GB', {
  weekday: 'long',
  day: '2-digit',
  month: 'long',
  timeZone: IST_ZONE,
});

const dayKeyOf = (iso) => {
  if (!iso) return 'tba';
  try {
    return DAY_KEY_FMT.format(new Date(iso));
  } catch {
    return 'tba';
  }
};

const dayLabelOf = (iso) => {
  if (!iso) return 'Date to be announced';
  try {
    return DAY_LABEL_FMT.format(new Date(iso)).toUpperCase();
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
  const feeLabel = event.addonPricePaise == null
    ? 'Registration details open soon'
    : event.addonPricePaise > 0
      ? `Add-on ${money(event.addonPricePaise)}`
      : 'Included with pass';
  const mascotHover = `${title}: ${event.categoryName || 'competition'}, ${formatLabel.toLowerCase()}, ${feeLabel.toLowerCase()}.`;

  // The whole card opens its detail page; the Explore and Register links keep
  // their own targets. Modified clicks are left to the browser.
  const handleCardClick = (clickEvent) => {
    if (clickEvent.defaultPrevented) return;
    if (clickEvent.button !== 0) return;
    if (clickEvent.metaKey || clickEvent.ctrlKey || clickEvent.shiftKey || clickEvent.altKey) return;
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
                size={48}
              />
            </div>
          </div>
        )}
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
        <Link className="exc-action" to={detailPath} aria-label={`Explore ${title}`}>
          <span>Explore</span>
          <ArrowUpRight size={11} strokeWidth={2.2} aria-hidden="true" />
        </Link>
        {event.registrationOpen ? (
          <Link
            className="exc-action is-primary"
            to="/portal/select-events"
            aria-label={`Register for ${title}`}
          >
            <span>Register</span>
            <ArrowRight size={11} strokeWidth={2.4} aria-hidden="true" />
          </Link>
        ) : (
          <span className="exc-action is-disabled" aria-disabled="true">
            <span>Closed</span>
          </span>
        )}
      </div>

      <p className="exc-plaque">
        <b>{feeLabel}</b>
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
        {kicker ? <span className="px-card-kicker">{kicker}</span> : null}
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
      const img = new Image();
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
    let idleCallback = null;
    const loadNextBatch = () => {
      if (!active || nextBatchStart >= TOTAL_HERO_FRAMES) return;
      const end = Math.min(nextBatchStart + 12, TOTAL_HERO_FRAMES);
      for (let i = nextBatchStart; i < end; i++) {
        loadFrame(i);
      }
      nextBatchStart = end;
      if (nextBatchStart >= TOTAL_HERO_FRAMES) return;
      if (typeof window.requestIdleCallback === 'function') {
        idleCallback = window.requestIdleCallback(loadNextBatch, { timeout: 200 });
      } else {
        // No idle API: finish the remainder in one pass rather than chaining
        // timers, so the effect owns a single cancellable allocation.
        loadNextBatch();
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
      if (idleCallback !== null && typeof window.cancelIdleCallback === 'function') {
        window.cancelIdleCallback(idleCallback);
      }
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
        <div className="lusion-hero-scroll-cue" ref={scrollPromptRef}>
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

function PassHighlightSection({ policy, registration, profile, user }) {
  const tiltRef = useCardTilt({ maxTilt: 2.5, scale: 1.01 });
  const lunchDays = policy?.lunchIncludedDays?.length || 2;
  const includedCount = policy?.includedEventCount || 3;
  const priceRupees = Math.round((policy?.passPricePaise || 35000) / 100);
  const valueCap = money(policy?.includedValueCapPaise || 45000);
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
    <section className="apple-pass-section pass-scene" ref={sceneRef}>
      <div className="pass-scene-bg" aria-hidden="true">
        <img src={PARALLAX_BG_VAULT} alt="" decoding="async" />
      </div>
      <div className="pass-scene-veil" aria-hidden="true" />
      <div className="pass-scene-floor" aria-hidden="true" />
      <div className="pass-scene-content">
        <div className="pass-scene-card">
          <HolographicTicket />
        </div>
        <RegistrationPricing policy={registration} profile={profile} user={user} />
      </div>
    </section>
  );
}

export function RegistrationPricing({ policy, profile, user }) {
  if (!policy?.prices) return null;
  const education = String(profile?.educationLevel || profile?.course || '').toLowerCase();
  const currentKey = user
    ? education === 'polytechnic'
      ? 'polytechnicPaise'
      : profile?.isteMember
        ? 'isteMemberPaise'
        : education === 'b.tech'
          ? 'nonIstePaise'
          : null
    : null;
  const rates = [
    {
      key: 'isteMemberPaise',
      label: 'ISTE Member',
      sub: 'Active membership ID verified at desk',
    },
    {
      key: 'nonIstePaise',
      label: 'Non-ISTE Student',
      sub: 'College & university undergraduates',
    },
    {
      key: 'polytechnicPaise',
      label: 'Polytechnic Student',
      sub: 'Diploma students (subsidized rate)',
    },
  ];

  return (
    <section className="px-pricing" aria-label="Registration pricing">
      <div className="px-pricing-head">
        <div className="px-pricing-tag">
          <span>REGISTRATION TIERS</span>
        </div>

        <h3>{policy.registrationOpen ? 'Choose your pass rate' : 'Registration opens soon'}</h3>

        {policy.registrationOpen ? (
          <p className="px-pricing-note">
            Rates auto-qualify based on your saved student profile credentials.
          </p>
        ) : (
          <div className="px-pricing-chip">
            <CalendarDays size={13} className="px-pricing-chip-icon" />
            <span>
              Opens {date(policy.registrationUnlockAt)} • {time(policy.registrationUnlockAt)} IST
            </span>
          </div>
        )}

        <div className="px-pricing-perks">
          <div className="px-perk-item">
            <Check size={12} strokeWidth={2.5} />
            <span>2 full convention days floor access</span>
          </div>
          <div className="px-perk-item">
            <Check size={12} strokeWidth={2.5} />
            <span>Up to 3 included events + lunch</span>
          </div>
        </div>
      </div>

      <div className="px-price-list">
        <div className="px-price-list-header">
          <span>Category</span>
          <span>All-Access Pass</span>
        </div>
        {rates.map(({ key, label, sub }) => {
          const isCurrent = key === currentKey;
          return (
            <div className={`px-price-row${isCurrent ? ' is-current' : ''}`} key={key}>
              <div className="px-price-row-info">
                <span className="px-price-label">
                  {label}
                  {isCurrent ? <b className="px-price-current">Your Rate</b> : null}
                </span>
                <span className="px-price-sub">{sub}</span>
              </div>
              <div className="px-price-amount">
                <strong>{money(policy.prices[key])}</strong>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function Home() {
  const { edition, policy, config } = useSite();
  const { user } = useAuth();
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
  const registration = useAsync(() => publicApi.registrationPolicy(), [], { enabled: true });
  const participantProfile = useAsync(() => authApi.profile(), [user?.id], { enabled: Boolean(user) });

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

  // Hooks are all called above this guard. Returning any earlier changed hook
  // order between renders ("Rendered fewer hooks than expected").
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
      <section className="px-preview" id="discover" aria-labelledby="px-preview-title">
        <div className="px-stage-bg" aria-hidden="true">
          <img src={SCENE_BG} alt="" decoding="async" />
        </div>
        <div className="px-stage-veil" aria-hidden="true" />
        <img
          className="px-stage-mascot"
          src={SCENE_MASCOT}
          alt=""
          onClick={onMascotTap}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              onMascotTap();
            }
          }}
          role="button"
          tabIndex={0}
          aria-label="Mascot easter egg"
          draggable="false"
          decoding="async"
        />
        <MascotEasterEggBubble message={eggMessage} />

        <div className="px-stage-inner">
          <header className="px-preview-head">
            <span className="px-preview-kicker">{edition?.name || 'Parallax'}</span>
            <h2 id="px-preview-title">
              Pick your <em>path.</em>
            </h2>
          </header>

          <div className="px-grid">
            <PreviewCard
              mascotTarget="home-edition"
              mascotHover="Who runs Parallax, where it happens and what it covers."
              kicker="01 / The Edition"
              title="About Parallax"
              copy={`${edition.name} is the ${edition.organizer || 'ISTE'} convention hosted at ${edition.host || 'NSSCE'}.`}
              cta="Read more"
              to="/about"
              image={ABOUT_ART}
            />
            <PreviewCard
              mascotTarget="home-schedule"
              mascotHover="Both days, every session, with times and rooms."
              kicker="02 / The Programme"
              title="Schedule"
              copy="Every session, round and room across both convention days."
              cta="See the schedule"
              to="/schedule"
              image={SCHEDULE_ART}
            />
            <PreviewCard
              mascotTarget="home-events"
              mascotHover="Hackathons, hardware builds, design sprints and paper sessions."
              kicker="03 / The Competitions"
              title="Events"
              copy="Hackathons, hardware builds, design sprints and paper sessions."
              meta={`${eventTotal ?? 0} events · ${categoryTotal ?? 0} categories`}
              cta="See all events"
              to="/events"
              image={EVENTS_ART}
            />
          </div>
        </div>
      </section>

      {/* Chapter 02: All-Access Pass Architecture with Layer Parallax */}
      <PassHighlightSection
        policy={policy}
        registration={registration.data?.data}
        profile={participantProfile.data?.data}
        user={user}
      />

      {announcements.length ? (
        <section className="section news-section">
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

export function About() {
  const { edition, policy } = useSite();
  return (
    <>
      <PageTitle
        kicker="About"
        title={
          <>
            About
            <br />
            <em>{edition?.name || 'Parallax 2026'}.</em>
          </>
        }
        desc={`${edition?.organizer || 'ISTE'} brings the convention to ${placeLabel(edition?.host, edition?.city) || 'NSS College of Engineering, Palakkad'}. Two days, one campus.`}
      />
      <section className="section prose-grid">
        <HudFrame as="article" className="about-main-card">
          <Eyebrow>The Idea</Eyebrow>
          <h2>Two days of student engineering.</h2>
          <p>
            {edition?.name || 'Parallax 2026'} is run by the {edition?.organizer || 'ISTE'} chapter
            at {placeLabel(edition?.host, edition?.city) || 'NSS College of Engineering'}. Individuals and teams
            build, compete and present across both days.
          </p>
          <p>
            Every event, time, room and fee on this site comes from the same catalogue the
            organisers edit.
          </p>
          <div className="about-facts">
            <div>
              <span>Organiser</span>
              <b>{edition?.organizer || 'ISTE'}</b>
            </div>
            <div>
              <span>Host</span>
              <b>{edition?.host || 'NSSCE'}</b>
            </div>
            <div>
              <span>Venue</span>
              <b>{edition?.venue || 'Campus'}</b>
            </div>
            <div>
              <span>Dates</span>
              <b>{dateRange(edition?.startsAt, edition?.endsAt)}</b>
            </div>
          </div>
        </HudFrame>
        <HudFrame as="article" className="host-card">
          <img src={NSSCE} alt={`${edition?.host || 'NSSCE'} emblem`} />
          <Eyebrow>Host Institution</Eyebrow>
          <h3>{edition?.host || 'NSS College of Engineering'}</h3>
          <p>{edition?.city || 'Palakkad, Kerala'}</p>
          <div className="host-rule" />
          <p>
            Pass: {money(policy?.passPricePaise)}, lunch included on{' '}
            {policy?.lunchIncludedDays?.length || 0} days.
          </p>
        </HudFrame>
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
        <section className="section directory exc-catalogue">
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
                >
                  <header className="exc-day-head">
                    <span className="exc-day-index">
                      Day {groupIndex + 1}
                    </span>
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

  const isTeam = event.format === 'team';
  const accent = getEventAccent(event);

  return (
    <>
      {/* Full-bleed banner — banner image if available, atmospheric fallback otherwise */}
      <div className="event-detail-hero">
        <div className="event-detail-hero-bg">
          {event.bannerUrl ? (
            <img src={event.bannerUrl} alt="" className="event-detail-hero-img" />
          ) : (
            <img
              src={PARALLAX_BG_VAULT}
              alt=""
              className="event-detail-hero-img event-detail-hero-fallback"
            />
          )}
          <div className="event-detail-hero-vignette" />
        </div>
        <div className="event-detail-hero-content">
          <div className="event-detail-hero-meta">
            <span className={`apple-cat-dot dot-${accent}`} />
            <span className="event-detail-hero-cat">{event.categoryName}</span>
            <span className="event-detail-hero-sep">·</span>
            <span className="event-detail-hero-format">
              {isTeam ? `Team · ${event.teamMinSize || 2}–${event.teamMaxSize || 4}` : 'Individual'}
            </span>
          </div>
          <h1 className="event-detail-hero-title">{event.title}</h1>
          {event.summary ? <p className="event-detail-hero-desc">{event.summary}</p> : null}
          <div className="event-detail-hero-badges">
            <Badge tone={event.registrationOpen ? 'good' : 'muted'}>
              {event.registrationOpen ? 'Registration open' : 'Registration closed'}
            </Badge>
            {event.isFeatured ? <Badge tone="accent">Featured</Badge> : null}
          </div>
        </div>
      </div>

      {/* Breadcrumb navigation */}
      <div className="event-detail-breadcrumb">
        <Link to="/events" className="event-detail-back">
          <ArrowRight size={13} style={{ transform: 'rotate(180deg)' }} strokeWidth={2} />
          <span>All events</span>
        </Link>
      </div>

      <section className="section detail-grid">
        <article className="detail-main">
          <Eyebrow>About this Event</Eyebrow>
          <h2>{event.title}</h2>
          {event.descriptionHtml ? (
            <div
              className="rich-text"
              dangerouslySetInnerHTML={{ __html: event.descriptionHtml }}
            />
          ) : (
            <p>{event.summary}</p>
          )}
          {event.rulesHtml ? (
            <>
              <h3>Requirements &amp; rules</h3>
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
        <aside className="detail-card" data-mascot-protect>
          <span className="detail-card-label">EVENT DETAILS</span>
          <div className="detail-row">
            <span>Format</span>
            <b style={{ textTransform: 'capitalize' }}>{event.format}</b>
          </div>
          {isTeam ? (
            <div className="detail-row">
              <span>Team size</span>
              <b>
                {event.teamMinSize}–{event.teamMaxSize} members
              </b>
            </div>
          ) : null}
          {event.baseValuePaise != null ? <div className="detail-row">
            <span>Included value</span>
            <b>{money(event.baseValuePaise)}</b>
          </div> : null}
          {event.addonPricePaise != null ? <div className="detail-row">
            <span>Add-on fee</span>
            <b>{money(event.addonPricePaise)}</b>
          </div> : null}
          <div className="detail-row">
            <span>Capacity</span>
            <b>
              {event.capacity || 'Unlimited'}
              {event.seatsLeft != null ? ` · ${event.seatsLeft} left` : ''}
            </b>
          </div>
          <div className="detail-row">
            <span>Schedule</span>
            <b>
              {event.startsAt
                ? `${date(event.startsAt)} · ${time(event.startsAt)}${event.endsAt ? ` – ${time(event.endsAt)}` : ''}`
                : 'TBA'}
            </b>
          </div>
          <div className="detail-row">
            <span>Venue</span>
            <b>{event.venueRoom || 'To be announced'}</b>
          </div>
          {event.teamFeeBasis || event.addonChargeBasis ? (
            <div className="detail-row">
              <span>Fee basis</span>
              <b>{event.teamFeeBasis || event.addonChargeBasis}</b>
            </div>
          ) : null}
          <p className="detail-card-note">
            Every participant needs an active convention pass. Add-on fees are charged separately.
          </p>
          <div data-mascot-target="event-register" data-mascot-label="the registration entry point">
            <Button to="/portal/select-events" icon={ArrowRight} className="full">
              Plan this in your portal
            </Button>
          </div>
          <Link to="/events" className="event-backlink">
            Back to all events
          </Link>
        </aside>
      </section>
    </>
  );
}

export function PassPage() {
  const { edition, policy } = useSite();
  const { user } = useAuth();
  const registration = useAsync(() => publicApi.registrationPolicy(), [], { enabled: true });
  const participantProfile = useAsync(() => authApi.profile(), [user?.id], { enabled: Boolean(user) });
  const mode = policy?.includedSelectionMode === 'exact' ? 'Exactly' : 'Up to';
  const lunchDays = policy?.lunchIncludedDays?.length || 2;
  const includedCount = policy?.includedEventCount || 3;
  const priceRupees = policy?.passPricePaise == null ? null : Math.round(policy.passPricePaise / 100);
  const valueCap = money(policy?.includedValueCapPaise || 45000);

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

      <RegistrationPricing
        policy={registration.data?.data}
        profile={participantProfile.data?.data}
        user={user}
      />

      <section className="section apple-pass-page-section">
        <div className="apple-pass-page-grid">
          <HudFrame as="article" className="apple-pass-pricing-box apple-pass-page-card">
            <span className="apple-price-caption">All-access pass</span>
            <div className={`apple-price-amount${priceRupees == null ? ' is-locked' : ''}`}>
              {priceRupees == null ? (
                <span className="apple-price-reveal">
                  <span className="apple-price-reveal-label">Registration starts on</span>
                  <span className="apple-price-reveal-date">
                    {registration.data?.data?.registrationUnlockAt
                      ? date(registration.data.data.registrationUnlockAt)
                      : 'when registration opens'}
                  </span>
                </span>
              ) : (
                <>
                  <span className="apple-price-currency">₹</span>
                  <span className="apple-price-number">{priceRupees}</span>
                  <span className="apple-price-tenure">/ pass</span>
                </>
              )}
            </div>
            <p className="apple-price-note">{edition?.name || 'Parallax 2026'} Convention Pass</p>

            <div className="apple-pass-benefits" style={{ margin: '24px 0 28px', width: '100%' }}>
              <div className="apple-benefit-row">
                <span className="apple-check-icon">
                  <Check size={13} strokeWidth={2.4} />
                </span>
                <span>
                  <b>Lunch included</b> on both convention days ({lunchDays} days)
                </span>
              </div>
              <div className="apple-benefit-row">
                <span className="apple-check-icon">
                  <Check size={13} strokeWidth={2.4} />
                </span>
                <span>
                  <b>
                    {mode} {includedCount} included events
                  </b>{' '}
                  within {valueCap} base cap
                </span>
              </div>
              <div className="apple-benefit-row">
                <span className="apple-check-icon">
                  <Check size={13} strokeWidth={2.4} />
                </span>
                <span>
                  <b>Full floor access</b> with verified digital convention ticket
                </span>
              </div>
            </div>

            <Link to="/portal/pass" className="apple-pass-btn">
              <span>Get your pass</span>
              <span className="apple-btn-arrow">
                <ArrowRight size={14} strokeWidth={2.4} />
              </span>
            </Link>

            <small className="apple-instant-tag" style={{ marginTop: '16px' }}>
              {policy?.gstNote || 'Fees in Indian rupees.'} Paid securely in the portal.
            </small>
          </HudFrame>

          <HudFrame as="article" className="apple-pass-copy-card">
            <span className="apple-pass-kicker">How it works</span>
            <h2>
              Pass first.
              <br />
              <em>Then pick your programme.</em>
            </h2>

            <ol className="apple-pass-steps">
              <li>
                <b>01 / Every participant gets one pass</b>
                <p>
                  It includes lunch on both days and is required before reserving any event in the
                  catalogue.
                </p>
              </li>
              <li>
                <b>
                  02 / Choose {mode.toLowerCase()} {includedCount} eligible events
                </b>
                <p>
                  The sum of their published base values stays within the {valueCap} allowance. The
                  pass fee is never deducted from that sum.
                </p>
              </li>
              <li>
                <b>03 / Add extra events separately</b>
                <p>
                  Additional challenge registrations use each event’s published add-on fee and can
                  be reserved after your pass.
                </p>
              </li>
              <li>
                <b>04 / Team members each hold a pass</b>
                <p>
                  {policy?.teamMembersRequirePass
                    ? 'Every team member must hold an active pass before the team entry is confirmed.'
                    : 'Team entry is available without a separate pass per member in this edition.'}
                </p>
              </li>
            </ol>

            <div className="apple-cap-well">
              <span className="apple-cap-title">Included event value</span>
              <b className="apple-cap-amount">
                {valueCap} <small>live edition policy</small>
              </b>
              <p>
                Selection locks on {date(policy?.selectionChangeDeadline)}. Unpaid add-on
                reservations expire after {policy?.holdMinutes || 15} minutes.
              </p>
            </div>
          </HudFrame>
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
      <section className="section apple-schedule-section">
        {schedule.loading ? <Loading label="Loading schedule" rows={3} /> : null}
        {schedule.error ? <ErrorBox error={schedule.error} onRetry={schedule.reload} /> : null}
        {!schedule.loading && !schedule.error && !days.length ? (
          <Empty
            title="The schedule is not published"
            desc="Sessions will appear here once released."
          />
        ) : null}
        <ScheduleBoard days={days} />
      </section>
    </div>
  );
}

export function VenuePage() {
  const { edition } = useSite();
  if (!edition) return <Loading label="Loading venue details" rows={2} />;
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
      <section className="section venue-grid venue-page-section">
        <SectionHead kicker="Getting there" title="One campus, two days" />
        <HudFrame as="article" className="venue-map-card">
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
              sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
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
        </HudFrame>
        <HudFrame as="article" className="venue-copy">
          <Eyebrow>Host Campus</Eyebrow>
          <h2>{edition?.host || 'NSS College of Engineering'}</h2>
          <p>{edition?.city || 'Palakkad, Kerala'}</p>
          <p>
            Sessions run across {edition?.venue || 'campus halls'}. Room numbers and lab assignments
            are published with each session in the live schedule; registration check-in opens at the
            campus main auditorium on both days.
          </p>
          <div className="detail-row">
            <span>Dates</span>
            <b>{dateRange(edition?.startsAt, edition?.endsAt)}</b>
          </div>
          <div className="detail-row">
            <span>Venue</span>
            <b>{edition?.venue || 'Campus'}</b>
          </div>
          <div className="detail-row">
            <span>City</span>
            <b>{edition?.city || 'Palakkad'}</b>
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
        </HudFrame>
      </section>
    </div>
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
      `Lunch on ${(policy?.lunchIncludedDays || []).map(dayLabel).join(' and ') || 'both convention days'}, full floor access, and an included event allowance.`,
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
        : 'Yes. Add-on events can be reserved separately.',
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
    ['Where do I get help?', `Write to ${edition?.contactEmail || 'the organisers'}.`],
  ];

  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
      <PageTitle
        kicker="FAQ"
        title={
          <>
            Common{' '}
            <br />
            <em>questions.</em>
          </>
        }
        desc="Passes, events, verification and refunds."
      />
      </PageScene>
      <section className="section apple-faq-section">
        <div className="apple-faq-list">
          {rows.map(([question, answer]) => (
            <details className="apple-faq-card" key={question}>
              <summary className="apple-faq-summary">
                <span className="apple-faq-question">{question}</span>
                <span className="apple-faq-chevron" aria-hidden="true">
                  <ChevronDown size={18} strokeWidth={2} />
                </span>
              </summary>
              <div className="apple-faq-answer">
                <p>{answer}</p>
              </div>
            </details>
          ))}
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
        image: 'chairperson.jpg',
      },
      {
        name: 'Dr. Praseeda K I',
        role: 'Faculty Secretary',
        image: 'secretary.jpg',
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
        image: 'Sreenath K_.png',
      },
    ],
  },
];

const TEAM_HOVER_LINES = {
  'Midhun K M':
    'That one is Midhun K M. He built me, front to back. His other work is at midhunkm.pages.dev.',
  'Arjun M L': 'Arjun M L did the frontend. Personal site: arjc.github.io.',
};

function teamSlug(name = '') {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

function TeamMemberCard({ member }) {
  const [imgError, setImgError] = useState(false);
  const imageUrl = `${import.meta.env.BASE_URL}images/team/${member.image}`;
  const initials = member.name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('');
  const mascotProps = {
    'data-mascot-target': `team-${teamSlug(member.name)}`,
    'data-mascot-label': member.name,
    'data-mascot-hover':
      TEAM_HOVER_LINES[member.name] || `${member.name}, ${member.role} on this year's crew.`,
  };

  if (member.featured) {
    const CardTag = member.link ? 'a' : 'article';
    const cardProps = member.link
      ? {
          href: member.link,
          target: '_blank',
          rel: 'noopener noreferrer',
          title: `${member.name} — personal site`,
        }
      : {};

    return (
      <CardTag
        className={`team-member-card is-featured${member.link ? ' is-linked' : ''}`}
        {...cardProps}
        {...mascotProps}
      >
        <div className="tm-frame">
          <div className="tm-frame-media" data-initials={initials}>
            {!imgError && (
              <img
                src={imageUrl}
                alt={member.name}
                loading="eager"
                decoding="async"
                onError={() => setImgError(true)}
              />
            )}
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
      <div className="team-member-image" data-initials={initials}>
        {!imgError && (
          <img
            src={imageUrl}
            alt={member.name}
            loading="eager"
            decoding="async"
            onError={() => setImgError(true)}
          />
        )}
      </div>

      <div className="team-member-info">
        <h3>{member.name}</h3>
        <span>{member.role}</span>
      </div>
    </article>
  );
}

export function TeamPage() {
  useEffect(() => {
    // Preload all team member images eagerly so they display instantly without lag
    TEAM_GROUPS.forEach((group) => {
      group.members.forEach((member) => {
        if (member.image) {
          const img = new Image();
          img.src = `${import.meta.env.BASE_URL}images/team/${member.image}`;
        }
      });
    });
  }, []);

  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
      <PageTitle
        kicker="Team"
        title={
          <>
            Who runs{' '}
            <br />
            <em>Parallax.</em>
          </>
        }
        desc="Faculty, student leads and the web team."
      />
      </PageScene>

      <section className="team-page">
        {TEAM_GROUPS.map((group) => (
          <section className="team-group" key={group.title}>
            <div className="team-group-heading">
              <div>
                <h2>{group.title}</h2>
                <p>{group.description}</p>
              </div>
            </div>

            <div className={`team-grid${group.title === 'Web-Dev Team' ? ' is-webdev' : ''}`}>
              {group.members.map((member) => (
                <TeamMemberCard key={member.name} member={member} />
              ))}
            </div>
          </section>
        ))}
      </section>
    </div>
  );
}

export function ContactPage() {
  const { edition } = useSite();
  const email = edition?.contactEmail || 'iste@nssce.ac.in';
  const [topic, setTopic] = useState('general');
  const [name, setName] = useState('');
  const [senderEmail, setSenderEmail] = useState('');
  const [message, setMessage] = useState('');
  const [sent, setSent] = useState(false);

  const topics = [
    { id: 'pass', label: 'Pass & Pricing' },
    { id: 'events', label: 'Event Rules & Registration' },
    { id: 'teams', label: 'Team Coordination' },
    { id: 'travel', label: 'Travel & Accommodation' },
    { id: 'general', label: 'General Inquiries' },
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    const topicLabel = topics.find((t) => t.id === topic)?.label || 'General';
    const subject = encodeURIComponent(`[Parallax 2026] Inquiry: ${topicLabel}`);
    const body = encodeURIComponent(
      `Name: ${name || 'Participant'}\nEmail: ${senderEmail || 'Not provided'}\nCategory: ${topicLabel}\n\nMessage:\n${message}\n\n--\nSent via Parallax 2026 Portal`,
    );
    window.location.href = `mailto:${email}?subject=${subject}&body=${body}`;
    setSent(true);
  };

  return (
    <div className="page-scene-page">
      <PageScene bg={BACKGROUND_ART} mascot={MASCOT_ART}>
      <PageTitle
        kicker="Contact"
        title={
          <>
            Talk to{' '}
            <br />
            <em>the team.</em>
          </>
        }
        desc="Email us about passes, events or travel."
        aside={
          <div className="contact-status-card">
            <div className="contact-status-indicator">
              <span className="contact-status-pulse" />
              <span>Desk online</span>
            </div>
            <span className="contact-status-hours">Typical response &lt; 4 hours</span>
          </div>
        }
      />
      </PageScene>

      <section className="section contact-section">
        {/* Touchpoint Cards Grid */}
        <div className="contact-cards-grid">
          {/* Card 1: Direct Convention Email */}
          <article className="contact-channel-card">
            <div className="contact-channel-icon-wrap">
              <Mail size={22} strokeWidth={1.8} />
            </div>
            <div className="contact-channel-body">
              <span className="contact-channel-tag">Email</span>
              <h3 className="contact-channel-title">Email the organisers</h3>
              <p className="contact-channel-desc">
                Passes, team entries, certificates and press.
              </p>
              <a href={`mailto:${email}`} className="contact-channel-link">
                <span>{email}</span>
                <ArrowUpRight size={14} strokeWidth={2} />
              </a>
            </div>
          </article>

          {/* Card 2: Campus & Host Venue */}
          <article className="contact-channel-card">
            <div className="contact-channel-icon-wrap">
              <Building2 size={22} strokeWidth={1.8} />
            </div>
            <div className="contact-channel-body">
              <span className="contact-channel-tag">Campus</span>
              <h3 className="contact-channel-title">Host campus</h3>
              <p className="contact-channel-desc">
                {placeLabel(edition?.host, edition?.city) || 'NSS College of Engineering'}.
                Desk at the main auditorium.
              </p>
              <Link to="/venue" className="contact-channel-link">
                <span>Campus Location &amp; Directions</span>
                <ArrowRight size={14} strokeWidth={2} />
              </Link>
            </div>
          </article>

          {/* Card 3: Participant Self-Service */}
          <article className="contact-channel-card">
            <div className="contact-channel-icon-wrap">
              <ShieldCheck size={22} strokeWidth={1.8} />
            </div>
            <div className="contact-channel-body">
              <span className="contact-channel-tag">Portal</span>
              <h3 className="contact-channel-title">Student portal</h3>
              <p className="contact-channel-desc">
                Your sessions, team, entry QR and verification status.
              </p>
              <Link to="/portal" className="contact-channel-link">
                <span>Open Student Portal</span>
                <ArrowRight size={14} strokeWidth={2} />
              </Link>
            </div>
          </article>
        </div>

        {/* Executive In-Page Direct Dispatch / Quick Contact Form */}
        <div className="contact-dispatch-wrap">
          <div className="contact-dispatch-header">
            <div className="contact-dispatch-head-left">
              <span className="contact-dispatch-kicker">Message</span>
              <h2 className="contact-dispatch-title">Send a message</h2>
              <p className="contact-dispatch-desc">
                Pick a category and write below. It goes to the organising inbox.
              </p>
            </div>
            <div className="contact-dispatch-head-right">
              <div className="contact-fast-stat">
                <b>09:00 – 18:00 IST</b>
                <span>Desk Active Hours</span>
              </div>
            </div>
          </div>

          <form className="contact-dispatch-form" onSubmit={handleSubmit}>
            <div className="contact-topic-selector">
              <span className="contact-field-label">Select Inquiry Category</span>
              <div
                className="contact-topic-chips"
                data-mascot-target="contact-topics"
                data-mascot-label="inquiry category selector"
              >
                {topics.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`contact-topic-chip ${topic === t.id ? 'is-active' : ''}`}
                    onClick={() => setTopic(t.id)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="contact-form-grid">
              <div className="contact-form-group">
                <label className="contact-field-label" htmlFor="contact-name">
                  Your Full Name
                </label>
                <input
                  id="contact-name"
                  type="text"
                  className="contact-input"
                  placeholder="e.g. Analogue Interface"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  data-mascot-target="contact-name"
                  data-mascot-label="your full name"
                />
              </div>

              <div className="contact-form-group">
                <label className="contact-field-label" htmlFor="contact-email">
                  Your Email Address
                </label>
                <input
                  id="contact-email"
                  type="email"
                  className="contact-input"
                  placeholder="e.g. warner@college.ac.in"
                  value={senderEmail}
                  onChange={(e) => setSenderEmail(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="contact-form-group">
              <label className="contact-field-label" htmlFor="contact-message">
                Your Message or Question
              </label>
              <textarea
                id="contact-message"
                className="contact-textarea"
                rows={5}
                placeholder="Describe your question, event name, or registration token..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                required
                data-mascot-target="contact-message"
                data-mascot-label="your message"
              />
            </div>

            <div className="contact-form-footer">
              <button type="submit" className="contact-submit-btn">
                <span>Send email</span>
                <Send size={15} strokeWidth={2} />
              </button>

              <span className="contact-dispatch-note">Direct route to {email}</span>
            </div>

            {sent && (
              <div className="contact-sent-notice">
                <Check size={16} strokeWidth={2.4} />
                <span>
                  Inquiry opened in your email client. If it did not open, please write directly to{' '}
                  <b>{email}</b>.
                </span>
              </div>
            )}
          </form>
        </div>

        {/* Quick FAQ Callout Banner */}
        <div className="contact-faq-banner">
          <div className="contact-faq-banner-content">
            <HelpCircle size={22} strokeWidth={1.8} className="contact-faq-icon" />
            <div>
              <h4>Most answers are already written</h4>
              <p>Pass validity, lunch, team size and cancellations.</p>
            </div>
          </div>
          <Link to="/faq" className="contact-faq-btn">
            <span>Read FAQ</span>
            <ArrowRight size={14} strokeWidth={2} />
          </Link>
        </div>
      </section>
    </div>
  );
}

export function Footer() {
  const { edition } = useSite();
  return (
    <footer className="footer">
      <div className="footer-top">
        <Link
          to="/"
          className="footer-brand"
          aria-label={`${edition?.name || 'Parallax 2026'} home`}
        >
          <img src={ISTE} alt={edition?.organizer || 'ISTE'} className="footer-logo footer-iste-logo" />
        </Link>
        <p>Organised by ISTE</p>
        <div className="footer-host">
          <img src={NSSCE} alt="NSSCE emblem" />
          <span>
            Hosted by {(edition?.host || 'NSS College of Engineering').split(',')[0]}
            <br />
            {edition?.city || 'Palakkad, Kerala'}
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
          ['Meet the Team', '/team'],
          ['Portal', '/portal'],
        ].map(([label, to]) => (
          <Link key={to} to={to}>
            {label}
          </Link>
        ))}
      </div>
      <div className="footer-bottom">
        <span className="footer-copy">
          © 2026 All rights reserved.
        </span>
        <span className="footer-credits">
          Developed by{' '}
          <a
            href="https://midhunkm.pages.dev/"
            target="_blank"
            rel="noopener noreferrer"
            className="footer-credit-link"
          >
            Midhun K M
          </a>
          {' with '}
          <a
            href="https://arjc.github.io/"
            target="_blank"
            rel="noopener noreferrer"
            className="footer-credit-link"
          >
            Arjun M L
          </a>
          {' & '}
          <Link to="/team" className="footer-credit-link">
            Kaladharan Lal
          </Link>
        </span>
      </div>
    </footer>
  );
}

export { ISTE, LOGO, NSSCE, GLOBE };
