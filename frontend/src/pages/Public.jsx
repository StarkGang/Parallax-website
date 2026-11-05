import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
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
  Mail,
  MapPin,
  Navigation,
  PenTool,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Ticket,
  Users,
  Zap,
} from "lucide-react";
import { publicApi } from "../lib/api.js";
import { useCardTilt, gsap, ScrollTrigger } from "../lib/motion.js";

import { useSite } from "../lib/site.jsx";
import {
  date,
  dateRange,
  dayLabel,
  money,
  time,
  weekday,
} from "../lib/format.js";
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
} from "../components/ui.jsx";
import HolographicTicket from "../components/HolographicTicket.jsx";
import "./EventCard.css";
import HeroOdyssey from "../components/HeroOdyssey.jsx";

const LOGO = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.png`;
const GLOBE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/modified assets/globe.svg`;
const NSSCE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/NSSCE-Palakkad-Logo.webp`;
const ISTE = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/ISTE LOGO NO  BG PNG.png`;

// High-fidelity architectural parallax depth backplates & vector assets
const PARALLAX_BG_VAULT = `${import.meta.env.BASE_URL}images/parallax-bg-vault.webp`;
const PARALLAX_BG_CORE = `${import.meta.env.BASE_URL}images/parallax-bg-core.webp`;
const PARALLAX_BG_PEDESTAL = `${import.meta.env.BASE_URL}images/parallax-bg-pedestal.webp`;
const PARALLAX_DEPTH_BG = `${import.meta.env.BASE_URL}images/parallax-depth-bg.webp`;
const PARALLAX_VECTOR = `${import.meta.env.BASE_URL}images/parallax-vector.svg`;
const PARALLAX_LOGO_ASSET = `${import.meta.env.BASE_URL}images/parallax-logo.png`;

function CategoryIcon({ category, size = 30 }) {
  const cat = (category || "").toLowerCase();
  if (
    cat.includes("comp") ||
    cat.includes("code") ||
    cat.includes("hack") ||
    cat.includes("data")
  ) {
    return <Code2 size={size} strokeWidth={1.5} />;
  }
  if (
    cat.includes("elect") ||
    cat.includes("circuit") ||
    cat.includes("solder")
  ) {
    return <Zap size={size} strokeWidth={1.5} />;
  }
  if (cat.includes("robot") || cat.includes("line") || cat.includes("maze")) {
    return <Bot size={size} strokeWidth={1.5} />;
  }
  if (cat.includes("desig") || cat.includes("cad")) {
    return <PenTool size={size} strokeWidth={1.5} />;
  }
  if (cat.includes("engin") || cat.includes("proj")) {
    return <Boxes size={size} strokeWidth={1.5} />;
  }
  return <Layers size={size} strokeWidth={1.5} />;
}

function EventIcon({ iconId, category, size = 22 }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);

  return (
    <>
      {(!loaded || failed || !iconId) && (
        <CategoryIcon category={category} size={size} />
      )}
      {iconId && !failed && (
        <img
          src={publicApi.iconUrl(iconId)}
          alt=""
          className="pro-event-icon-img"
          style={loaded ? undefined : { display: "none" }}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
      )}
    </>
  );
}

function getEventAccent(event) {
  if (event.accent && typeof event.accent === "string") {
    const raw = event.accent.toLowerCase().trim();
    if (raw) return raw;
  }
  const cat = (event.categorySlug || event.categoryName || "").toLowerCase();
  if (cat.includes("electr")) return "orange";
  if (cat.includes("engin")) return "amber";
  if (cat.includes("robot")) return "lime";
  if (cat.includes("design")) return "violet";
  if (cat.includes("comput") || cat.includes("code")) return "cyan";
  return "cyan";
}

export function EventCard({ event, index = 0 }) {
  const isTeam = event.format === "team";
  const formatLabel = isTeam
    ? `Team (${event.teamMinSize || 2}–${event.teamMaxSize || 4})`
    : "Individual";

  return (
    <div
      className="xcard-slot rise"
      style={{ animationDelay: `${index * 35}ms` }}
    >
      <Link to={`/events/${event.slug}`} className="xcard">
        <div className="xcard-media">
          {event.bannerUrl ? (
            <img
              src={event.bannerUrl}
              alt={event.title}
              className="xcard-img"
              loading="lazy"
              width={480}
              height={176}
            />
          ) : (
            <div className="xcard-fallback">
              <img src={PARALLAX_BG_CORE} alt="" className="xcard-fallback-bg" />
              <EventIcon
                iconId={event.iconId}
                category={event.categorySlug || event.categoryName}
                size={36}
              />
            </div>
          )}
        </div>

        <div className="xcard-body">
          <div className="xcard-status-row">
            <span className="xcard-updated">
              {event.dateLabel || (event.startsAt ? date(event.startsAt) : "TBA")}
            </span>
            <span className="xcard-sep">•</span>
            <span
              className={`xcard-status ${event.registrationOpen ? "is-open" : "is-closed"}`}
            >
              <span className="xcard-status-dot" />
              {event.registrationOpen ? "Open" : "Closed"}
            </span>
          </div>

          <h3 className="xcard-title">{event.title}</h3>

          <div className="xcard-reveal" aria-hidden="false">
            <div className="xcard-reveal-inner">
              <p className="xcard-desc">{event.summary}</p>
              <div className="xcard-tags">
                <span className="xcard-tag">
                  <span className={`apple-cat-dot dot-${getEventAccent(event)}`} />
                  {event.categoryName}
                </span>
                <span className="xcard-tag">{formatLabel}</span>
              </div>
            </div>
          </div>

          <div className="xcard-footer">
            <span className="xcard-venue">
              <MapPin size={12} strokeWidth={1.8} />
              {event.venueRoom || "Main Stage"}
            </span>
            <span className="xcard-price">
              {event.addonPricePaise > 0
                ? `Add-on ${money(event.addonPricePaise)}`
                : "Included with pass"}
            </span>
          </div>
        </div>
      </Link>
    </div>
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
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const img = imagesRef.current[frameIdx];
    if (!img || !img.complete || img.naturalWidth === 0) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;

    if (
      canvas.width !== Math.floor(w * dpr) ||
      canvas.height !== Math.floor(h * dpr)
    ) {
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

  // Preload image sequence for instantaneous 60fps scrub
  useEffect(() => {
    let active = true;
    const loadedImages = [];
    const baseUrl = import.meta.env.BASE_URL;

    let loadedCount = 0;
    for (let i = 1; i <= TOTAL_HERO_FRAMES; i++) {
      const img = new Image();
      const num = String(i).padStart(3, "0");
      img.src = `${baseUrl}anim/sequence/frame_${num}.webp`;
      img.onload = () => {
        loadedCount++;
        if (i === 1 && active) {
          renderFrame(0);
        }
        if (loadedCount >= Math.min(20, TOTAL_HERO_FRAMES) && active) {
          setFramesLoaded(true);
        }
      };
      loadedImages.push(img);
    }
    imagesRef.current = loadedImages;

    const onResize = () => {
      renderFrame(currentFrameRef.current);
    };
    window.addEventListener("resize", onResize);

    return () => {
      active = false;
      window.removeEventListener("resize", onResize);
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

      stage.style.setProperty("--mouse-x", `${(x + 0.5) * 100}%`);
      stage.style.setProperty("--mouse-y", `${(y + 0.5) * 100}%`);

      if (canvasRef.current) {
        gsap.to(canvasRef.current, {
          rotateY: x * 3,
          rotateX: -y * 3,
          scale: 1.01,
          transformPerspective: 1200,
          ease: "power1.out",
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
          ease: "power2.out",
          duration: 0.6,
        });
      }
    };

    stage.addEventListener("mousemove", onMouseMove);
    stage.addEventListener("mouseleave", onMouseLeave);

    return () => {
      stage.removeEventListener("mousemove", onMouseMove);
      stage.removeEventListener("mouseleave", onMouseLeave);
    };
  }, []);

  // GSAP ScrollTrigger Sequence Scrubbing with Hero Logo Fly-Through
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return undefined;

    const isReduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (isReduced) {
      renderFrame(TOTAL_HERO_FRAMES - 1);
      return undefined;
    }

    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: track,
        start: "top top",
        end: "bottom bottom",
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
            scrollPromptRef.current.style.opacity = progress > 0.05 ? "0" : "1";
            scrollPromptRef.current.style.pointerEvents =
              progress > 0.05 ? "none" : "auto";
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
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (isReduced) return undefined;

    const layers = document.querySelectorAll("[data-parallax-speed]");
    if (!layers.length) return undefined;

    const ctx = gsap.context(() => {
      layers.forEach((layer) => {
        const speed =
          parseFloat(layer.getAttribute("data-parallax-speed")) || 0.2;
        const parent = layer.closest("section") || layer.parentElement;
        gsap.fromTo(
          layer,
          { yPercent: -speed * 45, force3D: true },
          {
            yPercent: speed * 45,
            force3D: true,
            ease: "none",
            scrollTrigger: {
              trigger: parent,
              start: "top bottom",
              end: "bottom top",
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
  const tiltRef = useCardTilt({ maxTilt: 2.5, scale: 1.01 });
  const lunchDays = policy?.lunchIncludedDays?.length || 2;
  const includedCount = policy?.includedEventCount || 3;
  const priceRupees = Math.round((policy?.passPricePaise || 35000) / 100);
  const valueCap = money(policy?.includedValueCapPaise || 45000);

  return (
    <>
      <section className="apple-pass-section tf-parallax-section">
      <HolographicTicket />
      </section>
      
    </>
  );
}

export function Home() {
  const { edition, policy, config } = useSite();
  const heroStackRef = useRef(null);
  const odysseyRef = useRef(null);
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
  const news = useAsync(
    () => publicApi.announcements(slug, { pageSize: 2 }),
    [slug],
    {
      enabled: Boolean(slug),
    },
  );

  if (!edition) return null;
  const events =
    featured.data?.data && featured.data.data.length > 0
      ? featured.data.data
      : fallbackEvents.data?.data || [];
  const announcements = news.data?.data || [];
  const days = Math.max(
    1,
    Math.round(
      (new Date(edition.endsAt).setHours(23, 59) -
        new Date(edition.startsAt).setHours(0, 0)) /
        86_400_000,
    ),
  );

  // Initialize hardware-accelerated parallax layer scrub down the page
  useParallaxScroll();

  useEffect(() => {
    const stack = heroStackRef.current;
    const odyssey = odysseyRef.current;
    if (!stack || !odyssey) return undefined;

    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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
          ease: "none",
          scrollTrigger: {
            trigger: stack,
            start: "top top",
            end: "top+=1000vh top",
            scrub: true,
          },
        },
      );
    }, stack);

    return () => ctx.revert();
  }, []);

  return (
    <>
      <div className="home-hero-stack" ref={heroStackRef}>
        {/* The parallax sequence stays pinned beneath the opening panel. */}
        <HeroParallax edition={edition} days={days} />
        <div className="home-odyssey-panel" ref={odysseyRef}>
          <HeroOdyssey
            title={edition.name}
            subtitle="Lighting Up The Future"
            description={`One pass unlocks ${edition.name}. Explore the challenges, workshops, and ideas shaping the next perspective.`}
          />
        </div>
      </div>


      {/* The Programme & Featured Challenges Showcase with 2.5D Layer Parallax */}
      <section
        className="section lusion-programme-section tf-parallax-section"
        id="programme"
      >
        <style>{`
          @media (max-width: 767px) {
            #programme .lusion-section-head,
            #programme .lusion-head-left,
            #programme .lusion-section-title,
            #programme .lusion-section-desc {
              text-align: center;
            }
            #programme .lusion-head-actions {
              justify-content: center;
            }
          }
        `}</style>


        {/* Layer 0: Continuous Cyber Corridor Environment */}
        <div
          className="tf-parallax-bg"
          data-parallax-speed="0.22"
          aria-hidden="true"
        >
          <img src={PARALLAX_DEPTH_BG} alt="" className="tf-bg-img" />
          <div className="tf-vignette-overlay" />
        </div>


        {/* Layer 1: Interactive Foreground Content */}
        <div className="tf-parallax-fg">
          <div className="lusion-section-head">
            <div className="lusion-head-left">
              <h1 className="lusion-section-title">
                Discover all programs
              </h1>
              <p className="lusion-section-desc">
                A single convention pass for {days} days.
              </p>
            </div>
            <div className="lusion-head-actions">
              <Link to="/events" className="lusion-btn lusion-btn-primary">
                <span>Explore All Challenges</span>
                <span className="lusion-btn-icon">
                  <ArrowRight size={15} strokeWidth={2.2} />
                </span>
              </Link>
              <Link to="/pass" className="lusion-btn lusion-btn-ghost">
                <span>All-Access Pass</span>
                <span className="lusion-btn-icon">
                  <ArrowUpRight size={15} strokeWidth={2.2} />
                </span>
              </Link>
            </div>
          </div>

          {(featured.loading && !events.length) ||
          (fallbackEvents.loading && !events.length) ? (
            <Loading label="Loading the programme" rows={2} />
          ) : featured.error && fallbackEvents.error ? (
            <ErrorBox error={featured.error} onRetry={featured.reload} />
          ) : events.length ? (
            <div className="lusion-event-grid">
              {events.map((event, index) => (
                <EventCard key={event.id} event={event} index={index} />
              ))}
              // midhun add a see all card with + thumbnail and data at the end
            </div>
          ) : (
            <Empty
              title="The programme is being published"
              desc="Featured events will appear here."
            />
          )}
        </div>
      </section>

      {/* Chapter 02: All-Access Pass Architecture with Layer Parallax */}
      <PassHighlightSection policy={policy} />

      {/* Chapter 03: Architectural Facts with Floor Grid Runway */}
      <section className="facts section tf-parallax-section">
        <div
          className="tf-parallax-bg"
          data-parallax-speed="0.28"
          aria-hidden="true"
        >
          <img src={PARALLAX_BG_PEDESTAL} alt="" className="tf-bg-img" />
          <div className="tf-vignette-overlay" />
        </div>
        <div className="fact tf-parallax-fg">
          <span>01 / FORMAT</span>
          <b>
            Individual
            <br />& team events
          </b>
        </div>
        <div className="fact tf-parallax-fg">
          <span>02 / DURATION</span>
          <b>
            {days} days
            <br />
            together
          </b>
        </div>
        <div className="fact tf-parallax-fg">
          <span>03 / WHEN</span>
          <b>
            {date(edition.startsAt)}
            <br />
            {date(edition.endsAt)}
          </b>
        </div>
        <div className="fact tf-parallax-fg">
          <span>04 / WHERE</span>
          <b>
            {edition.venue}
            <br />
            {edition.city}
          </b>
        </div>
      </section>


            <section className="cta section tf-parallax-section">
        <div
          className="tf-parallax-bg"
          data-parallax-speed="0.18"
          aria-hidden="true"
        >
          {/* <img src={PARALLAX_DEPTH_BG} alt="" className="tf-bg-img" /> */}
          <div className="tf-vignette-overlay" />
        </div>

        <div className="tf-parallax-fg">
          <div className="cta-emblem-center" aria-hidden="true">
            <img src={LOGO} alt="" className="cta-emblem-img" />
          </div>
          <Eyebrow>Your Next Perspective</Eyebrow>
          <h2>
            Make room for
            <br />
            <em>the new perspectives.</em>
          </h2>
          <p>
            One pass unlocks {edition?.name || "Parallax 2026"}. Check the
            timetable, review the challenges, and secure your badge.
          </p>
          <div className="cta-action-group">
            <Link to="/pass" className="lusion-btn lusion-btn-primary">
              <span>Get your pass</span>
              <span className="lusion-btn-icon">
                <ArrowRight size={15} strokeWidth={2.2} />
              </span>
            </Link>
            <Link to="/events" className="lusion-btn lusion-btn-ghost">
              <span>Explore events</span>
              <span className="lusion-btn-icon">
                <ArrowUpRight size={15} strokeWidth={2.2} />
              </span>
            </Link>
          </div>
        </div>
      </section>

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
        desc={`${edition?.name || "Parallax 2026"} is a ${edition?.organizer || "ISTE"} convention hosted at ${edition?.host || "NSSCE"}. The programme is published from a single live catalogue.`}
      />
      <section className="section prose-grid">
        <article className="about-main-card">
          <Eyebrow>The Idea</Eyebrow>
          <h2>Curiosity brings us together.</h2>
          <p>
            Named for the shift in perspective created by a change in viewpoint,{" "}
            {edition?.name || "Parallax 2026"} invites students to look at
            technology and engineering from many angles. The convention is
            planned by the {edition?.organizer || "ISTE"} and hosted at{" "}
            {edition?.host || "NSSCE"}, {edition?.city || "Palakkad"}.
          </p>
          <p>
            Every event in the catalogue is a real record in the convention
            database: title, category, format, schedule, capacity and fees all
            come from the same source the organisers edit.
          </p>
          <div className="about-facts">
            <div>
              <span>ORGANISER</span>
              <b>{edition?.organizer || "ISTE"}</b>
            </div>
            <div>
              <span>HOST</span>
              <b>{edition?.host || "NSSCE"}</b>
            </div>
            <div>
              <span>VENUE</span>
              <b>{edition?.venue || "Campus"}</b>
            </div>
            <div>
              <span>DATES</span>
              <b>{dateRange(edition?.startsAt, edition?.endsAt)}</b>
            </div>
          </div>
        </article>
        <article className="host-card">
          <img src={NSSCE} alt={`${edition?.host || "NSSCE"} emblem`} />
          <Eyebrow>Host Institution</Eyebrow>
          <h3>{edition?.host || "NSS College of Engineering"}</h3>
          <p>{edition?.city || "Palakkad, Kerala"}</p>
          <div className="host-rule" />
          <p>
            Convention pass: {money(policy?.passPricePaise)} per participant,
            including lunch on {policy?.lunchIncludedDays?.length || 0} days.
          </p>
        </article>
      </section>
    </>
  );
}

export function EventsPage() {
  const { edition, slug } = useSite();
  const [query, setQuery] = useState("");
  const debounced = useDebounced(query);
  const [category, setCategory] = useState("");
  const [format, setFormat] = useState("");
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
  const lastPage = Math.max(
    1,
    Math.ceil((meta.total || 0) / (meta.pageSize || 9)),
  );

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
          {meta.total} {meta.total === 1 ? "event" : "events"}
          <span>·</span>
          {edition?.registrationOpen
            ? "registration open"
            : "registration closed"}
          <span>·</span>
          page {meta.page} of {lastPage}
        </div>
        {list.loading ? (
          <Loading label="Loading the catalogue" rows={2} />
        ) : list.error ? (
          <ErrorBox error={list.error} onRetry={list.reload} />
        ) : events.length ? (
          <>
            <div className="event-grid lusion-event-grid">
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
                  onClick={() =>
                    setPage((value) => Math.min(lastPage, value + 1))
                  }
                  disabled={page >= lastPage}
                >
                  Next
                </Button>
              </div>
            ) : null}
          </>
        ) : (
          <Empty
            title="No matching events"
            desc="Try another search term or filter."
          >
            <Button
              variant="ghost"
              onClick={() => {
                setQuery("");
                setCategory("");
                setFormat("");
              }}
            >
              Clear filters
            </Button>
          </Empty>
        )}
        <p className="notice">
          <ShieldCheck size={16} strokeWidth={1.5} /> Student eligibility is
          verified in the participant portal, either by roster match,
          institutional email or a reviewed document.
        </p>
      </section>
    </>
  );
}

export function EventDetail() {
  const { slug } = useSite();
  const { eventSlug } = useParams();
  const detail = useAsync(
    () => publicApi.event(slug, eventSlug),
    [slug, eventSlug],
    {
      enabled: Boolean(slug && eventSlug),
    },
  );

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
        <ErrorBox
          error={detail.error}
          onRetry={detail.reload}
          title="Event not found"
        />
        <div className="center-actions" style={{ marginTop: "24px" }}>
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

  const isTeam = event.format === "team";
  const accent = getEventAccent(event);

  return (
    <>
      {/* Full-bleed banner — banner image if available, atmospheric fallback otherwise */}
      <div className="event-detail-hero">
        <div className="event-detail-hero-bg">
          {event.bannerUrl ? (
            <img
              src={event.bannerUrl}
              alt=""
              className="event-detail-hero-img"
            />
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
              {isTeam
                ? `Team · ${event.teamMinSize || 2}–${event.teamMaxSize || 4}`
                : "Individual"}
            </span>
          </div>
          <h1 className="event-detail-hero-title">{event.title}</h1>
          {event.summary ? (
            <p className="event-detail-hero-desc">{event.summary}</p>
          ) : null}
          <div className="event-detail-hero-badges">
            <Badge tone={event.registrationOpen ? "good" : "muted"}>
              {event.registrationOpen
                ? "Registration open"
                : "Registration closed"}
            </Badge>
            {event.isFeatured ? <Badge tone="accent">Featured</Badge> : null}
          </div>
        </div>
      </div>

      {/* Breadcrumb navigation */}
      <div className="event-detail-breadcrumb">
        <Link to="/events" className="event-detail-back">
          <ArrowRight
            size={13}
            style={{ transform: "rotate(180deg)" }}
            strokeWidth={2}
          />
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
              <div
                className="rich-text"
                dangerouslySetInnerHTML={{ __html: event.rulesHtml }}
              />
            </>
          ) : null}
          {event.prizesHtml ? (
            <>
              <h3>Prizes</h3>
              <div
                className="rich-text"
                dangerouslySetInnerHTML={{ __html: event.prizesHtml }}
              />
            </>
          ) : null}
          <p className="notice">
            <ShieldCheck size={16} strokeWidth={1.5} /> Eligibility is confirmed
            through the participant portal before a registration is treated as
            final.
          </p>
        </article>
        <aside className="detail-card">
          <span className="detail-card-label">EVENT DETAILS</span>
          <div className="detail-row">
            <span>Format</span>
            <b style={{ textTransform: "capitalize" }}>{event.format}</b>
          </div>
          {isTeam ? (
            <div className="detail-row">
              <span>Team size</span>
              <b>
                {event.teamMinSize}–{event.teamMaxSize} members
              </b>
            </div>
          ) : null}
          <div className="detail-row">
            <span>Included value</span>
            <b>{money(event.baseValuePaise)}</b>
          </div>
          <div className="detail-row">
            <span>Add-on fee</span>
            <b>{money(event.addonPricePaise)}</b>
          </div>
          <div className="detail-row">
            <span>Capacity</span>
            <b>
              {event.capacity || "Unlimited"}
              {event.seatsLeft != null ? ` · ${event.seatsLeft} left` : ""}
            </b>
          </div>
          <div className="detail-row">
            <span>Schedule</span>
            <b>
              {event.startsAt
                ? `${date(event.startsAt)} · ${time(event.startsAt)}${event.endsAt ? ` – ${time(event.endsAt)}` : ""}`
                : "TBA"}
            </b>
          </div>
          <div className="detail-row">
            <span>Venue</span>
            <b>{event.venueRoom || "To be announced"}</b>
          </div>
          {event.teamFeeBasis || event.addonChargeBasis ? (
            <div className="detail-row">
              <span>Fee basis</span>
              <b>{event.teamFeeBasis || event.addonChargeBasis}</b>
            </div>
          ) : null}
          <p className="detail-card-note">
            Every participant needs an active convention pass. Add-on fees are
            charged separately.
          </p>
          <Button to="/portal/select-events" icon={ArrowRight} className="full">
            Plan this in your portal
          </Button>
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
  const mode = policy?.includedSelectionMode === "exact" ? "Exactly" : "Up to";
  const lunchDays = policy?.lunchIncludedDays?.length || 2;
  const includedCount = policy?.includedEventCount || 3;
  const priceRupees = Math.round((policy?.passPricePaise || 35000) / 100);
  const valueCap = money(policy?.includedValueCapPaise || 45000);

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
        desc="A single registration unlocks full floor access across both days. The pass, included allowance and add-ons are transparently structured."
      />

      <section className="section apple-pass-page-section">
        <div className="apple-pass-page-grid">
          <article className="apple-pass-pricing-box apple-pass-page-card">
            <span className="apple-price-caption">ALL-ACCESS PASS</span>
            <div className="apple-price-amount">
              <span className="apple-price-currency">₹</span>
              <span className="apple-price-number">{priceRupees}</span>
              <span className="apple-price-tenure">/ pass</span>
            </div>
            <p className="apple-price-note">
              {edition?.name || "Parallax 2026"} Convention Pass
            </p>

            <div
              className="apple-pass-benefits"
              style={{ margin: "24px 0 28px", width: "100%" }}
            >
              <div className="apple-benefit-row">
                <span className="apple-check-icon">
                  <Check size={13} strokeWidth={2.4} />
                </span>
                <span>
                  <b>Lunch included</b> on both convention days ({lunchDays}{" "}
                  days)
                </span>
              </div>
              <div className="apple-benefit-row">
                <span className="apple-check-icon">
                  <Check size={13} strokeWidth={2.4} />
                </span>
                <span>
                  <b>
                    {mode} {includedCount} included events
                  </b>{" "}
                  within {valueCap} base cap
                </span>
              </div>
              <div className="apple-benefit-row">
                <span className="apple-check-icon">
                  <Check size={13} strokeWidth={2.4} />
                </span>
                <span>
                  <b>Full floor access</b> with verified digital convention
                  ticket
                </span>
              </div>
            </div>

            <Link to="/portal/pass" className="apple-pass-btn">
              <span>Get your pass</span>
              <span className="apple-btn-arrow">
                <ArrowRight size={14} strokeWidth={2.4} />
              </span>
            </Link>

            <small className="apple-instant-tag" style={{ marginTop: "16px" }}>
              {policy?.gstNote || "Fees in Indian rupees."} Paid securely in the
              portal.
            </small>
          </article>

          <article className="apple-pass-copy-card">
            <span className="apple-pass-kicker">PRICING ARCHITECTURE</span>
            <h2>
              Pass first.
              <br />
              <em>Then pick your programme.</em>
            </h2>

            <ol className="apple-pass-steps">
              <li>
                <b>01 / Every participant gets one pass</b>
                <p>
                  It includes lunch on both days and is required before
                  reserving any event in the catalogue.
                </p>
              </li>
              <li>
                <b>
                  02 / Choose {mode.toLowerCase()} {includedCount} eligible
                  events
                </b>
                <p>
                  The sum of their published base values stays within the{" "}
                  {valueCap} allowance. The pass fee is never deducted from that
                  sum.
                </p>
              </li>
              <li>
                <b>03 / Add extra events separately</b>
                <p>
                  Additional challenge registrations use each event’s published
                  add-on fee and can be reserved after your pass.
                </p>
              </li>
              <li>
                <b>04 / Team members each hold a pass</b>
                <p>
                  {policy?.teamMembersRequirePass
                    ? "Every team member must hold an active pass before the team entry is confirmed."
                    : "Team entry is available without a separate pass per member in this edition."}
                </p>
              </li>
            </ol>

            <div className="apple-cap-well">
              <span className="apple-cap-title">INCLUDED EVENT VALUE CAP</span>
              <b className="apple-cap-amount">
                {valueCap} <small>live edition policy</small>
              </b>
              <p>
                Selection locks on {date(policy?.selectionChangeDeadline)}.
                Unpaid add-on reservations expire after{" "}
                {policy?.holdMinutes || 15} minutes.
              </p>
            </div>
          </article>
        </div>
      </section>
    </>
  );
}

export function SchedulePage() {
  const { slug } = useSite();
  const schedule = useAsync(() => publicApi.schedule(slug), [slug], {
    enabled: Boolean(slug),
  });
  const days = schedule.data?.data || [];

  const formatTimeSlot = (startIso, endIso) => {
    if (!startIso) return "TBA";
    const s = time(startIso);
    const e = time(endIso);
    if (!e) return s;
    const sNum = s.replace(/\s*[ap]m/i, "").trim();
    const eClean = e.toUpperCase().trim();
    return `${sNum} – ${eClean}`;
  };

  const totalSessions = days.reduce(
    (sum, d) => sum + (d.items?.length || 0),
    0,
  );

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
        desc="Every published session, ordered by its live start time and room assignment."
        aside={
          totalSessions > 0 ? (
            <div className="schedule-stat-pill">
              <span className="schedule-stat-num">{totalSessions}</span>
              <span className="schedule-stat-label">sessions scheduled</span>
            </div>
          ) : null
        }
      />
      <section className="section apple-schedule-section">
        {schedule.loading ? (
          <Loading label="Loading schedule" rows={3} />
        ) : null}
        {schedule.error ? (
          <ErrorBox error={schedule.error} onRetry={schedule.reload} />
        ) : null}
        {!schedule.loading && !schedule.error && !days.length ? (
          <Empty
            title="The schedule is not published"
            desc="Sessions will appear here once released."
          />
        ) : null}
        <div className="apple-schedule-grid">
          {days.map((day, index) => {
            const count = day.items?.length || 0;
            const firstTime = day.items?.[0] ? time(day.items[0].startsAt) : "";
            const lastTime = day.items?.[count - 1]
              ? time(day.items[count - 1].endsAt)
              : "";
            const d = new Date(day.date);
            const wkd = isNaN(d.getTime())
              ? `DAY 0${index + 1}`
              : d
                  .toLocaleDateString("en-US", { weekday: "short" })
                  .toUpperCase();
            const dateStr = isNaN(d.getTime())
              ? day.label
              : d.toLocaleDateString("en-US", {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                });

            return (
              <article
                className="apple-schedule-card rise"
                key={day.date}
                style={{ animationDelay: `${index * 80}ms` }}
              >
                <div className="apple-schedule-head">
                  <div className="apple-schedule-kicker-row">
                    <span className="apple-schedule-kicker">
                      {wkd} · DAY 0{index + 1}
                    </span>
                    <span className="apple-schedule-count">
                      {count} {count === 1 ? "session" : "sessions"}
                      {firstTime ? ` · ${firstTime} – ${lastTime}` : ""}
                    </span>
                  </div>
                  <h2 className="apple-schedule-heading">{dateStr}</h2>
                </div>

                {count === 0 ? (
                  <p className="apple-schedule-empty">
                    Sessions to be announced.
                  </p>
                ) : (
                  <ol className="apple-schedule-rows">
                    {(day.items || []).map((item, i) => (
                      <li key={item.id} className="apple-schedule-item">
                        <Link
                          to={`/events/${item.slug}`}
                          className="apple-schedule-row-link"
                        >
                          <time
                            className="apple-schedule-time"
                            dateTime={item.startsAt}
                          >
                            <span
                              className="apple-schedule-dot"
                              aria-hidden="true"
                            />
                            <span>
                              {formatTimeSlot(item.startsAt, item.endsAt)}
                            </span>
                          </time>
                          <div className="apple-schedule-content">
                            <b className="apple-schedule-title">{item.title}</b>
                            <span className="apple-schedule-room">
                              <MapPin
                                size={11}
                                strokeWidth={1.8}
                                style={{ opacity: 0.6 }}
                              />
                              <span>{item.room || "Room TBA"}</span>
                            </span>
                          </div>
                          <div className="apple-schedule-meta">
                            {item.category ? (
                              <span className="apple-schedule-tag">
                                {item.category}
                              </span>
                            ) : null}
                            <ArrowRight
                              size={13}
                              strokeWidth={1.8}
                              className="apple-schedule-arrow"
                            />
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ol>
                )}
              </article>
            );
          })}
        </div>
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
            <em>{edition?.city?.split(",")[0] || "Palakkad"}.</em>
          </>
        }
        desc={`${edition?.venue || "Campus"}, hosted by ${edition?.host || "NSSCE"}.`}
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
          <h2>{edition?.host || "NSS College of Engineering"}</h2>
          <p>{edition?.city || "Palakkad, Kerala"}</p>
          <p>
            Sessions run across {edition?.venue || "campus halls"}. Room numbers
            and lab assignments are published with each session in the live
            schedule; registration check-in opens at the campus main auditorium
            on both days.
          </p>
          <div className="detail-row">
            <span>Dates</span>
            <b>{dateRange(edition?.startsAt, edition?.endsAt)}</b>
          </div>
          <div className="detail-row">
            <span>Venue</span>
            <b>{edition?.venue || "Campus"}</b>
          </div>
          <div className="detail-row">
            <span>City</span>
            <b>{edition?.city || "Palakkad"}</b>
          </div>
          <div className="detail-row">
            <span>Transit Access</span>
            <b>
              Palakkad Junction (PGT) ~ 7 km · Coimbatore Airport (CJB) ~ 65 km
            </b>
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
  const mode = policy?.includedSelectionMode === "exact" ? "exactly" : "up to";
  const rows = [
    [
      "Is the convention pass mandatory?",
      `Yes. Every participant needs their own ${money(policy?.passPricePaise)} pass. Event add-on fees never replace it.`,
    ],
    [
      "What does the pass include?",
      `Lunch on ${(policy?.lunchIncludedDays || []).map(dayLabel).join(" and ") || "both convention days"}, full floor access, and an included event allowance.`,
    ],
    [
      "How many included events can I select?",
      `${mode} ${policy?.includedEventCount} eligible events, with a base-value cap of ${money(policy?.includedValueCapPaise)}.`,
    ],
    [
      "Can I change my included selections?",
      `Until ${date(policy?.selectionChangeDeadline)}. After that the selection locks and the portal disables edits.`,
    ],
    [
      "Can I register for more events?",
      policy?.addonRequiresPass
        ? "Yes, after the pass. Extra events use their published add-on fee."
        : "Yes. Add-on events can be reserved separately.",
    ],
    [
      "How does the team rule work?",
      policy?.teamMembersRequirePass
        ? "Each team member must hold an active pass before the team entry can be confirmed."
        : "Team entry is available without a separate pass for each member in this edition.",
    ],
    [
      "How is student eligibility verified?",
      "By roster match, institutional email confirmation, or a reviewed student document in the portal.",
    ],
    [
      "What happens after payment?",
      "The pass activates immediately, included registrations are created, and an entry ticket with a scannable token is issued.",
    ],
    [
      "Can I get a refund?",
      "Refunds are handled by the finance team against a paid order. Ask the organisers through the contact address.",
    ],
    [
      "Where do I get help?",
      `Write to ${edition?.contactEmail || "the organisers"}.`,
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
        desc="Answers reflect the live edition policy, fees, and convention regulations."
      />
      <section className="section apple-faq-section">
        <div className="apple-faq-list">
          {rows.map(([question, answer], index) => (
            <details className="apple-faq-card" key={question}>
              <summary className="apple-faq-summary">
                <div className="apple-faq-q-left">
                  <span className="apple-faq-num">
                    {`0${index + 1}`.slice(-2)}
                  </span>
                  <span className="apple-faq-question">{question}</span>
                </div>
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
    </>
  );
}

const TEAM_GROUPS = [
  {
    title: 'Faculty Leadership',
    description: 'The faculty members guiding and supporting the convention.',
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
    description: 'The student leadership driving Parallax forward.',
    members: [
      {
        name: 'Kaladharan Lal',
        role: 'Chairperson',
        image: 'chairperson.jpg',
      },
      {
        name: 'Student Name',
        role: 'Secretary',
        image: 'secretary.jpg',
      },
    ],
  },
  {
    title: 'Core Organising Team',
    description: 'The coordinators responsible for bringing every aspect of the convention together.',
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
        image: 'finance-coordinator.jpg',
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
  {
    title: 'Web-Dev Team',
    description: 'The brains behind this dynamic and advanced full-stack web app.',
    members: [
      {
        name: 'Mithun',
        role: 'Backend',
        image: 'backend.jpg',
      },
      {
        name: 'Arjun',
        role: 'Frontend',
        image: 'frontend.jpg',
      },
      {
        name: 'Kaladharan Lal',
        role: 'System Design',
        image: 'chairperson.jpg',
      },
    ],
  },
];

function TeamMemberCard({ member }) {
  const imageUrl =
    `${import.meta.env.BASE_URL}images/team/${member.image}`;

  return (
    <article className="team-member-card">
      <div className="team-member-image">
        <img
          src={imageUrl}
          alt={member.name}
          loading="lazy"
          onError={(e) => {
            e.currentTarget.style.display = 'none';
          }}
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
    <>
      <PageTitle
        kicker="The People Behind Parallax"
        title={
          <>
            Behind every great event
            <br />
            <em>is a great team.</em>
          </>
        }
        desc="Meet the people whose dedication, teamwork and vision brought Parallax to life."
      />

      <section className="team-page">
        {TEAM_GROUPS.map((group, index) => (
          <section
            className="team-group"
            key={group.title}
          >
            <div className="team-group-heading">
              <span className="team-index">
                {String(index + 1).padStart(2, '0')}
              </span>

              <div>
                <h2>{group.title}</h2>
                <p>{group.description}</p>
              </div>
            </div>

            <div className="team-grid">
              {group.members.map((member) => (
                <TeamMemberCard
                  key={member.role}
                  member={member}
                />
              ))}
            </div>
          </section>
        ))}
      </section>
    </>
  );
}

export function ContactPage() {
  const { edition } = useSite();
  const email = edition?.contactEmail || "iste@nssce.ac.in";
  const [topic, setTopic] = useState("general");
  const [name, setName] = useState("");
  const [senderEmail, setSenderEmail] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);

  const topics = [
    { id: "pass", label: "Pass & Pricing" },
    { id: "events", label: "Event Rules & Registration" },
    { id: "teams", label: "Team Coordination" },
    { id: "travel", label: "Travel & Accommodation" },
    { id: "general", label: "General Inquiries" },
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    const topicLabel = topics.find((t) => t.id === topic)?.label || "General";
    const subject = encodeURIComponent(
      `[Parallax 2026] Inquiry: ${topicLabel}`,
    );
    const body = encodeURIComponent(
      `Name: ${name || "Participant"}\nEmail: ${senderEmail || "Not provided"}\nCategory: ${topicLabel}\n\nMessage:\n${message}\n\n--\nSent via Parallax 2026 Portal`,
    );
    window.location.href = `mailto:${email}?subject=${subject}&body=${body}`;
    setSent(true);
  };

  return (
    <>
      <PageTitle
        kicker="Official Inquiries"
        title={
          <>
            Let’s get
            <br />
            <em>in touch.</em>
          </>
        }
        desc="Have questions about the convention, passes, challenge schedules, or campus logistics? Our organising team responds directly."
        aside={
          <div className="contact-status-card">
            <div className="contact-status-indicator">
              <span className="contact-status-pulse" />
              <span>Desk Online</span>
            </div>
            <span className="contact-status-hours">
              Typical response &lt; 4 hours
            </span>
          </div>
        }
      />

      <section className="section contact-section">
        {/* Touchpoint Cards Grid */}
        <div className="contact-cards-grid">
          {/* Card 1: Direct Convention Email */}
          <article className="contact-channel-card">
            <div className="contact-channel-icon-wrap">
              <Mail size={22} strokeWidth={1.8} />
            </div>
            <div className="contact-channel-body">
              <span className="contact-channel-tag">DIRECT INQUIRIES</span>
              <h3 className="contact-channel-title">
                Official Convention Email
              </h3>
              <p className="contact-channel-desc">
                For pass assistance, corporate partnerships, certificates, or
                general convention inquiries.
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
              <span className="contact-channel-tag">CAMPUS DESK</span>
              <h3 className="contact-channel-title">Host Institution</h3>
              <p className="contact-channel-desc">
                {edition?.host || "NSS College of Engineering"},{" "}
                {edition?.city || "Palakkad"}. Main desk at the auditorium.
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
              <span className="contact-channel-tag">STUDENT PORTAL</span>
              <h3 className="contact-channel-title">Self-Service Console</h3>
              <p className="contact-channel-desc">
                Review your registered sessions, team credentials, attendance QR
                tokens, and verification status.
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
              <span className="contact-dispatch-kicker">
                DIRECT TRANSMISSION
              </span>
              <h2 className="contact-dispatch-title">
                Send a message to the organisers
              </h2>
              <p className="contact-dispatch-desc">
                Select your category and fill out the details below. We'll
                prepare your dispatch with the organising committee.
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
              <span className="contact-field-label">
                Select Inquiry Category
              </span>
              <div className="contact-topic-chips">
                {topics.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`contact-topic-chip ${topic === t.id ? "is-active" : ""}`}
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
                  placeholder="e.g. Alex Kumar"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
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
                  placeholder="e.g. alex@college.edu"
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
              />
            </div>

            <div className="contact-form-footer">
              <button type="submit" className="contact-submit-btn">
                <span>Dispatch Email Inquiry</span>
                <Send size={15} strokeWidth={2} />
              </button>

              <span className="contact-dispatch-note">
                Direct route to {email}
              </span>
            </div>

            {sent && (
              <div className="contact-sent-notice">
                <Check size={16} strokeWidth={2.4} />
                <span>
                  Inquiry opened in your email client. If it did not open,
                  please write directly to <b>{email}</b>.
                </span>
              </div>
            )}
          </form>
        </div>

        {/* Quick FAQ Callout Banner */}
        <div className="contact-faq-banner">
          <div className="contact-faq-banner-content">
            <HelpCircle
              size={22}
              strokeWidth={1.8}
              className="contact-faq-icon"
            />
            <div>
              <h4>Looking for instant answers?</h4>
              <p>
                Common questions about pass validity, lunch inclusions, team
                member rules, and cancellations are documented in the FAQ.
              </p>
            </div>
          </div>
          <Link to="/faq" className="contact-faq-btn">
            <span>Read FAQ</span>
            <ArrowRight size={14} strokeWidth={2} />
          </Link>
        </div>
      </section>
    </>
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
          aria-label={`${edition?.name || "Parallax 2026"} home`}
        >
          <img
            src={LOGO}
            alt={edition?.name || "Parallax 2026"}
            className="footer-logo"
          />
        </Link>
        <p>
          A shift in perspective.
          <br />A leap in innovation.
        </p>
        <div className="footer-host">
          <img src={ISTE} alt={`${edition?.organizer || "ISTE"} emblem`} />
          <span>
            Hosted by {edition?.host || "NSSCE"}
            <br />
            {edition?.city || "Palakkad"}
          </span>
        </div>
      </div>
      <div className="footer-links">
        {[
          ["About", "/about"],
          ["Events", "/events"],
          ["Convention pass", "/pass"],
          ["Schedule", "/schedule"],
          ["Venue", "/venue"],
          ["FAQ", "/faq"],
          ["Contact", "/contact"],
          ["Portal", "/portal"],
        ].map(([label, to]) => (
          <Link key={to} to={to}>
            {label}
          </Link>
        ))}
      </div>
      <div className="footer-bottom">
        <span>
          © {new Date().getFullYear()} {edition?.name || "Parallax 2026"} ·{" "}
          {edition?.organizer || "ISTE"}
        </span>
        <span>{dateRange(edition?.startsAt, edition?.endsAt)}</span>
        <span className="social">
          <Ticket size={16} strokeWidth={1.4} /> Live convention platform
        </span>
      </div>
    </footer>
  );
}

export { ISTE, LOGO, NSSCE, GLOBE };
