import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ArrowRight, ArrowUpRight, RefreshCw } from 'lucide-react';
import { Link } from "react-router-dom";
import { mascotSay } from "./mascot/mascotSay.js";
import "./HeroOdyssey.css";
import "./StatePages.css";

const HERO_BG_COSMOS = `${import.meta.env.BASE_URL}images/ho-bg-cosmos.webp`;
const STRIP_TOP = `${import.meta.env.BASE_URL}images/ho-strip-top.webp`;
const STRIP_BOTTOM = `${import.meta.env.BASE_URL}images/ho-strip-bottom.webp`;

/**
 * Full-screen state page (404 / error) built from the same Odyssey lockup as the
 * home hero: dark cosmos backdrop, auras, editorial display rows and a gold tag.
 */
export function StatePage({ code, italic, title, tail, message, children }) {
  const rootRef = useRef(null);

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
      const tag = root.querySelector(".ho-row-tag");
      const meta = root.querySelector(".ho-meta");

      const tl = gsap.timeline();
      if (lines.length) {
        tl.from(
          lines,
          { opacity: 0, yPercent: 100, duration: 1.2, ease: "expo.inOut", stagger: 0.08 },
          0.05,
        );
      }
      if (strips.length) {
        tl.from(
          strips,
          { yPercent: 100, duration: 1.3, ease: "expo.inOut", stagger: 0.08 },
          0.1,
        );
      }
      if (tag) {
        tl.from(tag, { opacity: 0, x: 16, duration: 0.8, ease: "expo.out" }, 0.5);
      }
      if (meta) {
        tl.from(meta, { opacity: 0, y: 18, duration: 0.9, ease: "expo.out" }, 0.6);
      }
    }, root);

    return () => ctx.revert();
  }, []);

  return (
    <section className="ho-root state-page" ref={rootRef} aria-labelledby="state-title">
      <div className="ho-bg" aria-hidden="true">
        <img className="ho-bg-img" src={HERO_BG_COSMOS} alt="" decoding="async" />
        <div className="ho-aura ho-aura--indigo" />
        <div className="ho-aura ho-aura--cyan" />
        <div className="ho-overlay" />
      </div>

      <div className="ho-container">
        <div className="ho-editorial" id="state-title">
          <div className="ho-row">
            <span className="ho-display">
              <i className="ho-display-inner">{code}</i>
            </span>
            <span className="ho-media-mask" aria-hidden="true">
              <span className="ho-media-strip">
                <img src={STRIP_TOP} alt="" decoding="async" />
              </span>
            </span>
          </div>

          <div className="ho-row">
            <span className="ho-display ho-display--italic">
              <i className="ho-display-inner">{italic}</i>
            </span>
            <span className="ho-display">
              <i className="ho-display-inner">{title}</i>
            </span>
            <span className="ho-row-tag" aria-hidden="true">
              <span className="ho-row-tag-roman">{code}</span>
              <span className="ho-row-tag-copy">
                <span className="ho-row-tag-kicker">PARALLAX</span>
                <span className="ho-row-tag-sub">2027 EDITION</span>
              </span>
            </span>
          </div>

          <div className="ho-row">
            <span className="ho-media-mask" aria-hidden="true">
              <span className="ho-media-strip">
                <img src={STRIP_BOTTOM} alt="" decoding="async" />
              </span>
            </span>
            <span className="ho-display">
              <i className="ho-display-inner">{tail}</i>
            </span>
          </div>
        </div>

        <div className="ho-meta">
          <p className="ho-desc">{message}</p>
          <div className="ho-cta state-actions">{children}</div>
        </div>

        <div className="ho-credit">
          <span>DESIGNED &amp; ENGINEERED BY </span>
          <a href="https://midhunkm.pages.dev" target="_blank" rel="noopener noreferrer">
            MIDHUN K M
          </a>
        </div>
      </div>
    </section>
  );
}

export function NotFoundPage() {
  return (
    <StatePage
      code="404"
      italic="OFF THE"
      title="MAP."
      tail="GO BACK."
      message="This page drifted off the programme. The link may be old, or the event moved in the catalogue."
    >
      <Link
        to="/"
        className="lusion-btn lusion-btn-primary"
        onPointerEnter={() => mascotSay("Wrong turn, let's head back.", 5200, "jump")}
      >
        <span>Back to convention</span>
        <span className="lusion-btn-icon">
          <ArrowRight size={15} strokeWidth={2.2} aria-hidden="true" />
        </span>
      </Link>
      <Link
        to="/events"
        className="lusion-btn lusion-btn-ghost"
        onPointerEnter={() => mascotSay("Browse events, the real ones are waiting.", 5200, "wave")}
      >
        <span>Browse events</span>
        <span className="lusion-btn-icon">
          <ArrowUpRight size={15} strokeWidth={2.2} aria-hidden="true" />
        </span>
      </Link>
    </StatePage>
  );
}

export function ErrorPage({ onRetry }) {
  return (
    <StatePage
      code="ERR"
      italic="OOPS"
      title="BROKE."
      tail="TRY AGAIN."
      message="A gremlin got into the works. Nothing you did. Give it another shot, or head back to the convention."
    >
      <button
        type="button"
        className="lusion-btn lusion-btn-primary"
        onClick={onRetry}
        onPointerEnter={() => mascotSay("Let's give that another go.", 5200, "wave")}
      >
        <span>Try again</span>
        <span className="lusion-btn-icon">
          <RefreshCw size={15} strokeWidth={2.2} aria-hidden="true" />
        </span>
      </button>
      <Link
        to="/"
        className="lusion-btn lusion-btn-ghost"
        onPointerEnter={() => mascotSay("Back home, no questions asked.", 5200, "jump")}
      >
        <span>Back home</span>
        <span className="lusion-btn-icon">
          <ArrowRight size={15} strokeWidth={2.2} aria-hidden="true" />
        </span>
      </Link>
    </StatePage>
  );
}