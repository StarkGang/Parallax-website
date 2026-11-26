/**
 * Mascot behaviour map.
 *
 * All route lines, ambient lines, tips, and hover reactions share one consistent
 * voice so old and new dialogues never clash.
 */

export const WALK_SPEED_PX_PER_SEC = 150;

export const MASCOT_TIMING = {
  evaluateDelayMs: 400,
  ambientDelayMs: 12000,
  holdMs: 5200,
  globalCooldownMs: 2400,
  repositionCooldownMs: 600,
  strollMs: 16000,
  strollJitterMs: 6000,
  strollMinDistancePx: 180,
  boredMs: 11000,
  pointHighlightMs: 2000,
};

export const EXCLUDED_PREFIXES = ['/portal', '/manage', '/login'];

export const GENERAL_TIPS = [
  'Hover any card and I will tell you what it is actually about.',
  'One pass covers both days, lunch, and up to three included events.',
  'Double-click me if you are curious who built me.',
];

const COOLDOWN = 12000;

export const MASCOT_ROUTES = [
  {
    id: 'home',
    match: /^\/$/,
    line: 'Scroll down, the real show starts just below!',
    ambient: 'Keep scrolling… there is more down there.',
    tips: [
      'Scroll down, the real show starts just below!',
      'Keep scrolling… almost there!',
      "Oh, that's me staring at those 3! What would you choose?",
    ],
    behaviors: [
      {
        target: 'home-edition',
        message: "New here? Start with About, I'll save you a spot.",
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
      },
      {
        target: 'home-pass',
        message: 'One pass, both days, lunch included. You are welcome.',
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
      },
      {
        target: 'home-events',
        message: "Workshops, hackathons, or sprints, what's it gonna be?",
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
      },
    ],
  },
  {
    id: 'events',
    match: /^\/events$/,
    line: 'Hover any event and I will break it down for you.',
    ambient: 'Pick your events wisely, some timings overlap.',
    tips: [
      'Hover any event card to see what it is about.',
      'Check if an event fits your pass or needs an add-on.',
      'Once you get your pass, lock your seats in the portal.',
    ],
    group: {
      prefix: 'event-',
      message: 'Hover any event and I will tell you what happens there.',
      action: 'point',
      cooldownMs: 10000,
      maxShows: 99,
    },
  },
  {
    id: 'event-detail',
    match: /^\/events\/[^/]+$/,
    line: 'All the rules and timings for this one are right here.',
    ambient: 'Check the team size first, then grab your pass.',
    tips: [
      'You will need an active pass before you can register.',
      'Check the team size first, then go bug your friends.',
    ],
    behaviors: [
      {
        target: 'event-register',
        message: 'Feeling brave? Hit register.',
        action: 'point',
        cooldownMs: COOLDOWN,
        maxShows: 2,
      },
    ],
  },
  {
    id: 'pass',
    match: /^\/pass$/,
    line: 'Get it now, one pass covers both days!',
    ambient: 'Hover over a pass tier and I will tell you the catch.',
    tips: [
      'Make sure you have your ISTE membership if you pick the ISTE pass!',
      'Lunch is included on both days. You are welcome.',
      'Get your pass first, then pick your events in the portal.',
    ],
  },
  {
    id: 'schedule',
    match: /^\/schedule$/,
    line: 'Hover any session and let us see if you will actually wake up for it.',
    ambient: 'If two sessions clash, that is a you-problem. Plan ahead!',
    tips: [
      'Hover over any time slot for my honest opinion.',
      'Morning sessions hit different… especially before coffee.',
    ],
  },
  {
    id: 'venue',
    match: /^\/venue$/,
    line: 'Let me check my maps for the location…',
    ambient: 'Oh, I actually study here!',
    tips: [
      'Hover the campus block or map below.',
      'NSSCE Palakkad, you cannot miss it.',
    ],
  },
  {
    id: 'faq',
    match: /^\/faq$/,
    line: 'Plan it yourself, everything you need is right here.',
    ambient: 'Still stuck after reading? Hit the Contact page.',
    tips: [
      'Pass and registration questions are right at the top.',
      'Plan it yourself, the answers really are all here.',
    ],
  },
  {
    id: 'contact',
    match: /^\/contact$/,
    line: 'Need a real human? Fill this out and I will watch.',
    ambient: 'Type your name and email, I promise not to judge.',
    tips: [
      'Pick a category so it reaches the right desk.',
      'Send the message and all you have to do is wait.',
    ],
    behaviors: [
      {
        target: 'contact-topics',
        message: 'Pick what this is about first.',
        action: 'point',
        cooldownMs: 12000,
        maxShows: 99,
        priority: 1,
      },
      {
        target: 'contact-name',
        message: 'Drop your name here, let us see what it is.',
        action: 'point',
        cooldownMs: 14000,
        maxShows: 99,
        priority: 2,
      },
      {
        target: 'contact-submit',
        message: 'Ready? Send it and wait!',
        action: 'point',
        cooldownMs: 14000,
        maxShows: 99,
        priority: 3,
      },
    ],
  },
  {
    id: 'team',
    match: /^\/team$/,
    line: 'Hover a face and I will tell you who they are.',
    ambient: 'A bunch of students run this whole thing. Yes, really.',
    tips: [
      'Hover any card to meet the crew.',
      'One of these cards runs more of this than you would guess.',
    ],
    group: {
      prefix: 'team-',
      message: 'Pick a face, I will introduce them.',
      action: 'point',
      cooldownMs: 12000,
      maxShows: 99,
    },
    behaviors: [
      {
        target: 'team-midhun-k-m',
        message: 'Quietly behind most of what you are clicking right now.',
        action: 'point',
        cooldownMs: 60000,
        maxShows: 1,
        priority: 1,
      },
    ],
  },
  {
    id: 'about',
    match: /^\/about$/,
    line: 'Change your angle, change the whole picture. That is Parallax.',
    ambient: 'Host, dates, and the whole story are right here.',
    tips: [
      'NSSCE Palakkad, two days, one convention.',
      'Check out Pass or Events next.',
    ],
  },
  {
    id: 'not-found',
    match: /.*/,
    line: 'Whoops, you wandered off the map.',
    ambient: 'Let us get you back, Events is a good start.',
    tips: [
      'Try the events page or head back home.',
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
  return Math.min(4800, 2600 + String(text).length * 32);
}
