const IST = 'Asia/Kolkata';

// Formatters are module-level: building Intl objects per call is measurable in
// tables that render one price or date per row.
const inrFmt = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

const istInputFmt = new Intl.DateTimeFormat('en-CA', {
  timeZone: IST,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

const dayMonthFmt = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit',
  month: 'short',
  timeZone: IST,
});

export const money = (paise) => inrFmt.format(Number(paise || 0) / 100);

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

export const dateRange = (start, end) => {
  if (!start) return 'Dates to be announced';
  const a = new Date(start);
  const b = end ? new Date(end) : null;
  if (!b) return date(start);
  const sameYear = a.getFullYear() === b.getFullYear();
  const left = sameYear ? dayMonthFmt.format(a) : date(a);
  const right = date(b);
  return `${left} - ${right}`;
};

export const toLocalInput = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

export const fromLocalInput = (value) => (value ? new Date(value).toISOString() : null);

export const toISTInput = (iso) => {
  if (!iso) return '';
  const parts = istInputFmt.formatToParts(new Date(iso));
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
};

export const fromISTInput = (value) => {
  if (!value) return null;
  const [day, clock] = value.split('T');
  const [year, month, dateValue] = day.split('-').map(Number);
  const [hour, minute] = clock.split(':').map(Number);
  return new Date(Date.UTC(year, month - 1, dateValue, hour - 5, minute - 30)).toISOString();
};

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
