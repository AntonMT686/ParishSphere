import i18n from '@/i18n';

function locale(): string {
  return i18n.language === 'ta' ? 'ta-IN' : 'en-IN';
}

/** API datetimes are UTC without offset; render them in the browser's time zone. */
export function parseApiDate(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—';
  return parseApiDate(value).toLocaleString(locale(), { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatDate(value?: string | null): string {
  if (!value) return '—';
  const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : parseApiDate(value);
  return d.toLocaleDateString(locale(), { dateStyle: 'medium' });
}

export function timeAgo(value: string): string {
  const diff = (Date.now() - parseApiDate(value).getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: 'auto' });
  if (diff < 60) return rtf.format(-Math.round(diff), 'second');
  if (diff < 3600) return rtf.format(-Math.round(diff / 60), 'minute');
  if (diff < 86400) return rtf.format(-Math.round(diff / 3600), 'hour');
  return rtf.format(-Math.round(diff / 86400), 'day');
}

export function formatMoney(value: string | number, currency = 'INR'): string {
  return new Intl.NumberFormat(locale(), { style: 'currency', currency }).format(Number(value));
}

/** Format a local wall-clock value from the API (e.g. a meeting time stored in parish time, no zone). */
export function formatWallTime(value?: string | null, withDate = true): string {
  if (!value) return '—';
  const d = new Date(value.replace(/[zZ]$/, ''));
  return withDate
    ? d.toLocaleString(locale(), { dateStyle: 'medium', timeStyle: 'short' })
    : d.toLocaleTimeString(locale(), { timeStyle: 'short' });
}
