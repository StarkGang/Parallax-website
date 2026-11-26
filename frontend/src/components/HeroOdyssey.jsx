import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ArrowDown } from 'lucide-react';
import "./HeroOdyssey.css";

const STRIP_TOP = `${import.meta.env.BASE_URL}images/ho-strip-top.webp`;
const STRIP_BOTTOM = `${import.meta.env.BASE_URL}images/ho-strip-bottom.webp`;
const HERO_BG_COSMOS = `${import.meta.env.BASE_URL}images/ho-bg-cosmos.webp`;

export default function HeroOdyssey({
  desc = "Explore a convention built for bold ideas, practical engineering, and new perspectives.",
  facts = [],
}) {
  const rootRef = useRef(null);

  // Extract duration, date range, and venue cleanly from facts if provided
  const daysText = facts[0] || "2 days";
  const dateText = facts[1] || "08 Jan – 09 Jan 2027";
  const venueText = facts[2] || "NSS College of Engineering, Palakkad, Kerala";

  // Pull big day numbers (e.g. "08–09") and month/year (e.g. "JAN 2027")
  const dayMatches = dateText.match(/\b\d{1,2}\b/g) || ["08", "09"];
  const bigDays =
    dayMatches.length >= 2 ? `${dayMatches[0]}–${dayMatches[1]}` : dayMatches[0];
  const monthMatch = dateText.match(/[A-Za-z]{3,}/);
  const yearMatch = dateText.match(/\b20\d{2}\b/);
  const monthYear = `${(monthMatch ? monthMatch[0] : "JAN").toUpperCase()} ${yearMatch ? yearMatch[0] : "2027"}`;

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;

    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reducedMotion) return undefined;

    const ctx = gsap.context(() => {
      const lines = root.querySelectorAll(".ho-display-inner");
      const strips = root.querySelectorAll(".ho-media-strip");
      const stripImgs = root.querySelectorAll(".ho-media-strip img");
      const meta = root.querySelector(".ho-meta");
      const sideTag = root.querySelector(".ho-row-tag");
      const credit = root.querySelector(".ho-credit");

      const tl = gsap.timeline({
        paused: true,
        defaults: { force3D: true, clearProps: "transform,opacity" },
      });

      if (lines.length) {
        tl.from(
          lines,
          {
            opacity: 0,
            yPercent: 100,
            duration: 1.6,
            ease: "expo.inOut",
            stagger: 0.1,
          },
          0.06,
        );
      }

      if (strips.length) {
        tl.from(
          strips,
          {
            yPercent: 100,
            duration: 1.75,
            ease: "expo.inOut",
            stagger: 0.08,
          },
          0.12,
        );
      }

      if (stripImgs.length) {
        tl.from(
          stripImgs,
          {
            yPercent: -100,
            scale: 1.22,
            opacity: 0,
            duration: 1.75,
            ease: "expo.inOut",
            stagger: 0.08,
          },
          0.12,
        );
      }

      if (sideTag) {
        tl.from(
          sideTag,
          {
            opacity: 0,
            x: 16,
            duration: 1.0,
            ease: "expo.out",
          },
          0.62,
        );
      }

      if (meta) {
        tl.from(
          meta,
          {
            opacity: 0,
            y: 18,
            duration: 1.0,
            ease: "expo.out",
          },
          0.78,
        );
      }

      if (credit) {
        tl.from(
          credit,
          {
            opacity: 0,
            duration: 0.85,
            ease: "power2.out",
          },
          0.92,
        );
      }

      let started = false;
      let fallbackTimer = 0;
      const startReveal = () => {
        if (started) return;
        started = true;
        clearTimeout(fallbackTimer);
        requestAnimationFrame(() => tl.play(0));
      };

      let alreadyBooted = false;
      try {
        alreadyBooted = Boolean(sessionStorage.getItem("px_booted"));
      } catch {}

      if (alreadyBooted || window.__pxBootPhase !== "booting") {
        startReveal();
      } else {
        window.addEventListener("parallax:boot-reveal", startReveal, { once: true });
        fallbackTimer = window.setTimeout(startReveal, 900);
      }
    }, root);

    return () => ctx.revert();
  }, []);

  return (
    <section className="ho-root" ref={rootRef} aria-labelledby="home-hero-title">
      <div className="ho-bg" aria-hidden="true">
        <img className="ho-bg-img" src={HERO_BG_COSMOS} alt="" decoding="async" />
        <div className="ho-aura ho-aura--indigo" />
        <div className="ho-aura ho-aura--cyan" />
        <div className="ho-overlay" />
      </div>

      <div className="ho-container">
        <div className="ho-editorial" id="home-hero-title">
          {/* Row 1: Display text + counter-parallax liquid-blue strip */}
          <div className="ho-row">
            <span className="ho-display">
              <i className="ho-display-inner">ISTE 25TH</i>
            </span>
            <span className="ho-media-mask" aria-hidden="true">
              <span className="ho-media-strip">
                <img src={STRIP_TOP} alt="" decoding="async" />
              </span>
            </span>
          </div>

          {/* Row 2: Italic editorial accent + display text + subtle edition tag */}
          <div className="ho-row">
            <span className="ho-display ho-display--italic">
              <i className="ho-display-inner">ANNUAL</i>
            </span>
            <span className="ho-display">
              <i className="ho-display-inner">STUDENT</i>
            </span>
            <span className="ho-row-tag" aria-hidden="true">
              <span className="ho-row-tag-roman">XXV</span>
              <span className="ho-row-tag-copy">
                <span className="ho-row-tag-kicker">PARALLAX</span>
                <span className="ho-row-tag-sub">25TH EDITION</span>
              </span>
            </span>
          </div>

          {/* Row 3: Counter-parallax atmospheric strip + display text */}
          <div className="ho-row">
            <span className="ho-media-mask" aria-hidden="true">
              <span className="ho-media-strip">
                <img src={STRIP_BOTTOM} alt="" decoding="async" />
              </span>
            </span>
            <span className="ho-display">
              <i className="ho-display-inner">CONVENTION.</i>
            </span>
          </div>
        </div>

        <div className="ho-meta">
          <p className="ho-desc">{desc}</p>

          <div className="ho-stats" aria-label="Event dates and venue">
            <div className="ho-date-block">
              <span className="ho-date-big">{bigDays}</span>
              <span className="ho-date-sub">
                <b>{monthYear}</b>
                <small>{daysText}</small>
              </span>
            </div>

            <div className="ho-venue-block">
              <span className="ho-venue-kicker">HOST VENUE</span>
              <span className="ho-venue-name">{venueText}</span>
            </div>
          </div>

          <button
            type="button"
            className="ho-cta lusion-btn lusion-btn-primary"
            onClick={() => window.scrollTo({ top: 150, behavior: "smooth" })}
          >
            <span>Dive in</span>
            <span className="lusion-btn-icon">
              <ArrowDown size={15} strokeWidth={2.2} aria-hidden="true" />
            </span>
          </button>
        </div>

        <div className="ho-credit">
          <span>DESIGNED & ENGINEERED BY </span>
          <a
            href="https://midhunkm.pages.dev"
            target="_blank"
            rel="noopener noreferrer"
          >
            MIDHUN K M
          </a>
        </div>
      </div>
    </section>
  );
}
