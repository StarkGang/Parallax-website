/**
 * Reads what the current page is actually about.
 *
 * The mascot never invents content: every line it speaks is built from headings,
 * labels and counts that exist in the DOM right now, so the commentary matches
 * whatever page or data the reader is looking at.
 */
const clean = (value = '') => String(value).replace(/\s+/g, ' ').trim();

function textOf(selector, root = document) {
  const node = root.querySelector(selector);
  return node ? clean(node.textContent) : '';
}

export function readPageContext() {
  if (typeof document === 'undefined') {
    return { title: '', kicker: '', headings: [], targets: [], counts: {} };
  }

  const main = document.querySelector('main') || document.body;

  const title = textOf('h1', main);

  const headings = [...main.querySelectorAll('h2, h3')]
    .map((node) => clean(node.textContent))
    .filter((value) => value.length > 2 && value.length < 90);

  const targets = [...main.querySelectorAll('[data-mascot-target]')].map((element) => ({
    id: element.getAttribute('data-mascot-target'),
    label: clean(element.getAttribute('data-mascot-label') || ''),
    hover: clean(element.getAttribute('data-mascot-hover') || ''),
  }));

  const counts = {
    targets: targets.length,
    events: targets.filter((target) => target.id?.startsWith('event-')).length,
    sections: main.querySelectorAll('section').length,
    links: main.querySelectorAll('a[href]').length,
  };

  return { title, headings: [...new Set(headings)].slice(0, 8), targets, counts };
}

/** One sentence about the page, drawn from its own content. */
export function contextLine(context, routeLine = '') {
  if (!context) return routeLine;

  const { title, headings, counts } = context;

  if (counts.events > 1) {
    return `${counts.events} competitions are listed here — I can point at any of them.`;
  }

  if (headings.length) {
    const heading = headings[Math.floor(Math.random() * headings.length)];
    const short = heading.length > 46 ? `${heading.slice(0, 44)}…` : heading;
    return `${short} — that is what this part of the page covers.`;
  }

  if (title) return `${title} — that is what this page is about.`;
  return routeLine;
}
