import type { Criterion } from '../api/types';

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return hours ? `${hours} h ${String(mins).padStart(2, '0')} m` : `${mins} m`;
}

export function formatMiles(miles: number): string {
  const value =
    miles >= 10 || miles === 0 ? Math.round(miles).toLocaleString('en-US') : miles.toFixed(1);
  return `${value} mi`;
}

export function formatLoad(lb: number): string {
  return `${lb.toLocaleString('en-US')} lb`;
}

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(timeZone: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${timeZone}|${JSON.stringify(options)}`;
  let fmt = formatters.get(key);
  if (!fmt) {
    fmt = new Intl.DateTimeFormat('en-US', { timeZone, ...options });
    formatters.set(key, fmt);
  }
  return fmt;
}

/** "Sat 2:20 PM MDT" — always with the zone, since trips cross time zones. */
export function formatTime(value: string | number | Date, timeZone: string): string {
  return formatter(timeZone, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(new Date(value));
}

/** "3:06 PM": compact clock time for map labels. */
export function formatClock(value: string | number | Date, timeZone: string): string {
  return formatter(timeZone, { hour: 'numeric', minute: '2-digit' }).format(new Date(value));
}

export function zoneAbbreviation(timeZone: string, at: Date = new Date()): string {
  const part = formatter(timeZone, { timeZoneName: 'short' })
    .formatToParts(at)
    .find((p) => p.type === 'timeZoneName');
  return part?.value ?? timeZone;
}

export function formatCriterion(criterion: Criterion, value: number | null): string {
  if (value === null) return '—';
  switch (criterion) {
    case 'coverage':
      return `${Math.round(value * 100)}%`;
    case 'risk_index':
      return value.toFixed(2);
    case 'duration_s':
      return formatDuration(value);
    default:
      return formatMiles(value);
  }
}
