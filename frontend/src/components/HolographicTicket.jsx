import { useRef } from "react";
import { Link } from "react-router-dom";

/**
 * HolographicTicket
 * 3D-tilt convention ticket with holographic foil + specular highlight.
 * Dependencies: React only (styles are injected via <style>, no Tailwind needed).
 */
export default function HolographicTicket({
  eyebrow = "Two days of engineering. One all-pass.",
  name = "ALL ACCESS PASS",
  venue = "Full floor clearance, Competition & Workshop with zero gated tracks or hidden fees.",
  dates = "DECMBER XX_XX, 2026",
  city = "ISTE",
  stubText = "₹500",
  price = "GET NOW",
  perks = [
    "Lunch on both days",
    "Upto 3 events",
    "Unrestricted access to all exhibitions",
  ],
}) {
  const tiltRef = useRef(null);

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
          <article className="ht-ticket" aria-label={`${stubText} pass for ${name}`}>
            <div className="ht-streak" aria-hidden="true" />
            <div className="ht-grain" aria-hidden="true" />

            <div className="ht-main">
              <p className="ht-eyebrow">{eyebrow}</p>

              <h2 className="ht-name">{name}</h2>

              <div className="ht-foot">
                <p className="ht-venue">
                  {venue} • {dates} • {city}
                </p>
                <ul className="ht-perks">
                  {perks.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                  <br />
                  <br />
                  <li className="ht-price">{price}</li>
                </ul>
              </div>
            </div>

            <div className="ht-stub" aria-hidden="true">
              <span>{stubText}</span>
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
  aspect-ratio: 760 / 420;
  min-height: 300px;
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
  padding: clamp(20px, 5%, 56px);
  font-family: 'JetBrains Mono', ui-monospace, Menlo, Consolas, monospace;
  transform: translateZ(30px);
}

.ht-eyebrow {
  margin: 0;
  font-size: clamp(10px, 1.6vw, 13px);
  letter-spacing: .04em;
  color: #a8a2b8;
}

.ht-name {
  margin: 0;
  font-family: 'Archivo Black', 'Segoe UI', system-ui, sans-serif;
  font-weight: 900;
  font-size: clamp(34px, 8vw, 66px);
  line-height: .98;
  letter-spacing: -.01em;
  text-transform: uppercase;
  max-width: 9ch;
}

.ht-foot { display: grid; gap: 10px; }

.ht-venue {
  margin: 0;
  font-size: clamp(10px, 1.6vw, 13px);
  font-weight: 700;
  letter-spacing: .02em;
  color: #ddd9ea;
}

.ht-perks {
  display: flex; flex-wrap: wrap; gap: 6px 14px;
  margin: 0; padding: 0; list-style: none;
  font-size: clamp(9px, 1.4vw, 11px);
  color: #9d97b0;
}
.ht-perks li::before { content: "✓ "; color: #8f6bff; }
.ht-perks .ht-price { color: #f6f4fb; font-weight: 700; }
.ht-perks .ht-price::before { content: ""; }

.ht-stub {
  position: relative; z-index: 1;
  display: grid; place-items: center;
  border-left: 1.5px dashed rgba(200, 190, 230, .35);
  transform: translateZ(20px);
}
.ht-stub span {
  writing-mode: vertical-rl;
  font-family: 'JetBrains Mono', ui-monospace, Menlo, Consolas, monospace;
  font-size: clamp(34px, 7.5vw, 62px);
  font-weight: 700;
  letter-spacing: .06em;
  color: #dcd8e8;
  white-space: nowrap;
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
  .ht-stage { --stub: 72px; }
  .ht-ticket { aspect-ratio: auto; min-height: 340px; }
}

@media (prefers-reduced-motion: reduce) {
  .ht-tilt { transform: none !important; transition: none; }
}
`;