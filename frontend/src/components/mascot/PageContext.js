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

  const viewportHeight = typeof window === 'undefined' ? 0 : window.innerHeight;

  // Keep track of whether a heading is on screen right now: the guide talks
  // about what the reader can see, not about the top of a long page.
  const headings = [...main.querySelectorAll('h2, h3')]
    .map((node) => {
      const rect = node.getBoundingClientRect();
      return {
        text: clean(node.textContent),
        visible: rect.bottom > 0 && rect.top < viewportHeight * 0.92,
      };
    })
    .filter(({ text }) => text.length > 2 && text.length < 90);

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

  const uniqueHeadings = headings.filter(
    (heading, index) => headings.findIndex((other) => other.text === heading.text) === index,
  );

  return { title, headings: uniqueHeadings.slice(0, 10), targets, counts };
}

/** One sentence about the page, drawn from its own content. */
export function contextLine(context, routeLine = '') {
  if (!context) return routeLine;

  const { title, headings, counts } = context;

  if (counts.events > 1) {
    return `${counts.events} competitions are listed here — I can point at any of them.`;
  }

  if (headings.length) {
    const onScreen = headings.filter((heading) => heading.visible);
    const pool = onScreen.length ? onScreen : headings;
    const heading = pool[Math.floor(Math.random() * pool.length)].text;
    const short = heading.length > 46 ? `${heading.slice(0, 44)}…` : heading;
    return `${short} — that is what this part of the page covers.`;
  }

  if (title) return `${title} — that is what this page is about.`;
  return routeLine;
}
