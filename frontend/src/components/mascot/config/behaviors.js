/**
 * Mascot behaviour map.
 *
 * To add a page or a target you only touch this file and the page markup:
 *   <section data-mascot-target="my-target">…</section>
 *   { match: /^\/my-page$/, behaviors: [{ target: 'my-target', message: '…' }] }
 *
 * No pixel coordinates live here. The registry measures the element and picks
 * a free spot beside it at runtime.
 *
 * VOICE GUIDE (keep new lines in this voice):
 * - Parallax is a student-built mascot who actually wants you to come to the fest.
 * - Short, chatty, a little cheeky. Contractions always. One idea per bubble.
 * - No corporate phrases ("explore our offerings", "take your time", "worth a look").
 * - Facts stay accurate: pass = both days + up to 3 events, lunch both days,
 *   add-ons cost extra, fee basis shows on every card, registration is in the portal.
 */

/** On-screen walking speed; MascotModel paces the Walk clip to match it. */
export const WALK_SPEED_PX_PER_SEC = 118;

export const MASCOT_TIMING = {
  evaluateDelayMs: 300,
  /** Long enough that the guide stays quiet while someone is reading. */
  ambientDelayMs: 6000,
  holdMs: 3400,
  globalCooldownMs: 1800,
  repositionCooldownMs: 600,
  /** How often a resting mascot crosses the layout on its own. */
  strollMs: 11000,
  /** Random extra wait, so the pacing never feels metronomic. */
  strollJitterMs: 6000,
  /** A stroll is only worth walking if it actually crosses ground. */
  strollMinDistancePx: 320,
  /** After this long standing still, the mascot hops instead of idling. */
  boredMs: 18000,
  /** How long a pointed-out card stays ringed after an arrival point. */
  pointHighlightMs: 2600,
};

export const EXCLUDED_PREFIXES = ['/portal', '/manage', '/login'];

export const GENERAL_TIPS = [
  'Click any card and I\'ll tag along.',
  'Everything here is pulled live from the organisers, so no stale info.',
  'Lost? Same. Try the menu up top.',
  'I walk around a lot. Don\'t take it personally.',
  'Psst. The good stuff is usually a scroll away.',
];

const COOLDOWN = 12000;

export const MASCOT_ROUTES = [
  {
    id: 'home',
    match: /^\/$/,
    line: 'Hey, I\'m your guide! Scroll down, I\'ll show you around.',
    ambient: 'Two days, one pass. Start wherever looks fun.',
    tips: [
      'Edition, schedule, competitions. That\'s the whole site, really.',
      'One pass covers both days and up to three events.',
      'Every event card shows what it costs before you click in. No surprises.',
      'Lunch is sorted on both days, by the way.',
    ],
    tour: {
      intro:
        'Three things to see here. Poke any of them, or let me walk you through in order.',
      outro:
        'And that\'s the map! Go open whichever one made you curious.',
      steps: [
        {
          target: 'home-edition',
          message: 'First up, the edition. What Parallax is, when it\'s on, and who\'s hosting.',
        },
        {
          target: 'home-schedule',
          message: 'Next, the schedule. Both days, session by session.',
        },
        {
          target: 'home-events',
          message: 'And the competitions. Fees are listed on every card.',
        },
      ],
    },
    behaviors: [
      {
        target: 'home-edition',
        message: 'New here? Start with this one.',
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
      },
      {
        target: 'home-schedule',
        message: 'Two days of stuff. Have a look!',
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
      },
      {
        target: 'home-events',
        message: 'Okay, this is the fun part. Competitions!',
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
      },
    ],
  },
  {
    id: 'events',
    match: /^\/events$/,
    ambient: 'The organisers update this list live, so check back.',
    tips: [
      'Too many events? Filter by category or format.',
      'Fee info is right on the card. Look before you click.',
      'You register in the participant portal, not here.',
      'Can\'t pick just one? Your pass covers up to three.',
    ],
    group: {
      prefix: 'event-',
      message: 'Pick a fight. I mean, an event.',
      action: 'point',
      cooldownMs: 10000,
      maxShows: 99,
    },
    tour: {
      intro: 'This is the live catalogue. Hover a card and I\'ll read you the details.',
      outro: 'Open any card for the full brief. You\'ll need a pass before you can register.',
      steps: [{ group: 'event-', count: 3 }],
    },
  },
  {
    id: 'event-detail',
    match: /^\/events\/[^/]+$/,
    ambient: 'Everything about this event is on this page. Scroll on.',
    tips: [
      'You\'ll need an active pass before you can register.',
      'Check the team size first, then go bug your friends.',
      'Want the register button? I know where it is.',
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
    tour: {
      intro: 'Quick version of this page, coming up.',
      outro: 'That\'s it. Pass first, then this button.',
      steps: [
        {
          target: 'event-register',
          message: 'This is where you sign up for the event.',
        },
      ],
    },
  },
  {
    id: 'pass',
    match: /^\/pass$/,
    line: 'One pass, two days, up to three events. Simple.',
    ambient: 'Price and rules here are always the latest ones.',
    tips: [
      'Want more than three events? Extras cost a little more.',
      'Lunch is included on both days. You\'re welcome.',
      'You buy the pass and pick your events in the participant portal.',
    ],
  },
  {
    id: 'schedule',
    match: /^\/schedule$/,
    line: 'Here\'s the whole programme, straight from the organisers.',
    ambient: 'Nothing here is made up. The team updates it themselves.',
    tips: [
      'Tap a session to see the rules and fees.',
      'If two things clash, that\'s a you-problem. Plan ahead!',
      'The schedule and the events list always match.',
    ],
  },
  {
    id: 'venue',
    match: /^\/venue$/,
    line: 'This is where it all goes down.',
    ambient: 'The map\'s below. Scroll and you won\'t get lost.',
    tips: [
      'Campus map is right on this page.',
      'Travel and contact details are down in the footer.',
    ],
  },
  {
    id: 'faq',
    match: /^\/faq$/,
    line: 'Got questions? Probably answered here already.',
    ambient: 'Still stuck after this? The organisers reply within a day.',
    tips: [
      'Pass and registration questions are right at the top.',
      'Can\'t find yours? Message the organisers, they don\'t bite.',
    ],
  },
  {
    id: 'contact',
    match: /^\/contact$/,
    line: 'Need a real human? Right this way.',
    ambient: 'The organisers usually reply within a day.',
    tips: [
      'Use the form for registration or payment trouble.',
      'Pick a category first so your message lands with the right person.',
      'Add the email you registered with, so they can find you fast.',
      'The student committee is on it. Promise.',
    ],
    behaviors: [
      {
        target: 'contact-topics',
        message: 'Pick what this is about, so it reaches the right desk.',
        action: 'point',
        cooldownMs: 8000,
        maxShows: 99,
        priority: 1,
      },
      {
        target: 'contact-name',
        message: 'Your name goes here. Full one, please.',
        action: 'point',
        cooldownMs: 10000,
        maxShows: 99,
        priority: 2,
      },
      {
        target: 'contact-message',
        message: 'Tell them what\'s up. A few lines is plenty.',
        action: 'point',
        cooldownMs: 10000,
        maxShows: 99,
        priority: 3,
      },
      {
        target: 'contact-submit',
        message: 'Ready? Hit dispatch!',
        action: 'point',
        cooldownMs: 10000,
        maxShows: 99,
        priority: 4,
      },
    ],
    tour: {
      intro: 'It\'s a short form. I\'ll walk you through it.',
      outro: 'Done! Send it and someone will get back to you within a day.',
      steps: [
        {
          target: 'contact-topics',
          message: 'Pick a category first. It saves everyone time.',
        },
        { target: 'contact-name', message: 'Name goes here. Same one you registered with.' },
        {
          target: 'contact-message',
          message: 'Then tell them what you need in a couple of lines.',
        },
      ],
    },
  },
  {
    id: 'team',
    match: /^\/team$/,
    line: 'Students built this whole thing. Yes, really.',
    ambient: 'Hover a face and I will tell you who they are.',
    tips: [
      'These are the people who built and run all of this.',
      'Hover a card for names. I do the remembering for you.',
      'Questions about how it was built? Ask through the contact page.',
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
        message: 'That one is the reason I exist. Go say hi.',
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
    line: 'Change your angle, change the whole picture. That\'s the idea.',
    ambient: 'Host, dates and venue are all on this page.',
    tips: [
      'Host college and dates are right here.',
      'Pass and schedule are one click away in the menu.',
    ],
  },
  {
    id: 'not-found',
    match: /.*/,
    line: 'Whoops, you\'ve wandered off the map.',
    ambient: 'Let\'s get you back. Events list is a good start.',
    tips: [
      'Try the events page or head back home.',
      'Old links sometimes break when events move around.',
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