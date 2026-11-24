const IST = 'Asia/Kolkata';

export const money = (paise) => {
  const value = Number(paise || 0) / 100;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
  }).format(value);
};

export const rupees = (paise) => Number(paise || 0) / 100;
export const paise = (amount) => Math.round(Number(amount || 0) * 100);

const dateFmt = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  timeZone: IST,
});
const timeFmt = new Intl.DateTimeFormat('en-IN', {
  hour: 'numeric',
  minute: '2-digit',
  timeZone: IST,
});
const weekdayFmt = new Intl.DateTimeFormat('en-IN', {
  weekday: 'long',
  day: '2-digit',
  month: 'long',
  timeZone: IST,
});

export const date = (iso) => (iso ? dateFmt.format(new Date(iso)) : 'To be announced');
export const time = (iso) => (iso ? timeFmt.format(new Date(iso)) : '');
export const weekday = (iso) => (iso ? weekdayFmt.format(new Date(iso)) : '');
export const dateTime = (iso) => (iso ? `${date(iso)} · ${time(iso)}` : '-');

export const fileSize = (bytes) => {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

// Convention dates are always Indian Standard Time, whatever the browser's
// timezone. Reading the year off a local Date would flip a 31 Dec/1 Jan range
// into a same-year label for browsers west of IST.
const istPart = (value, type, options) =>
  new Intl.DateTimeFormat('en-GB', { ...options, timeZone: IST })
    .formatToParts(new Date(value))
    .find((part) => part.type === type)?.value;

export const dateRange = (start, end) => {
  if (!start) return 'Dates to be announced';
  const a = new Date(start);
  const b = end ? new Date(end) : null;
  if (!b) return date(start);
  const sameYear =
    istPart(a, 'year', { year: 'numeric' }) === istPart(b, 'year', { year: 'numeric' });
  const left = sameYear
    ? new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', timeZone: IST }).format(a)
    : date(a);
  const right = date(b);
  return `${left} - ${right}`;
};

const IST_OFFSET = '+05:30';

/** datetime-local value for an ISO instant, always rendered in IST. */
export const toLocalInput = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: IST,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
      .formatToParts(d)
      .map((part) => [part.type, part.value]),
  );
  const hour = parts.hour === '24' ? '00' : parts.hour;
  return `${parts.year}-${parts.month}-${parts.day}T${hour}:${parts.minute}`;
};

/** Interpret a datetime-local value as IST rather than the browser's zone. */
export const fromLocalInput = (value) =>
  value ? new Date(`${value}:00${IST_OFFSET}`).toISOString() : null;

export const initials = (name = '') =>
  name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'PX';

export const titleCase = (value = '') =>
  value.replace(/[_-]/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());

export const dayLabel = (value) => (value === 'day1' ? 'Day one' : value === 'day2' ? 'Day two' : titleCase(value));

export const percent = (value, total) => {
  if (!total) return 0;
  return Math.min(100, Math.max(0, Math.round((value / total) * 100)));
};
