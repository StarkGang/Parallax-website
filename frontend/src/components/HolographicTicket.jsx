import { useRef } from "react";
import { Link } from "react-router-dom";
import { useSite } from "../lib/site.jsx";
import { dateRange, money } from "../lib/format.js";

/**
 * HolographicTicket
 * 3D-tilt convention ticket with holographic foil + specular highlight.
 * Dependencies: React only (styles are injected via <style>, no Tailwind needed).
 */
export default function HolographicTicket({
  eyebrow,
  name,
  venue,
  dates,
  city,
  stubText,
  price,
  perks,
}) {
  const { edition, policy } = useSite();
  const tiltRef = useRef(null);

  // The card reads the live edition and policy itself, so no caller can ship
  // placeholder copy by forgetting a prop. Explicit props still win.
  const includedCount = policy?.includedEventCount;
  const lunchDays = policy?.lunchIncludedDays?.length;
  const resolved = {
    eyebrow: eyebrow ?? "Two days of engineering. One all-pass.",
    name: name ?? `${edition?.name ?? "Convention"} Pass`,
    venue:
      venue ??
      "Full floor clearance, competitions, workshops and every exhibition - no gated tracks.",
    dates: dates ?? dateRange(edition?.startsAt, edition?.endsAt),
    city: city ?? edition?.city ?? "Palakkad, Kerala",
    stubText:
      stubText ??
      (policy?.passPricePaise
        ? money(policy.passPricePaise)
        : "Price reveal"),
    price: price ?? "Get now",
    perks:
      perks ??
      [
        lunchDays === 2 ? "Lunch on both convention days" : "Lunch included",
        includedCount ? `Up to ${includedCount} included events` : "Included event allowance",
        "Unrestricted access to all exhibitions",
      ],
  };

  const isStubLong = resolved.stubText.length > 7;

  const handleMove = (e) => {
    const el = tiltRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    el.style.setProperty("--ry", `${(px - 0.5) * 18}deg`);
    el.style.setProperty("--rx", `${(0.5 - py) * 14}deg`);
    el.style.setProperty("--gx", `${px * 100}%`);
    el.style.setProperty("--gy", `${py * 100}%`);
    el.style.setProperty("--foil", `${px * 100}%`);
    el.style.setProperty("--lit", "1");
  };

  const handleLeave = () => {
    const el = tiltRef.current;
    if (!el) return;
    el.style.setProperty("--ry", "0deg");
    el.style.setProperty("--rx", "0deg");
    el.style.setProperty("--lit", "0");
  };

  return (
    <>
      <style>{css}</style>
      <div className="ht-stage">
        <div className="ht-back" aria-hidden="true" />
        <div className="ht-glow" aria-hidden="true" />
        <div
          ref={tiltRef}
          className="ht-tilt"
          onPointerMove={handleMove}
          onPointerLeave={handleLeave}
        >
        <Link to="/pass">
          <article className="ht-ticket" aria-label={`${resolved.name}, ${resolved.stubText}`}>
            <div className="ht-streak" aria-hidden="true" />
            <div className="ht-grain" aria-hidden="true" />

            <div className="ht-main">
              <p className="ht-eyebrow">{resolved.eyebrow}</p>

              <h2 className="ht-name">{resolved.name}</h2>

              <div className="ht-foot">
                <p className="ht-venue">
                  {resolved.venue} • {resolved.dates} • {resolved.city}
                </p>
                <ul className="ht-perks">
                  {resolved.perks.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
                {resolved.price && (
                  <div className="ht-cta-wrap">
                    <span className="ht-cta">{resolved.price} &rarr;</span>
                  </div>
                )}
              </div>
            </div>

            <div className={`ht-stub${isStubLong ? " is-long" : ""}`} aria-hidden="true">
              <span>{resolved.stubText}</span>
            </div>

            <div className="ht-foil" aria-hidden="true" />
            <div className="ht-glare" aria-hidden="true" />
          </article>
          </Link>
        </div>
        <p className="ht-hint">
          Instant digital verification in Student Portal. T&C applies
        </p>
      </div>
    </>
  );
}

const noise =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='1.1' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.55  0 0 0 0 0.35  0 0 0 0 1  0 0 0 1.4 -0.45'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")";

const css = `
@import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=JetBrains+Mono:wght@400;700&display=swap');

.ht-stage {
  --stub: 120px;
  position: relative;
  isolation: isolate;
  display: grid;
  place-items: center;
  gap: 28px;
  padding: 40px 16px;
  perspective: 1200px;
}

/* Rear plate gives the ticket thickness behind the front face. */
.ht-back {
  position: absolute;
  z-index: -1;
  top: 50%;
  left: 50%;
  width: min(706px, 90%);
  aspect-ratio: 760 / 420;
  translate: -50% -52%;
  transform: rotate(-2.4deg);
  border-radius: 12px;
  border: 1px solid rgba(126, 108, 220, 0.24);
  background: linear-gradient(160deg, rgba(25, 21, 44, 0.9), rgba(6, 8, 15, 0.94));
  box-shadow: 0 30px 60px -34px rgba(0, 0, 0, 0.95);
  pointer-events: none;
}

/* Contact glow so the ticket sits in the scene instead of floating on black. */
.ht-glow {
  position: absolute;
  z-index: -1;
  left: 50%;
  bottom: 12%;
  width: min(680px, 86%);
  height: 90px;
  translate: -50% 0;
  border-radius: 50%;
  background: radial-gradient(
    50% 50% at 50% 50%,
    rgba(124, 92, 255, 0.32) 0%,
    rgba(56, 189, 248, 0.16) 45%,
    rgba(5, 8, 15, 0) 75%
  );
  pointer-events: none;
}

.ht-tilt {
  --rx: 0deg; --ry: 0deg; --gx: 50%; --gy: 50%; --foil: 50%; --lit: 0;
  width: min(760px, 100%);
  transform: rotateX(var(--rx)) rotateY(var(--ry));
  transform-style: preserve-3d;
  transition: transform 0.35s cubic-bezier(.2,.7,.2,1);
  will-change: transform;
}
.ht-tilt:hover { transition: transform 0.08s linear; }

.ht-ticket {
  position: relative;
  display: grid;
  grid-template-columns: 1fr var(--stub);
  aspect-ratio: 760 / 430;
  min-height: 350px;
  overflow: hidden;
  border-radius: 10px;
  color: #f6f4fb;
  background:
    radial-gradient(60% 72% at 0% 26%, rgba(88, 42, 196, .58), transparent 62%),
    linear-gradient(160deg, #0a0d18 0%, #070a12 58%, #0d0a1c 100%);
  box-shadow:
    0 0 0 1px rgba(125, 211, 252, .16),
    0 26px 60px -26px rgba(0, 0, 0, .8),
    0 44px 100px -52px rgba(90, 40, 220, .6);
  -webkit-mask:
    radial-gradient(circle 14px at calc(100% - var(--stub)) 0, #0000 97%, #000),
    radial-gradient(circle 14px at calc(100% - var(--stub)) 100%, #0000 97%, #000);
  -webkit-mask-composite: source-in;
  mask:
    radial-gradient(circle 14px at calc(100% - var(--stub)) 0, #0000 97%, #000),
    radial-gradient(circle 14px at calc(100% - var(--stub)) 100%, #0000 97%, #000);
  mask-composite: intersect;
}

.ht-grain {
  position: absolute; inset: 0;
  background-image: ${noise};
  opacity: .38;
  mix-blend-mode: screen;
  pointer-events: none;
}

.ht-streak {
  position: absolute; left: -10%; bottom: 8%;
  width: 60%; height: 2px;
  background: linear-gradient(90deg, transparent, rgba(120, 70, 255, .9));
  transform: rotate(28deg);
  transform-origin: left center;
  pointer-events: none;
}

.ht-main {
  position: relative; z-index: 1;
  display: flex; flex-direction: column; justify-content: space-between;
  padding: clamp(20px, 4vw, 36px) clamp(22px, 4.5vw, 44px);
  gap: clamp(10px, 1.8vw, 18px);
  font-family: 'JetBrains Mono', ui-monospace, Menlo, Consolas, monospace;
  transform: translateZ(30px);
}

.ht-eyebrow {
  margin: 0;
  font-size: clamp(10px, 1.4vw, 12.5px);
  letter-spacing: .04em;
  color: #a8a2b8;
}

.ht-name {
  margin: 0;
  font-family: 'Archivo Black', 'Segoe UI', system-ui, sans-serif;
  font-weight: 900;
  font-size: clamp(28px, 6vw, 52px);
  line-height: 1.02;
  letter-spacing: -.01em;
  text-transform: uppercase;
  max-width: 12ch;
}

.ht-foot {
  display: grid;
  gap: 8px;
}

.ht-venue {
  margin: 0;
  font-size: clamp(9.5px, 1.35vw, 12px);
  font-weight: 700;
  letter-spacing: .02em;
  line-height: 1.4;
  color: #ddd9ea;
}

.ht-perks {
  display: flex; flex-wrap: wrap; gap: 4px 12px;
  margin: 0; padding: 0; list-style: none;
  font-size: clamp(8.5px, 1.2vw, 10.5px);
  line-height: 1.35;
  color: #9d97b0;
}
.ht-perks li::before { content: "✓ "; color: #8f6bff; }

.ht-cta-wrap {
  margin-top: 4px;
}
.ht-cta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #f6f4fb;
  font-size: clamp(9.5px, 1.25vw, 11px);
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  transition: all 0.2s ease;
}
.ht-ticket:hover .ht-cta {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.25);
  box-shadow: none;
  transform: translateX(2px);
}

.ht-stub {
  position: relative; z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-left: 1.5px dashed rgba(200, 190, 230, .35);
  transform: translateZ(20px);
  padding: 16px 4px;
  overflow: hidden;
}
.ht-stub span {
  writing-mode: vertical-rl;
  font-family: 'JetBrains Mono', ui-monospace, Menlo, Consolas, monospace;
  font-size: clamp(26px, 5.5vw, 42px);
  font-weight: 700;
  letter-spacing: .06em;
  color: #dcd8e8;
  white-space: nowrap;
  text-align: center;
}
.ht-stub.is-long span {
  font-size: clamp(14px, 2.5vw, 20px);
  letter-spacing: .15em;
  text-transform: uppercase;
  color: #d4cee4;
}

/* Holographic foil */
.ht-foil {
  position: absolute; inset: 0; z-index: 2;
  pointer-events: none;
  background:
    linear-gradient(115deg,
      transparent 15%,
      rgba(0, 255, 210, .35) 30%,
      rgba(255, 60, 200, .35) 45%,
      rgba(120, 90, 255, .4) 60%,
      rgba(255, 230, 120, .3) 72%,
      transparent 85%);
  background-size: 250% 250%;
  background-position: var(--foil) 50%;
  mix-blend-mode: color-dodge;
  opacity: calc(var(--lit) * .55);
  transition: opacity .3s ease;
}

/* Specular highlight */
.ht-glare {
  position: absolute; inset: 0; z-index: 3;
  pointer-events: none;
  background: radial-gradient(circle at var(--gx) var(--gy),
    rgba(255, 255, 255, .38), rgba(255, 255, 255, .08) 30%, transparent 55%);
  mix-blend-mode: overlay;
  opacity: var(--lit);
  transition: opacity .3s ease;
}

.ht-hint {
  margin: 0;
  max-width: 60ch;
  text-align: center;
  font-family: 'JetBrains Mono', ui-monospace, Menlo, Consolas, monospace;
  font-size: 12px;
  color: #7d7890;
}

@media (max-width: 560px) {
  .ht-stage { --stub: 64px; }
  .ht-ticket { aspect-ratio: auto; min-height: 340px; }
  .ht-main { padding: 18px 16px; }
  .ht-stub span { font-size: 18px; }
  .ht-stub.is-long span { font-size: 11px; letter-spacing: .1em; }
}

@media (prefers-reduced-motion: reduce) {
  .ht-tilt { transform: none !important; transition: none; }
}
`;