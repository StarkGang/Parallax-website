import { useState, useEffect, useRef, useMemo } from 'react';
import { BrandedQr } from './BrandedQr.jsx';
import { logisticsLine } from '../lib/attendee.js';
import { fallbackImageUrl } from '../lib/imageUrl.js';
import { normalizeYear } from './AttendeeInputs.jsx';
import './ParallaxIdCard.css';

export const OFFICIAL_PARALLAX_PATH =
  "M3625,990H3490L3330,819,3173,988H3046l220-238L3033,506h132l165,173,109-115h126L3396,747ZM2498,821c31.63-184.255,209-186,209-186h155c-8.87-55.755-63-62-63-62l-83-82h99c146.13,13.745,148,156,148,156l1,330H2627C2492.62,953.245,2498,821,2498,821ZM2350,272l131,79v784l-131-88V272Zm-200-24,131,79v784l-131-88V248ZM1655,821c31.62-184.255,209-186,209-186h155c-8.88-55.755-63-62-63-62l-83-82h99c146.12,13.745,148,156,148,156l1,330H1784C1649.63,953.245,1655,821,1655,821Zm-79-183-1,230L1429,990V444l68,38,48,45c51-53.753,144-46,144-46v98C1592.5,553.747,1576,638,1576,638ZM923,821c31.625-184.255,209-186,209-186h155c-8.87-55.755-63-62-63-62l-83-82h99c146.13,13.745,148,156,148,156l1,330H1052C917.625,953.245,923,821,923,821ZM779,712H630V904l-166,98,2-300,86-44c7.792-7.755,76-67,76-67H789c87.292-22.755,73-109,73-109,11.292-82.255-385-239-385-239V166L833,301c143.125,46.453,147,191,147,191C976.125,697.453,779,712,779,712Zm508,17V872H1105s-67.87-3.255-71-65c0,0,2.62-54.255,63-73Zm732,0V872H1837s-67.87-3.255-71-65c0,0,2.62-54.255,63-73Zm843,0V872H2680s-67.88-3.255-71-65c0,0,2.62-54.255,63-73Z";

/* Curated harmonious tone-on-tone triads */
export const PALETTES = [
  { name: 'Parallax Indigo', dark: '#0e1533', mid: '#4f46e5', light: '#7dd3fc' },
  { name: 'Cosmic Indigo', dark: '#14124a', mid: '#5a4bff', light: '#ff9a62' },
  { name: 'Deep Royal', dark: '#0b1d3a', mid: '#2f6bff', light: '#ffd23f' },
  { name: 'Velvet Purple', dark: '#2a0b3a', mid: '#a23df2', light: '#ff7ab8' },
  { name: 'Forest Amber', dark: '#0f2e22', mid: '#248255', light: '#ff9f2e' },
  { name: 'Carbon Ember', dark: '#15171c', mid: '#ff5a36', light: '#ffc24b' },
  { name: 'Crimson Rose', dark: '#3b0d18', mid: '#d92c55', light: '#ffafc0' },
  { name: 'Ocean Cyan', dark: '#062536', mid: '#00a8cc', light: '#5ef8d8' },
];

export const KINDS = ['waves', 'arches', 'petals', 'chevrons', 'orbs', 'tiles'];

/* Role to tone mapping: standard 'waves' geometry, role-specific tone palette */
export const ROLE_CONFIGS = {
  delegate: {
    paletteIdx: 0,
    roleTitle: 'College Student',
    tierPill: 'Convention Delegate',
    paletteName: 'Parallax Indigo',
    // Deep navy + indigo + sky: the attendee tier now sits in the same family
    // as the portal chrome instead of a separate green island.
    dark: '#0e1533',
    mid: '#4f46e5',
    light: '#7dd3fc',
    label: 'Convention Delegate',
  },
  volunteer: {
    paletteIdx: 5,
    roleTitle: 'Operations Crew',
    tierPill: 'Operations Staff',
    paletteName: 'Carbon Ember',
    dark: '#15171c',
    mid: '#ff5a36',
    light: '#ffc24b',
    label: 'Operations Crew',
  },
  coordinator: {
    paletteIdx: 1,
    roleTitle: 'Events Coordinator',
    tierPill: 'Lead Coordinator',
    paletteName: 'Cosmic Indigo',
    dark: '#14124a',
    mid: '#5a4bff',
    light: '#ff9a62',
    label: 'Event Coordinator',
  },
  organizer: {
    paletteIdx: 3,
    roleTitle: 'Organizing Committee',
    tierPill: 'Core Committee',
    paletteName: 'Velvet Purple',
    dark: '#2a0b3a',
    mid: '#a23df2',
    light: '#ff7ab8',
    label: 'Organizing Committee',
  },
  speaker: {
    paletteIdx: 2,
    roleTitle: 'Keynote Speaker',
    tierPill: 'Distinguished Guest',
    paletteName: 'Deep Royal',
    dark: '#0b1d3a',
    mid: '#2f6bff',
    light: '#ffd23f',
    label: 'Keynote Speaker',
  },
  faculty: {
    paletteIdx: 4,
    roleTitle: 'Faculty Advisor',
    tierPill: 'Chapter Leadership',
    paletteName: 'Forest Amber',
    dark: '#0f2e22',
    mid: '#248255',
    light: '#ff9f2e',
    label: 'Faculty / Patron',
  },
  sponsor: {
    paletteIdx: 6,
    roleTitle: 'Sponsor / Partner',
    tierPill: 'Title Partner',
    paletteName: 'Crimson Rose',
    dark: '#3b0d18',
    mid: '#d92c55',
    light: '#ffafc0',
    label: 'Sponsor / Partner',
  },
  media: {
    paletteIdx: 7,
    roleTitle: 'Press / Media',
    tierPill: 'Press Credential',
    paletteName: 'Ocean Cyan',
    dark: '#062536',
    mid: '#00a8cc',
    light: '#5ef8d8',
    label: 'Press / Media',
  },
};

/* Presets for the admin studio.
   One demo card (Midhun) proves the design, and every other entry is a role
   template with an empty name so the operator types the real holder's name
   instead of inheriting somebody else's. Roles mirror the ones published on the
   team page, plus generic guest/partner/attendee credentials. */
const NSS_COLLEGE = 'NSS College of Engineering, Palakkad';

const rolePreset = (key, group, label, role, tier, roleKey, extra = {}) => {
  const paletteIdx = ROLE_CONFIGS[roleKey] ? ROLE_CONFIGS[roleKey].paletteIdx : 0;
  const branch = extra.branch || 'Core Organising Team · ISTE SC NSSCE';
  return {
    key,
    group,
    label,
    name: '',
    role,
    tier,
    roleKey,
    paletteIdx,
    college: NSS_COLLEGE,
    branch,
    sub: `${branch} · ${NSS_COLLEGE}`,
    id: '',
    photo: '',
    kind: 'waves',
    ...extra,
  };
};

export const ADMIN_PRESETS = [
  {
    key: 'midhun',
    group: 'Sample',
    label: 'Midhun · Demo Card',
    name: 'MIDHUN K M',
    role: 'College Student',
    college: NSS_COLLEGE,
    branch: 'Computer Science & Engineering · Yr 2',
    sub: 'Computer Science · NSS College of Engineering',
    tier: 'Convention Delegate',
    id: 'PX-27-EA130B',
    photo: 'images/team/Midhunkm.jpg',
    roleKey: 'delegate',
    paletteIdx: 0,
    kind: 'waves',
  },

  /* Leadership */
  rolePreset('chairperson', 'Leadership', 'Chairperson', 'Chairperson', 'Core Committee', 'organizer'),
  rolePreset('secretary', 'Leadership', 'Secretary', 'Secretary', 'Core Committee', 'organizer'),
  rolePreset('faculty-chair', 'Leadership', 'Faculty Chairperson', 'Faculty Chairperson', 'Chapter Leadership', 'faculty', {
    branch: 'Faculty · ISTE Chapter NSSCE',
  }),
  rolePreset('faculty-secretary', 'Leadership', 'Faculty Secretary', 'Faculty Secretary', 'Chapter Leadership', 'faculty', {
    branch: 'Faculty · ISTE Chapter NSSCE',
  }),

  /* Core team, matching the published team page */
  rolePreset('events', 'Core Team', 'Events Coordinator', 'Events Coordinator', 'Core Team', 'coordinator'),
  rolePreset('design', 'Core Team', 'Design Coordinator', 'Design Coordinator', 'Core Team', 'coordinator'),
  rolePreset('publicity', 'Core Team', 'Publicity Coordinator', 'Publicity Coordinator', 'Core Team', 'coordinator'),
  rolePreset('finance', 'Core Team', 'Finance Coordinator', 'Finance Coordinator', 'Core Team', 'coordinator'),
  rolePreset('technical', 'Core Team', 'Technical Coordinator', 'Technical Coordinator', 'Core Team', 'coordinator'),
  rolePreset('web', 'Core Team', 'Web Team', 'Web & Development', 'Core Team', 'coordinator', {
    branch: 'Web & Systems · ISTE SC NSSCE',
  }),
  rolePreset('ops', 'Core Team', 'Operations Crew', 'Operations Crew', 'Operations Staff', 'volunteer', {
    branch: 'Stage & Logistics · ISTE SC NSSCE',
  }),

  /* Guests and partners */
  rolePreset('speaker', 'Guests & Partners', 'Keynote Speaker', 'Keynote Speaker', 'Distinguished Guest', 'speaker', {
    branch: 'Distinguished Guest · Parallax 2027',
  }),
  rolePreset('sponsor', 'Guests & Partners', 'Sponsor / Partner', 'Sponsor / Partner', 'Title Partner', 'sponsor', {
    branch: 'Partner Organisation',
  }),
  rolePreset('media', 'Guests & Partners', 'Press / Media', 'Press / Media', 'Press Credential', 'media', {
    branch: 'Press & Media',
  }),

  /* Attendees */
  rolePreset('delegate', 'Attendees', 'College Student', 'College Student', 'Convention Delegate', 'delegate', {
    branch: 'Computer Science & Engineering · Yr 2',
  }),
];

/* Color conversion and smart harmonious tone generator */
export function hexToHsl(hex) {
  let c = hex.replace('#', '');
  if (c.length === 3) c = c.split('').map((x) => x + x).join('');
  const num = parseInt(c, 16);
  const r = ((num >> 16) & 255) / 255;
  const g = ((num >> 8) & 255) / 255;
  const b = (num & 255) / 255;

  const max = Math.max(r, g, b),
    min = Math.min(r, g, b);
  let h = 0,
    s = 0,
    l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0);
        break;
      case g:
        h = (b - r) / d + 2;
        break;
      case b:
        h = (r - g) / d + 4;
        break;
    }
    h /= 6;
  }
  return [Math.round(h * 360), Math.round(s * 100), Math.round(l * 100)];
}

export function hslToHex(h, s, l) {
  h = ((h % 360) + 360) % 360;
  s = Math.max(0, Math.min(100, s)) / 100;
  l = Math.max(0, Math.min(100, l)) / 100;

  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  let r = 0,
    g = 0,
    b = 0;

  if (h >= 0 && h < 60) {
    r = c;
    g = x;
    b = 0;
  } else if (h >= 60 && h < 120) {
    r = x;
    g = c;
    b = 0;
  } else if (h >= 120 && h < 180) {
    r = 0;
    g = c;
    b = x;
  } else if (h >= 180 && h < 240) {
    r = 0;
    g = x;
    b = c;
  } else if (h >= 240 && h < 300) {
    r = x;
    g = 0;
    b = c;
  } else {
    r = c;
    g = 0;
    b = x;
  }

  const toHex = (val) => Math.round((val + m) * 255).toString(16).padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

export function generateToneTriad(baseHex) {
  try {
    const [h, s, l] = hexToHsl(baseHex);
    // midtone: vibrant and saturated signature
    const mid = hslToHex(h, Math.max(70, s), Math.min(55, Math.max(42, l)));
    // dark: deep rich contrast for text and backing
    const dark = hslToHex(h, Math.min(95, Math.max(65, s + 10)), 12);
    // light: luminous accent for pills and highlights
    const light = hslToHex((h + 10) % 360, Math.min(100, Math.max(80, s + 15)), 72);
    return { name: `Custom (${baseHex})`, dark, mid, light };
  } catch {
    return { name: 'Custom Palette', dark: '#0a3d42', mid: '#2bb673', light: '#b8f23d' };
  }
}

const mix = (a, b, t) => {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const A = p(a),
    B = p(b);
  return (
    '#' +
    A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, '0')).join('')
  );
};

function shapes(p, side) {
  return side === 'f'
    ? { bg: p.mid, a: p.dark, b: mix(p.mid, p.dark, 0.5), c: p.light, d: mix(p.mid, p.light, 0.55) }
    : { bg: p.dark, a: p.mid, b: mix(p.dark, p.mid, 0.55), c: p.light, d: mix(p.dark, p.light, 0.42) };
}

function rng(s) {
  return () => {
    s |= 0;
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function generateArtLayers(kind, W, H, p, seed) {
  const r = rng(seed),
    R = (a, b) => a + r() * (b - a),
    { a, b, c, d } = p;
  let L0 = '',
    L1 = '',
    L2 = '';

  const arch = (x, w, h, f) => {
    h = Math.max(h, w / 2 + 2);
    return `<path d="M${x},${H}V${H - h + w / 2}A${w / 2},${w / 2} 0 0 1 ${x + w},${H - h + w / 2}V${H}Z" fill="${f}"/>`;
  };
  const leaf = (cx, cy, w, h, rot, f) =>
    `<path transform="rotate(${rot} ${cx} ${cy})" d="M${cx},${cy + h / 2}Q${cx + w},${cy} ${cx},${cy - h / 2}Q${cx - w},${cy} ${cx},${cy + h / 2}Z" fill="${f}"/>`;
  const wave = (base, amp, f, ph, fill) => {
    let s = `M0,${H}L0,${base}`;
    for (let x = 0; x <= W; x += 2)
      s += `L${x},${(base + Math.sin((x / W) * 6.283 * f + ph) * amp).toFixed(1)}`;
    return `<path d="${s}L${W},${H}Z" fill="${fill}"/>`;
  };

  if (kind === 'arches') {
    for (let i = 0; i < 3; i++) L0 += arch((i * W) / 2.5 - 12 + R(0, 8), R(46, 56), H * R(0.8, 1.02), i % 2 ? b : a);
    for (let i = 0; i < 3; i++) L1 += arch(R(-6, W - 26), R(26, 36), H * R(0.45, 0.78), i % 2 ? d : c);
    for (let i = 0; i < 3; i++) L2 += arch(R(0, W - 14), R(11, 17), H * R(0.2, 0.42), i % 2 ? c : d);
  } else if (kind === 'petals') {
    for (let i = 0; i < 4; i++) L0 += leaf(R(8, W - 8), H * 0.72, R(46, 58), H * R(1, 1.25), R(-28, 28), i % 2 ? b : a);
    for (let i = 0; i < 4; i++) L1 += leaf(R(8, W - 8), H * 0.82, R(24, 34), H * R(0.55, 0.8), R(-35, 35), i % 2 ? d : c);
    for (let i = 0; i < 5; i++) L2 += leaf(R(4, W - 4), H * R(0.7, 0.95), R(11, 16), H * R(0.25, 0.4), R(-40, 40), i % 2 ? c : d);
  } else if (kind === 'chevrons') {
    const chev = (y, ax, th, col) =>
      `<polyline points="-8,${y + 26} ${ax},${y - 14} ${W + 8},${y + 26}" fill="none" stroke="${col}" stroke-width="${th}" stroke-linejoin="round"/>`;
    for (let k = 0; k < 6; k++) L0 += chev(H * 0.12 + k * H * 0.17, R(40, 60), 13, k % 2 ? b : a);
    for (let k = 0; k < 5; k++) L1 += chev(H * 0.2 + k * H * 0.18 + 4, R(38, 62), 5.5, k % 2 ? d : c);
    for (let k = 0; k < 3; k++) L2 += chev(H * 0.3 + k * H * 0.26, R(35, 65), 1.6, d);
  } else if (kind === 'orbs') {
    for (let i = 0; i < 3; i++) L0 += `<circle cx="${R(0, W)}" cy="${R(H * 0.35, H * 0.95)}" r="${R(W * 0.28, W * 0.44)}" fill="${i % 2 ? b : a}"/>`;
    for (let i = 0; i < 3; i++) L1 += `<circle cx="${R(0, W)}" cy="${R(H * 0.3, H)}" r="${R(W * 0.12, W * 0.2)}" fill="${i % 2 ? d : c}"/>`;
    for (let i = 0; i < 2; i++) L1 += `<circle cx="${R(0, W)}" cy="${R(0, H)}" r="${R(W * 0.18, W * 0.28)}" fill="none" stroke="${d}" stroke-width="1.6"/>`;
    for (let i = 0; i < 7; i++) L2 += `<circle cx="${R(0, W)}" cy="${R(0, H)}" r="${R(1.6, 4)}" fill="${i % 2 ? c : d}"/>`;
  } else if (kind === 'tiles') {
    const n = 3,
      cell = W / n,
      h = cell / 2;
    for (let y = 0; y < Math.ceil(H / cell); y++)
      for (let x = 0; x < n; x++) {
        const x0 = x * cell,
          y0 = y * cell,
          cx = x0 + h,
          cy = y0 + h,
          f = r() < 0.5 ? a : b,
          t = Math.floor(r() * 4),
          rot = `transform="rotate(${90 * Math.floor(r() * 4)} ${cx} ${cy})"`;
        if (t === 0) L0 += `<circle cx="${cx}" cy="${cy}" r="${h}" fill="${f}"/>`;
        else if (t === 1) L0 += `<path ${rot} d="M${x0},${y0}h${cell}a${cell},${cell} 0 0 1 -${cell},${cell}z" fill="${f}"/>`;
        else if (t === 2) L0 += `<path ${rot} d="M${x0},${y0 + cell}a${h},${h} 0 0 1 ${cell},0z" fill="${f}"/>`;
        else
          L0 += `<rect x="${x0}" y="${y0}" width="${cell}" height="${cell}" fill="${f}"/><circle cx="${cx}" cy="${cy}" r="${h * 0.55}" fill="${r() < 0.5 ? c : d}"/>`;
      }
    for (let i = 0; i < 4; i++) L1 += `<circle cx="${R(8, W - 8)}" cy="${R(8, H - 8)}" r="${R(5, 9)}" fill="${i % 2 ? c : d}"/>`;
    for (let i = 0; i < 3; i++) L2 += `<circle cx="${R(0, W)}" cy="${R(0, H)}" r="${R(10, 20)}" fill="none" stroke="${d}" stroke-width="1.4"/>`;
  } else {
    // Standard waves pattern
    for (let i = 0; i < 3; i++) L0 += wave(H * (0.3 + i * 0.2), R(5, 9), R(0.8, 1.6), R(0, 6.28), i % 2 ? b : a);
    for (let i = 0; i < 2; i++) L1 += wave(H * (0.5 + i * 0.22), R(4, 7), R(1, 2), R(0, 6.28), i ? d : c);
    for (let i = 0; i < 3; i++) {
      let s = '';
      const base = H * (0.35 + i * 0.2),
        f = R(1, 2),
        ph = R(0, 6.28);
      for (let x = 0; x <= W; x += 2) s += (x ? 'L' : 'M') + x + ',' + (base + Math.sin((x / W) * 6.283 * f + ph) * 6).toFixed(1);
      L2 += `<path d="${s}" fill="none" stroke="${d}" stroke-width="1.4"/>`;
    }
  }
  return [L0, L1, L2];
}

function generateBarcode(seed) {
  const r = rng(seed || 42);
  let x = 0,
    rects = [];
  while (x < 198) {
    const w = 1 + Math.floor(r() * 3);
    if (r() > 0.35) {
      rects.push(<rect key={x} x={x} y="0" width={w} height="40" fill="currentColor" />);
    }
    x += w + 1 + Math.floor(r() * 2);
  }
  return rects;
}

export default function ParallaxIdCard({
  user,
  registration,
  edition,
  category,
  photoUrl,
  qrPayload,
  qrPendingLabel = 'Issued after saving',
  roleKey = 'delegate',
  onRoleChange,
  kind = 'waves', // STANDARD DESIGN: waves for all posts
  onKindChange,
  customPalette = null,
  paletteIdx: controlledPaletteIdx,
  onPaletteChange,
  showControls = false,
  customData = null,
  allowPhotoUpload = false,
  onPhotoUploaded,
}) {
  // Determine role config
  const roleConfig = ROLE_CONFIGS[roleKey] || ROLE_CONFIGS.delegate;

  const [internalPaletteIdx, setInternalPaletteIdx] = useState(roleConfig.paletteIdx || 0);
  const [internalKind, setInternalKind] = useState(kind || 'waves');
  const [seed, setSeed] = useState(23);

  // Sync palette when roleKey changes
  useEffect(() => {
    if (ROLE_CONFIGS[roleKey]) {
      setInternalPaletteIdx(ROLE_CONFIGS[roleKey].paletteIdx);
    }
  }, [roleKey]);

  useEffect(() => {
    if (kind) setInternalKind(kind);
  }, [kind]);

  const activePaletteIdx = controlledPaletteIdx !== undefined ? controlledPaletteIdx : internalPaletteIdx;
  const activeKind = kind || internalKind || 'waves';

  const p = useMemo(() => {
    if (customPalette) return customPalette;
    return PALETTES[activePaletteIdx] || PALETTES[0];
  }, [customPalette, activePaletteIdx]);

  const stageRef = useRef(null);

  const spFront = useMemo(() => shapes(p, 'f'), [p]);
  const spBack = useMemo(() => shapes(p, 'b'), [p]);

  const frontLayers = useMemo(() => generateArtLayers(activeKind, 100, 76, spFront, seed), [activeKind, spFront, seed]);
  const backLayers = useMemo(() => generateArtLayers(activeKind, 100, 76, spBack, seed + 17), [activeKind, spBack, seed]);
  const barcodeRects = useMemo(() => generateBarcode(seed), [seed]);

  // 3D Parallax Tilt Effect
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    let tx = 0,
      ty = 0,
      cx = 0,
      cy = 0,
      raf = 0;
    const cards = stage.querySelectorAll('.card');
    const layers = stage.querySelectorAll('.pl-layer');

    const apply = () => {
      cards.forEach((c) => {
        c.style.transform = `perspective(1200px) rotateY(${(cx * 6).toFixed(2)}deg) rotateX(${(-cy * 5).toFixed(2)}deg)`;
      });
      layers.forEach((el) => {
        const d = +el.dataset.d || 0.5;
        el.style.transform = `translate3d(${(-cx * d * 16).toFixed(1)}px, ${(-cy * d * 12).toFixed(1)}px, 0) scale(1.14)`;
      });
    };

    const tick = () => {
      cx += (tx - cx) * 0.08;
      cy += (ty - cy) * 0.08;
      apply();
      if (Math.abs(tx - cx) > 0.002 || Math.abs(ty - cy) > 0.002) {
        raf = requestAnimationFrame(tick);
      } else {
        raf = 0;
      }
    };

    const onPointerMove = (e) => {
      tx = Math.max(-1, Math.min(1, (e.clientX / window.innerWidth - 0.5) * 2));
      ty = Math.max(-1, Math.min(1, (e.clientY / window.innerHeight - 0.5) * 2));
      if (!raf) raf = requestAnimationFrame(tick);
    };

    const onPointerLeave = () => {
      tx = 0;
      ty = 0;
      if (!raf) raf = requestAnimationFrame(tick);
    };

    window.addEventListener('pointermove', onPointerMove);
    document.addEventListener('pointerleave', onPointerLeave);

    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('pointerleave', onPointerLeave);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [frontLayers, backLayers]);

  // Data fields resolution
  const fullName = customData?.name || registration?.fullName || user?.fullName || 'MIDHUN K M';
  const collegeName =
    customData?.college ||
    customData?.collegeName ||
    customData?.institution ||
    (customData?.sub?.includes('·')
      ? customData.sub.split('·')[1].trim()
      : (customData?.sub || registration?.collegeName || user?.collegeName || 'NSS College of Engineering, Palakkad'));
  const branchCourse = customData?.branch
    ? customData.branch
    : (customData?.sub?.includes('·')
        ? customData.sub.split('·')[0].trim()
        : [
            registration?.branch || registration?.course || 'Computer Science & Engineering',
            registration?.yearOfStudy ? normalizeYear(registration.yearOfStudy) : null,
          ]
            .filter(Boolean)
            .join(' · '));

  const roleTitle = customData?.role || roleConfig.roleTitle || 'College Student';
  const tierPill = customData?.tier || (category?.name ? category.name : roleConfig.tierPill);
  const credentialId = customData?.id || registration?.registrationNumber || 'PX-27-EA130B';
  const resolvedPhoto = customData?.photo || photoUrl || (registration?.photoUrl ? registration.photoUrl : null);
  const [photoSrc, setPhotoSrc] = useState(resolvedPhoto);
  const [photoFallbackTried, setPhotoFallbackTried] = useState(false);
  useEffect(() => {
    setPhotoSrc(resolvedPhoto);
    setPhotoFallbackTried(false);
  }, [resolvedPhoto]);
  const isVerified = customData?.isVerified !== undefined ? customData.isVerified : registration?.verificationStatus === 'approved';

  // Gender / meal / bed. Printed on the back so the kitchen and the hostel desk
  // can read a card without a terminal. Hidden when nothing is on record.
  const attendeeLogistics = logisticsLine({
    gender: customData?.gender ?? registration?.gender,
    foodPreference: customData?.foodPreference ?? registration?.foodPreference,
    needsAccommodation: customData?.needsAccommodation ?? registration?.needsAccommodation,
  });

  const baseUrl = import.meta.env.BASE_URL || '/';
  const isteLogo = `${baseUrl}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/Iste_logo.png`;
  const nssceLogo = `${baseUrl}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/NSSCE-Palakkad-Logo.webp`;

  const cardStyle = {
    '--dark': p.dark,
    '--mid': p.mid,
    '--light': p.light,
  };

  // Hand the file over instead of a blob URL: the caller uploads it, so a saved
  // card keeps its photo after the tab closes.
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (onPhotoUploaded) onPhotoUploaded(file);
  };

  return (
    <div className="px-card-root">
      {/* 3D Stage with Front and Back */}
      <div className="stage" ref={stageRef}>
        {/* FRONT */}
        <section className="card front" style={cardStyle} aria-label="Pass front">
          <div className="id-edge-credit" aria-hidden="true">DEVELOPED BY MIDHUN K M</div>
          <div className="pl" style={{ background: spFront.bg }} aria-hidden="true">
            {frontLayers.map((svgContent, idx) => (
              <svg
                key={idx}
                className="pl-layer"
                data-d={[0.3, 0.65, 1.1][idx]}
                viewBox="0 0 100 76"
                preserveAspectRatio="xMidYMid slice"
                dangerouslySetInnerHTML={{ __html: svgContent }}
              />
            ))}
          </div>
          <div className="slot" />
          <label className={`photo ${allowPhotoUpload ? 'is-clickable' : ''}`} title={allowPhotoUpload ? 'Click to change photo' : ''}>
            {photoSrc ? (
              <img
                src={photoSrc}
                alt={fullName}
                referrerPolicy="no-referrer"
                onError={() => {
                  if (!photoFallbackTried) {
                    const fallback = fallbackImageUrl(resolvedPhoto, 480);
                    if (fallback && fallback !== photoSrc) {
                      setPhotoFallbackTried(true);
                      setPhotoSrc(fallback);
                      return;
                    }
                  }
                  setPhotoSrc(null);
                }}
              />
            ) : (
              <svg viewBox="0 0 100 117" aria-hidden="true">
                <circle cx="50" cy="48" r="19" />
                <path d="M8 117c2-30 18-42 42-42s40 12 42 42z" />
              </svg>
            )}
            {allowPhotoUpload && (
              <>
                <span className="photo-hint">Change</span>
                <input type="file" accept="image/*" onChange={handleFileChange} hidden />
              </>
            )}
          </label>
          <div className="panel">
            <div className="name" title={fullName}>{fullName}</div>
            <div className="role">{roleTitle}</div>
            <div className="sub-institution" title={`${branchCourse} · ${collegeName}`}>
              <div className="sub-branch">{branchCourse}</div>
              <div className="sub-college">{collegeName}</div>
            </div>
            <div className="pills">
              <span className="pill">{tierPill}</span>
              <span className="ver">
                <i>&#10003;</i>
                {isVerified ? 'Verified attendee' : 'Attendee pass'}
              </span>
            </div>
            <div className="row2">
              <div>
                <div className="f id">
                  <small>ID number</small>
                  <b>{credentialId}</b>
                </div>
                <div className="f">
                  <small>2-day convention pass</small>
                  <b>8-9 Jan 2027</b>
                </div>
                <div className="f">
                  <small>Venue</small>
                  <b>NSSCE Campus, Palakkad</b>
                </div>
              </div>
              <div className="qrb" aria-label="Check-in QR code">
                {qrPayload ? (
                  <BrandedQr value={qrPayload} title="Parallax entry QR" />
                ) : (
                  // Never draw a made-up payload: a code that no server issued
                  // fails at the desk. Show a placeholder until one exists.
                  <div className="qr-pending">
                    <small>QR</small>
                    <span>{qrPendingLabel}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="sign" aria-label="Digitally signed credential">
              <svg className="sign-seal" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M12 1.8l2.5 1.8 3.1-.2.9 3 2.5 1.9-1.2 2.9 1.2 2.9-2.5 1.9-.9 3-3.1-.2L12 22.2l-2.5-1.9-3.1.2-.9-3L3 15.6l1.2-2.9L3 9.9l2.5-1.9.9-3 3.1.2z"
                  fill="currentColor"
                  opacity="0.16"
                />
                <path
                  d="M8.1 12.2l2.5 2.5 5.3-5.3"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <div>
                <b>Digitally signed</b>
                <span>Scan the QR to verify this credential</span>
              </div>
            </div>
            <div className="foot">
              <div className="wm">
                <svg className="px-vector" viewBox="0 0 3161 969" aria-label="Parallax">
                  <path fill="currentColor" fillRule="evenodd" d={OFFICIAL_PARALLAX_PATH} transform="translate(-464 -166)" />
                </svg>
                <span>A shift in Perspective</span>
              </div>
              <div className="fr">
                <div className="org-badges">
                  <img src={isteLogo} alt="ISTE Logo" className="org-badge" />
                  <img src={nssceLogo} alt="NSSCE Logo" className="org-badge" />
                </div>
                <b>ISTE &middot; NSSCE</b>
                <span>STATE CONVENTION</span>
              </div>
            </div>
          </div>
        </section>

        {/* BACK */}
        <section className="card back" style={cardStyle} aria-label="Pass back">
          <div className="id-edge-credit" aria-hidden="true">DEVELOPED BY MIDHUN K M</div>
          <div className="pl" style={{ background: spBack.bg }} aria-hidden="true">
            {backLayers.map((svgContent, idx) => (
              <svg
                key={idx}
                className="pl-layer"
                data-d={[0.3, 0.65, 1.1][idx]}
                viewBox="0 0 100 76"
                preserveAspectRatio="xMidYMid slice"
                dangerouslySetInnerHTML={{ __html: svgContent }}
              />
            ))}
          </div>
          <div className="fade" />
          <div className="slot" />
          <div className="binfo">
            <div className="wm">
              <svg className="px-vector" viewBox="0 0 3161 969" aria-label="Parallax">
                <path fill="currentColor" fillRule="evenodd" d={OFFICIAL_PARALLAX_PATH} transform="translate(-464 -166)" />
              </svg>
              <span>A shift in Perspective</span>
            </div>
            <div className="rows">
              <div>
                <small>Institution / College</small>
                <b title={collegeName}>{collegeName}</b>
              </div>
              <div>
                <small>Department / Stream</small>
                <b title={branchCourse}>{branchCourse}</b>
              </div>
              <div>
                <small>Helpdesk &amp; Support</small>
                <b title={`${typeof window !== 'undefined' && window.location?.origin ? window.location.origin : 'https://parallax-iste.vercel.app'}/contact`}>
                  {`${typeof window !== 'undefined' && window.location?.origin ? window.location.origin : 'https://parallax-iste.vercel.app'}/contact`}
                </b>
              </div>
              <div>
                <small>Organizing Chapter</small>
                <b>ISTE Students Chapter NSSCE</b>
              </div>
              {attendeeLogistics ? (
                <div>
                  <small>Gender / Meal / Stay</small>
                  <b>{attendeeLogistics}</b>
                </div>
              ) : null}
            </div>
            <div className="code">
              <svg viewBox="0 0 200 40" preserveAspectRatio="none" aria-label="Barcode">
                {barcodeRects}
              </svg>
              <small>{credentialId}</small>
            </div>
            <div className="note">
              If found, please return to Registration Desk, NSS College of Engineering, Palakkad - 678008
            </div>
          </div>
        </section>
      </div>

      {/* Interactive Controls (Hidden during Print) */}
      {showControls && (
        <div className="controls-panel no-print">
          {/* Designation Role Switcher */}
          {onRoleChange && (
            <div className="control-section">
              <div className="control-label">Official Designation Post</div>
              <div className="btn-group">
                {Object.entries(ROLE_CONFIGS).map(([key, cfg]) => (
                  <button
                    key={key}
                    type="button"
                    className={`btn ${roleKey === key ? 'active' : ''}`}
                    aria-pressed={roleKey === key}
                    onClick={() => {
                      onRoleChange(key);
                      if (onPaletteChange) onPaletteChange(cfg.paletteIdx);
                      else setInternalPaletteIdx(cfg.paletteIdx);
                    }}
                  >
                    {cfg.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Color Palette Switcher */}
          <div className="control-section">
            <div className="control-label">Card Tone Palette (Standard Waves)</div>
            <div className="btn-group">
              {PALETTES.map((pal, idx) => (
                <button
                  key={pal.name}
                  type="button"
                  className={`btn ${activePaletteIdx === idx && !customPalette ? 'active' : ''}`}
                  onClick={() => {
                    if (onPaletteChange) onPaletteChange(idx);
                    else setInternalPaletteIdx(idx);
                    setSeed(Math.floor(Math.random() * 9999));
                  }}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <span
                    style={{
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      background: pal.mid,
                      display: 'inline-block',
                      border: '1px solid rgba(0,0,0,0.15)',
                    }}
                  />
                  {pal.name}
                </button>
              ))}
              <button
                type="button"
                className="btn"
                onClick={() => {
                  const next = (activePaletteIdx + 1) % PALETTES.length;
                  if (onPaletteChange) onPaletteChange(next);
                  else setInternalPaletteIdx(next);
                  setSeed(Math.floor(Math.random() * 9999));
                }}
              >
                Shuffle Colors
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
