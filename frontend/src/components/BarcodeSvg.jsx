/**
 * Code 39 barcode rendered as SVG.
 *
 * The pass already carries a QR for turnstiles; the barcode is the human-readable
 * credential line security desks scan with handheld wands. Encoding happens in the
 * browser from the registration number, so nothing is stored as an image.
 */
const CODE39 = {
  '0': 'nnnwwnwnn',
  '1': 'wnnwnnnnw',
  '2': 'nnwwnnnnw',
  '3': 'wnwwnnnnn',
  '4': 'nnnwwnnnw',
  '5': 'wnnwwnnnn',
  '6': 'nnwwwnnnn',
  '7': 'nnnwnnwnw',
  '8': 'wnnwnnwnn',
  '9': 'nnwwnnwnn',
  A: 'wnnnnwnnw',
  B: 'nnwnnwnnw',
  C: 'wnwnnwnnn',
  D: 'nnnnwwnnw',
  E: 'wnnnwwnnn',
  F: 'nnwnwwnnn',
  G: 'nnnnnwwnw',
  H: 'wnnnnwwnn',
  I: 'nnwnnwwnn',
  J: 'nnnnwwwnn',
  K: 'wnnnnnnww',
  L: 'nnwnnnnww',
  M: 'wnwnnnnwn',
  N: 'nnnnwnnww',
  O: 'wnnnwnnwn',
  P: 'nnwnwnnwn',
  Q: 'nnnnnnwww',
  R: 'wnnnnnwwn',
  S: 'nnwnnnwwn',
  T: 'nnnnwnwwn',
  U: 'wwnnnnnnw',
  V: 'nwwnnnnnw',
  W: 'wwwnnnnnn',
  X: 'nwnnwnnnw',
  Y: 'wwnnwnnnn',
  Z: 'nwwnwnnnn',
  '-': 'nwnnnnwnw',
  '.': 'wwnnnnwnn',
  ' ': 'nwwnnnwnn',
  $: 'nwnwnwnnn',
  '/': 'nwnwnnnwn',
  '+': 'nwnnnwnwn',
  '%': 'nnnwnwnwn',
  '*': 'nwnnwnwnn',
};

const NARROW = 1;
// 3:1 is the Code 39 reference ratio; ZXing decodes the rendered symbol.
const WIDE = 3;
const GAP = 1;
const BAR_HEIGHT = 40;

export function BarcodeSvg({ value = '', className = '', title = 'Credential barcode' }) {
  const text = String(value || '')
    .toUpperCase()
    .replace(/[^0-9A-Z\-. $/+%]/g, '')
    .trim()
    .slice(0, 24);

  if (!text) return null;

  const chars = ['*', ...text.split(''), '*'];
  const bars = [];
  let cursor = 0;

  chars.forEach((char, charIndex) => {
    const pattern = CODE39[char];
    if (!pattern) return;
    for (let index = 0; index < pattern.length; index += 1) {
      const width = pattern[index] === 'w' ? WIDE : NARROW;
      if (index % 2 === 0) bars.push({ x: cursor, width });
      cursor += width;
    }
    if (charIndex < chars.length - 1) cursor += GAP;
  });

  return (
    <svg
      className={className}
      viewBox={`0 0 ${cursor} ${BAR_HEIGHT}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`${title}: ${text}`}
      xmlns="http://www.w3.org/2000/svg"
    >
      <title>{`${title}: ${text}`}</title>
      {bars.map((bar) => (
        <rect key={bar.x} x={bar.x} y="0" width={bar.width} height={BAR_HEIGHT} fill="currentColor" />
      ))}
    </svg>
  );
}
