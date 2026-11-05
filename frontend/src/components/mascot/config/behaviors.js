/**
 * Mascot behaviour map.
 *
 * To add a page or a target you only touch this file and the page markup:
 *   <section data-mascot-target="my-target">…</section>
 *   { match: /^\/my-page$/, behaviors: [{ target: 'my-target', message: '…' }] }
 *
 * No pixel coordinates live here. The registry measures the element and picks
 * a free spot beside it at runtime.
 */

/** On-screen walking speed; MascotModel paces the Walk clip to match it. */
export const WALK_SPEED_PX_PER_SEC = 150;

export const MASCOT_TIMING = {
  evaluateDelayMs: 300,
  ambientDelayMs: 2800,
  holdMs: 3400,
  globalCooldownMs: 1800,
  repositionCooldownMs: 600,
  /** How often a resting mascot crosses the layout on its own. */
  strollMs: 3200,
  /** Random extra wait, so the pacing never feels metronomic. */
  strollJitterMs: 1800,
  /** A stroll is only worth walking if it actually crosses ground. */
  strollMinDistancePx: 180,
  /** After this long standing still, the mascot hops instead of idling. */
  boredMs: 6500,
  /** How long a pointed-out card stays ringed after an arrival point. */
  pointHighlightMs: 2600,
};

export const EXCLUDED_PREFIXES = ['/portal', '/manage', '/login'];

export const GENERAL_TIPS = [
  'I can point out the parts of the convention worth a closer look.',
  'Everything on this site comes from the live convention catalogue.',
  'Take your time — the programme is published and waiting.',
  'Click any card or section and I will follow along!',
];

const COOLDOWN = 12000;

export const MASCOT_ROUTES = [
  {
    id: 'home',
    match: /^\/$/,
    line: 'Hover a card below and I will tell you what it is.',
    ambient: 'One pass, two days. Start wherever your curiosity lands.',
    tips: [
      'I can point out the edition, the schedule and the competition catalogue.',
      'The pass includes both days and up to three included events.',
      'Every event card shows its fee basis before you open it.',
    ],
    tour: {
      intro:
        'Point at any of these three and I will explain it — or let me walk you through them in order.',
      outro:
        'That is the whole map: the edition, the programme and the competitions. Open whichever one you came for.',
      steps: [
        {
          target: 'home-edition',
          message: 'First, the edition — what Parallax is, the dates and the host institution.',
        },
        {
          target: 'home-schedule',
          message: 'Second, the programme — both convention days, session by session.',
        },
        {
          target: 'home-events',
          message: 'And the competition catalogue, where every event lists its fee basis.',
        },
      ],
    },
    behaviors: [
      {
        target: 'home-edition',
        message: 'Curious about Parallax? Start with the edition.',
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
      },
      {
        target: 'home-schedule',
        message: 'Check out the schedule!',
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
      },
      {
        target: 'home-events',
        message: 'Ready to explore events?',
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
      },
    ],
  },
  {
    id: 'events',
    match: /^\/events$/,
    ambient: 'The catalogue updates live from the organisers.',
    tips: [
      'Filter by category or format when the catalogue gets long.',
      'Every card shows its fee basis before you open it.',
      'Registration happens inside the participant portal.',
    ],
    group: {
      prefix: 'event-',
      message: 'Discover exciting events!',
      action: 'point',
      cooldownMs: 10000,
      maxShows: 99,
    },
    tour: {
      intro: 'These cards are the live catalogue. Hover one and I will read you its details.',
      outro: 'Open any card for the full brief — registration happens after you hold a pass.',
      steps: [{ group: 'event-', count: 3 }],
    },
  },
  {
    id: 'event-detail',
    match: /^\/events\/[^/]+$/,
    ambient: 'The full brief is on this page — take your time.',
    tips: [
      'Every participant needs an active convention pass first.',
      'Check the team size before you invite your teammates.',
      'I can point you at the registration entry point.',
    ],
    behaviors: [
      {
        target: 'event-register',
        message: 'Ready to join the challenge?',
        action: 'point',
        cooldownMs: COOLDOWN,
        maxShows: 2,
      },
    ],
    tour: {
      intro: 'Here is the short version of this page.',
      outro: 'That is the flow — an active pass first, then this register button.',
      steps: [
        {
          target: 'event-register',
          message: 'This button is the registration entry point for this event.',
        },
      ],
    },
  },
  {
    id: 'pass',
    match: /^\/pass$/,
    line: 'One pass, two days, up to three included events.',
    ambient: 'The pass price and policy are read from the live edition record.',
    tips: [
      'Add-on events are charged separately from the included allowance.',
      'Lunch is included on both convention days.',
      'Pass orders and event choices live in the participant portal.',
    ],
  },
  {
    id: 'schedule',
    match: /^\/schedule$/,
    line: 'The full programme, live from the catalogue.',
    ambient: 'Every session here is a real record the organisers maintain.',
    tips: [
      'Open an event from the programme to read its rules and fees.',
      'The schedule and the event catalogue share one source of truth.',
    ],
  },
  {
    id: 'venue',
    match: /^\/venue$/,
    line: 'This is where the convention happens.',
    ambient: 'The map is embedded below — no directions needed.',
    tips: ['The campus map is on this page.', 'Travel and contact details are in the footer.'],
  },
  {
    id: 'faq',
    match: /^\/faq$/,
    line: 'Most questions are answered right here.',
    ambient: 'If something is missing, the contact desk replies within a day.',
    tips: [
      'The pass and registration answers are grouped first.',
      'Still stuck? Contact the organisers from the contact page.',
    ],
  },
  {
    id: 'contact',
    match: /^\/contact$/,
    line: 'Need a human? The desk is right here.',
    ambient: 'The organisers reply within a day on convention business.',
    tips: [
      'Use the contact form for registration or payment questions.',
      'Pick an inquiry category above to route your message directly.',
      'Include your registered email so the team can find your record.',
      'Our student organising committee is standing by!',
    ],
    behaviors: [
      {
        target: 'contact-topics',
        message: 'Pick an inquiry category to route your message quickly!',
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
        priority: 1,
      },
      {
        target: 'contact-name',
        message: 'Enter your full name here.',
        action: 'point',
        cooldownMs: 10000,
        maxShows: 99,
        priority: 2,
      },
      {
        target: 'contact-message',
        message: 'Describe your question or issue in detail.',
        action: 'point',
        cooldownMs: 10000,
        maxShows: 99,
        priority: 3,
      },
      {
        target: 'contact-submit',
        message: 'Hit dispatch when you are ready to send!',
        action: 'point',
        cooldownMs: 10000,
        maxShows: 99,
        priority: 4,
      },
    ],
    tour: {
      intro: 'Let me show you the form field by field.',
      outro: 'That is it — send it and the desk replies within a day.',
      steps: [
        {
          target: 'contact-topics',
          message: 'Pick a category first so your message reaches the right desk.',
        },
        { target: 'contact-name', message: 'Your registered full name goes here.' },
        {
          target: 'contact-message',
          message: 'Then describe the question in a couple of lines.',
        },
      ],
    },
  },
  {
    id: 'team',
    match: /^\/team$/,
    line: 'This platform was built end to end by students.',
    ambient: 'Design, frontend, backend and operations — all student work.',
    tips: [
      'The team page lists who built and runs the convention platform.',
      'Questions about the build can go to the contact desk.',
    ],
  },
  {
    id: 'about',
    match: /^\/about$/,
    line: 'A different angle changes everything.',
    ambient: 'The edition, host and venue all come from the live record.',
    tips: [
      'The host institution and dates are on this page.',
      'The pass and programme are one click away in the navigation.',
    ],
  },
  {
    id: 'not-found',
    match: /.*/,
    line: 'This page is off the map.',
    ambient: 'The event catalogue is a good place to get back on track.',
    tips: [
      'Try the event catalogue or the homepage.',
      'Older links may point at events that moved in the programme.',
    ],
  },
];

export const MASCOT_STORAGE_KEY = 'parallax.mascot.hidden';

export function normalizePath(pathname = '') {
  const path = String(pathname || '/')
    .split('?')[0]
    .split('#')[0];
  if (path.length > 1 && path.endsWith('/')) return path.replace(/\/+$/, '');
  return path || '/';
}

export function resolveRouteBehavior(pathname) {
  const path = normalizePath(pathname);
  if (EXCLUDED_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))) {
    return null;
  }
  return (
    MASCOT_ROUTES.find((route) => route.match.test(path)) || MASCOT_ROUTES[MASCOT_ROUTES.length - 1]
  );
}

export function bubbleTtl(text = '') {
  return Math.min(6200, 3000 + String(text).length * 38);
}
