import { useState } from 'react';
import { Bot, Boxes, Calendar, Clock, Code2, Cpu, Gamepad2, Layers, MapPin, PenTool, Sparkles } from 'lucide-react';
import { OFFICIAL_PARALLAX_PATH } from './ParallaxIdCard.jsx';
import { publicApi } from '../lib/api.js';
import './EventGeneratedPoster.css';

function hashString(str, seed = 0x811c9dc5) {
  let h = seed >>> 0;
  for (let i = 0; i < str.length; i += 1) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  h ^= h >>> 16;
  h = Math.imul(h, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return h >>> 0;
}

function posterSeedKey(event) {
  return String(event?.slug || event?.title || event?.eventTitle || 'parallax')
    .trim()
    .toLowerCase();
}

// 48+ curated-harmony palettes generated via golden-angle hue stepping across
// both light editorial kraft/paper and deep cosmos/obsidian modes.
function pickPosterPalette(event) {
  const h = hashString(posterSeedKey(event), 0x9e3779b9);
  const slot = h % 48;
  const hue = Math.round((slot * 137.508) % 360);
  const discHue = (hue + 28) % 360;
  const isDark = slot % 3 === 1;

  if (isDark) {
    return {
      bg1: `hsl(${hue}, 42%, 15%)`,
      bg2: `hsl(${hue}, 44%, 11%)`,
      bg3: `hsl(${hue}, 48%, 7%)`,
      ink: `hsl(${discHue}, 76%, 74%)`,
      flap1: `hsl(${hue}, 76%, 44%)`,
      flap2: `hsl(${hue}, 74%, 24%)`,
      accent: `hsl(${discHue}, 82%, 68%)`,
      title: '#f8fafc',
      titleShadow: `hsl(${hue}, 55%, 5%)`,
      strip: `hsl(${hue}, 50%, 6%)`,
      footer: `hsl(${hue}, 72%, 34%)`,
      disc1: `hsl(${discHue}, 88%, 74%)`,
      disc2: `hsl(${discHue}, 82%, 52%)`,
      pillBg: `hsla(${discHue}, 76%, 74%, 0.14)`,
      statHighlight: `hsl(${discHue}, 86%, 74%)`,
    };
  }

  return {
    bg1: `hsl(${hue}, 42%, 82%)`,
    bg2: `hsl(${hue}, 38%, 74%)`,
    bg3: `hsl(${hue}, 36%, 65%)`,
    ink: `hsl(${hue}, 58%, 18%)`,
    flap1: `hsl(${hue}, 74%, 38%)`,
    flap2: `hsl(${hue}, 72%, 22%)`,
    accent: `hsl(${hue}, 74%, 36%)`,
    title: '#fffdf7',
    titleShadow: `hsl(${hue}, 62%, 16%)`,
    strip: `hsl(${hue}, 54%, 17%)`,
    footer: `hsl(${hue}, 72%, 30%)`,
    disc1: `hsl(${discHue}, 86%, 75%)`,
    disc2: `hsl(${discHue}, 80%, 54%)`,
    pillBg: 'rgba(255, 252, 245, 0.42)',
    statHighlight: `hsl(${discHue}, 88%, 74%)`,
  };
}

const POSTER_MOTIFS = [
  // 1. Navigational Compass Rose
  () => (
    <>
      <circle cx="230" cy="133" r="64" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <circle cx="230" cy="133" r="46" fill="none" stroke="var(--egp-ink)" strokeWidth="0.9" strokeOpacity="0.2" strokeDasharray="4 3" />
      <line x1="154" y1="133" x2="306" y2="133" stroke="var(--egp-ink)" strokeWidth="0.8" strokeOpacity="0.2" />
      <line x1="230" y1="57" x2="230" y2="209" stroke="var(--egp-ink)" strokeWidth="0.8" strokeOpacity="0.2" />
      <polygon points="230,78 242,121 285,133 242,145 230,188 218,145 175,133 218,121" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.22" />
    </>
  ),
  // 2. Orbital Gyroscope
  () => (
    <>
      <ellipse cx="230" cy="133" rx="74" ry="28" transform="rotate(-24 230 133)" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <ellipse cx="230" cy="133" rx="74" ry="28" transform="rotate(24 230 133)" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <ellipse cx="230" cy="133" rx="52" ry="52" fill="none" stroke="var(--egp-ink)" strokeWidth="0.85" strokeOpacity="0.18" strokeDasharray="3 4" />
      <circle cx="230" cy="133" r="14" fill="none" stroke="var(--egp-ink)" strokeWidth="1.2" strokeOpacity="0.28" />
      <circle cx="294" cy="105" r="4" fill="var(--egp-ink)" fillOpacity="0.24" />
      <circle cx="166" cy="161" r="4" fill="var(--egp-ink)" fillOpacity="0.24" />
    </>
  ),
  // 3. Hexagonal Lattice
  () => (
    <>
      <polygon points="230,67 287,100 287,166 230,199 173,166 173,100" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <polygon points="230,85 271,109 271,157 230,181 189,157 189,109" fill="none" stroke="var(--egp-ink)" strokeWidth="0.9" strokeOpacity="0.2" strokeDasharray="4 3" />
      <polygon points="230,105 254,119 254,147 230,161 206,147 206,119" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.22" />
      <line x1="230" y1="67" x2="230" y2="199" stroke="var(--egp-ink)" strokeWidth="0.7" strokeOpacity="0.16" />
      <line x1="173" y1="100" x2="287" y2="166" stroke="var(--egp-ink)" strokeWidth="0.7" strokeOpacity="0.16" />
      <line x1="287" y1="100" x2="173" y2="166" stroke="var(--egp-ink)" strokeWidth="0.7" strokeOpacity="0.16" />
    </>
  ),
  // 4. PCB Circuit Traces
  () => (
    <>
      <path d="M145 90 H195 L215 110 H265 L285 90 H325" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <path d="M145 133 H180 L200 153 H270 L290 133 H335" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <path d="M160 176 H210 L230 156 H280 L300 176 H340" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.2" />
      <circle cx="195" cy="90" r="3.5" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.28" />
      <circle cx="285" cy="90" r="3.5" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.28" />
      <circle cx="200" cy="153" r="3.5" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.28" />
      <circle cx="290" cy="133" r="3.5" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.28" />
      <rect x="218" y="121" width="24" height="24" rx="3" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
    </>
  ),
  // 5. Telemetry Radar Sweep
  () => (
    <>
      <circle cx="230" cy="133" r="66" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.22" />
      <circle cx="230" cy="133" r="44" fill="none" stroke="var(--egp-ink)" strokeWidth="0.9" strokeOpacity="0.2" strokeDasharray="3 3" />
      <circle cx="230" cy="133" r="22" fill="none" stroke="var(--egp-ink)" strokeWidth="0.9" strokeOpacity="0.2" />
      <path d="M230 133 L276 87 A66 66 0 0 1 296 133 Z" fill="var(--egp-ink)" fillOpacity="0.08" />
      <line x1="230" y1="62" x2="230" y2="204" stroke="var(--egp-ink)" strokeWidth="0.7" strokeOpacity="0.16" />
      <line x1="159" y1="133" x2="301" y2="133" stroke="var(--egp-ink)" strokeWidth="0.7" strokeOpacity="0.16" />
      <circle cx="268" cy="112" r="3" fill="var(--egp-ink)" fillOpacity="0.3" />
    </>
  ),
  // 6. Isometric Cube Wireframe
  () => (
    <>
      <polygon points="230,72 284,102 284,164 230,194 176,164 176,102" fill="none" stroke="var(--egp-ink)" strokeWidth="1.2" strokeOpacity="0.24" />
      <polyline points="176,102 230,133 284,102" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <line x1="230" y1="133" x2="230" y2="194" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <polygon points="230,96 262,114 262,152 230,170 198,152 198,114" fill="none" stroke="var(--egp-ink)" strokeWidth="0.85" strokeOpacity="0.18" strokeDasharray="3 3" />
    </>
  ),
  // 7. Nested Prism Diamonds
  () => (
    <>
      <rect x="184" y="87" width="92" height="92" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.22" />
      <rect x="184" y="87" width="92" height="92" transform="rotate(45 230 133)" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <rect x="204" y="107" width="52" height="52" transform="rotate(22.5 230 133)" fill="none" stroke="var(--egp-ink)" strokeWidth="0.9" strokeOpacity="0.2" strokeDasharray="3 3" />
      <circle cx="230" cy="133" r="10" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.24" />
    </>
  ),
  // 8. Harmonic Signal Waveforms
  () => (
    <>
      <line x1="145" y1="133" x2="315" y2="133" stroke="var(--egp-ink)" strokeWidth="0.8" strokeOpacity="0.18" strokeDasharray="3 3" />
      <path d="M145 133 Q166 83 187 133 T230 133 T273 133 T315 133" fill="none" stroke="var(--egp-ink)" strokeWidth="1.2" strokeOpacity="0.25" />
      <path d="M145 133 Q166 168 187 133 T230 133 T273 133 T315 133" fill="none" stroke="var(--egp-ink)" strokeWidth="0.9" strokeOpacity="0.2" />
      <path d="M145 133 Q156 105 167 133 T189 133 T211 133 T233 133 T255 133 T277 133 T299 133" fill="none" stroke="var(--egp-ink)" strokeWidth="0.7" strokeOpacity="0.16" />
    </>
  ),
  // 9. Precision Gear Rings
  () => (
    <>
      <circle cx="215" cy="128" r="40" fill="none" stroke="var(--egp-ink)" strokeWidth="4" strokeOpacity="0.16" strokeDasharray="6 5" />
      <circle cx="215" cy="128" r="28" fill="none" stroke="var(--egp-ink)" strokeWidth="1.1" strokeOpacity="0.24" />
      <circle cx="215" cy="128" r="10" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.24" />
      <circle cx="268" cy="158" r="24" fill="none" stroke="var(--egp-ink)" strokeWidth="3.5" strokeOpacity="0.16" strokeDasharray="5 4" />
      <circle cx="268" cy="158" r="16" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.24" />
      <circle cx="268" cy="158" r="5" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.24" />
    </>
  ),
  // 10. Golden Ratio Spiral Grid
  () => (
    <>
      <rect x="166" y="83" width="128" height="100" fill="none" stroke="var(--egp-ink)" strokeWidth="1" strokeOpacity="0.22" />
      <line x1="245" y1="83" x2="245" y2="183" stroke="var(--egp-ink)" strokeWidth="0.85" strokeOpacity="0.2" />
      <line x1="245" y1="133" x2="294" y2="133" stroke="var(--egp-ink)" strokeWidth="0.85" strokeOpacity="0.2" />
      <path d="M166 183 A79 79 0 0 1 245 104 A49 49 0 0 1 294 153 A30 30 0 0 1 264 183 A19 19 0 0 1 245 164" fill="none" stroke="var(--egp-ink)" strokeWidth="1.2" strokeOpacity="0.26" />
    </>
  ),
];

function pickPosterMotif(event) {
  return POSTER_MOTIFS[hashString(posterSeedKey(event), 3735928559) % POSTER_MOTIFS.length];
}

function PosterIcon({ iconId, category }) {
  const [failed, setFailed] = useState(false);
  const cat = String(category || '').toLowerCase();

  if (iconId && !failed) {
    return (
      <img
        src={publicApi.iconUrl(iconId)}
        alt=""
        className="egp-big-icon-img"
        onError={() => setFailed(true)}
      />
    );
  }
  if (cat.includes('robot')) return <Bot size={54} strokeWidth={1.7} />;
  if (cat.includes('electr')) return <Cpu size={54} strokeWidth={1.7} />;
  if (cat.includes('design')) return <PenTool size={54} strokeWidth={1.7} />;
  if (cat.includes('comput') || cat.includes('code')) return <Code2 size={54} strokeWidth={1.7} />;
  if (cat.includes('game') || cat.includes('carrom') || cat.includes('fun')) return <Gamepad2 size={54} strokeWidth={1.7} />;
  if (cat.includes('engin')) return <Boxes size={54} strokeWidth={1.7} />;
  if (cat.includes('ai')) return <Sparkles size={54} strokeWidth={1.7} />;
  return <Layers size={54} strokeWidth={1.7} />;
}

const baseUrl = import.meta.env.BASE_URL || '/';
const ISTE_LOGO = `${baseUrl}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/Iste_logo.png`;
const NSSCE_LOGO = `${baseUrl}images/nssce-logo-white.png`;

function formatPosterDate(raw) {
  if (!raw) return { day: '08', rest: 'JAN 2027', time: 'TBA' };
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return { day: '08', rest: 'JAN 2027', time: 'TBA' };
  const day = String(d.getDate()).padStart(2, '0');
  const month = d.toLocaleString('en-IN', { month: 'short' }).toUpperCase();
  const year = d.getFullYear();
  const time = d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }).toUpperCase();
  return { day, rest: `${month} ${year}`, time };
}

function formatPosterFee(event) {
  const paise =
    event?.addonPricePaise ??
    event?.baseValuePaise ??
    event?.feePaise ??
    0;
  if (event?.includedEligible && Number(paise) === 0) return 'INCLUDED';
  if (!Number(paise)) return 'FREE';
  return `₹${Math.round(Number(paise) / 100)}`;
}

export function EventGeneratedPoster({ event = {} }) {
  const title = event.title || event.eventTitle || 'Convention Event';
  const categoryLabel =
    event.categoryName ||
    event.category ||
    (event.format === 'team' || event.teamMode === 'team' ? 'TEAM EVENT' : 'PRE EVENT');
  const { day, rest, time } = formatPosterDate(event.startsAt || event.eventStartsAt);
  const feeText = formatPosterFee(event);
  const venue = event.venueRoom || event.venue || 'NSSCE';
  const isTeam = event.format === 'team' || event.teamMode === 'team';
  const pal = pickPosterPalette(event);
  const Motif = pickPosterMotif(event);

  return (
    <div
      className="egp-root"
      aria-hidden="true"
      style={{
        '--egp-bg1': pal.bg1,
        '--egp-bg2': pal.bg2,
        '--egp-bg3': pal.bg3,
        '--egp-ink': pal.ink,
        '--egp-flap1': pal.flap1,
        '--egp-flap2': pal.flap2,
        '--egp-accent': pal.accent,
        '--egp-title': pal.title,
        '--egp-title-shadow': pal.titleShadow,
        '--egp-strip': pal.strip,
        '--egp-footer': pal.footer,
        '--egp-disc1': pal.disc1,
        '--egp-disc2': pal.disc2,
        '--egp-pill-bg': pal.pillBg,
        '--egp-stat-hi': pal.statHighlight,
      }}
    >
      <div className="egp-edge-credit" aria-hidden="true">AUTO DESIGNED BY MIDHUN K M</div>
      {/* Generic blueprint / architectural background frame */}
      <svg className="egp-bg-svg" viewBox="0 0 400 266" preserveAspectRatio="none">
        {/* Outer blueprint border & corner target arcs */}
        <rect x="16" y="14" width="368" height="238" fill="none" stroke="var(--egp-ink)" strokeWidth="1.4" strokeOpacity="0.45" />
        <rect x="22" y="20" width="356" height="226" fill="none" stroke="var(--egp-ink)" strokeWidth="0.7" strokeOpacity="0.25" />
        <circle cx="16" cy="14" r="14" fill="none" stroke="var(--egp-ink)" strokeWidth="1.2" strokeOpacity="0.35" />
        <circle cx="384" cy="14" r="14" fill="none" stroke="var(--egp-ink)" strokeWidth="1.2" strokeOpacity="0.35" />
        <circle cx="16" cy="252" r="14" fill="none" stroke="var(--egp-ink)" strokeWidth="1.2" strokeOpacity="0.35" />
        <circle cx="384" cy="252" r="14" fill="none" stroke="var(--egp-ink)" strokeWidth="1.2" strokeOpacity="0.35" />

        {/* Algorithmic geometric motif (1 of 10) */}
        <Motif />

        {/* Top & bottom squiggle accents */}
        <path d="M148 40 q5 -5 10 0 t10 0 t10 0 t10 0 t10 0 t10 0 t10 0 t10 0" fill="none" stroke="var(--egp-accent)" strokeWidth="2.2" strokeLinecap="round" />
        <path d="M148 210 q5 -5 10 0 t10 0 t10 0 t10 0 t10 0 t10 0 t10 0 t10 0" fill="none" stroke="var(--egp-accent)" strokeWidth="2.2" strokeLinecap="round" />
      </svg>

      {/* Top-left folded crimson corner flap with NSSCE + ISTE logos */}
      <div className="egp-corner-flap">
        <div className="egp-corner-logos">
          <img src={NSSCE_LOGO} alt="" />
          <img src={ISTE_LOGO} alt="" />
        </div>
      </div>

      {/* Top-center organizer tag & top-right Parallax vector */}
      <div className="egp-top-bar">
        <span className="egp-org-kicker">ISTE SB NSSCE</span>
        <svg className="egp-px-logo" viewBox="0 0 3161 969" aria-label="Parallax">
          <path fill="currentColor" fillRule="evenodd" d={OFFICIAL_PARALLAX_PATH} transform="translate(-464 -166)" />
        </svg>
      </div>

      {/* Main focal area: Left EventIcon medallion + Right display typography */}
      <div className="egp-hero">
        <div className="egp-medallion-wrap">
          <PosterIcon
            iconId={event.iconId}
            category={event.categorySlug || event.categoryName || event.category}
          />
        </div>

        <div className="egp-copy">
          <span className="egp-pill">
            <i>&bull;</i> {String(categoryLabel).toUpperCase()}
          </span>
          <h4 className="egp-title">{title}</h4>
          <span className="egp-sub">
            {isTeam ? 'TEAM ENTRY' : 'SOLO ENTRY'} &middot; {venue}
          </span>
        </div>
      </div>

      {/* Bottom burgundy info strip */}
      <div className="egp-info-strip">
        <div className="egp-stat">
          <Calendar size={12} strokeWidth={2.2} />
          <b>{day}</b>
          <span>{rest}</span>
        </div>
        <div className="egp-stat">
          <Clock size={12} strokeWidth={2.2} />
          <b>{time}</b>
        </div>
        <div className="egp-stat">
          <b>{feeText}</b>
          <span>{feeText === 'INCLUDED' || feeText === 'FREE' ? 'PASS' : 'REG FEE'}</span>
        </div>
        <div className="egp-stat egp-stat-venue">
          <MapPin size={11} strokeWidth={2.2} />
          <span>{venue}</span>
        </div>
      </div>

      {/* Bottom crimson footer */}
      <div className="egp-footer-strip">
        <span>PARALLAX &apos;27</span>
        <span>ISTE CHAPTER NSSCE</span>
      </div>
    </div>
  );
}
