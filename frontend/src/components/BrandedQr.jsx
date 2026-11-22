import { useMemo } from 'react';

import { createQrMatrix } from '../lib/qrBrand.js';

const INK = '#0a1024';
/* The official brand P — the same asset the site ships as its favicon. */
const P_MARK = `${import.meta.env.BASE_URL}favicon-512x512.png`;
const FINDER = 7;
const QUIET = 3;

/**
 * Parallax credential QR.
 *
 * Same data and error correction as a standard QR, drawn with the convention's
 * own language: rounded modules, squared-off finder eyes and the Parallax "P"
 * in a sharp navy plate at the centre. Level H pads the code so the plate never
 * eats payload data.
 */
export function BrandedQr({ value, className = '', title = 'QR code' }) {
  const matrix = useMemo(() => {
    try {
      return createQrMatrix(value);
    } catch {
      return null;
    }
  }, [value]);

  if (!value || !matrix) return null;

  const { count, modules } = matrix;
  const inFinder = (row, col) =>
    (row < FINDER && col < FINDER) ||
    (row < FINDER && col >= count - FINDER) ||
    (row >= count - FINDER && col < FINDER);

  const plateSize = count >= 41 ? 11 : count >= 29 ? 9 : 7;
  const plateStart = Math.floor((count - plateSize) / 2);
  const inPlate = (row, col) =>
    row >= plateStart &&
    row < plateStart + plateSize &&
    col >= plateStart &&
    col < plateStart + plateSize;

  const center = count / 2;
  const markSize = plateSize - 1.5;

  const eye = (x, y) => (
    <g key={`eye-${x}-${y}`} transform={`translate(${x} ${y})`}>
      <rect x="0.5" y="0.5" width="6" height="6" rx="1.1" fill="none" stroke={INK} strokeWidth="1" />
      <rect x="2" y="2" width="3" height="3" rx="0.45" fill={INK} />
    </g>
  );

  return (
    <svg
      className={className}
      viewBox={`${-QUIET} ${-QUIET} ${count + QUIET * 2} ${count + QUIET * 2}`}
      role="img"
      aria-label={title}
      shapeRendering="geometricPrecision"
      style={{ display: 'block', width: '100%', height: 'auto' }}
      xmlns="http://www.w3.org/2000/svg"
    >
      <title>{title}</title>
      <rect
        x={-QUIET}
        y={-QUIET}
        width={count + QUIET * 2}
        height={count + QUIET * 2}
        fill="#ffffff"
      />

      <g fill={INK}>
        {modules.map((row, rowIndex) =>
          row.map((dark, colIndex) =>
            dark && !inFinder(rowIndex, colIndex) && !inPlate(rowIndex, colIndex) ? (
              <rect
                key={`${rowIndex}-${colIndex}`}
                x={colIndex}
                y={rowIndex}
                width="1"
                height="1"
                rx="0.2"
              />
            ) : null
          )
        )}
      </g>

      {eye(0, 0)}
      {eye(count - FINDER, 0)}
      {eye(0, count - FINDER)}

      <g>
        <rect
          x={plateStart - 0.25}
          y={plateStart - 0.25}
          width={plateSize + 0.5}
          height={plateSize + 0.5}
          rx="0.5"
          fill="#0a1024"
        />
        <image
          x={center - markSize / 2}
          y={center - markSize / 2}
          width={markSize}
          height={markSize}
          href={P_MARK}
          preserveAspectRatio="xMidYMid meet"
        />
      </g>
    </svg>
  );
}
