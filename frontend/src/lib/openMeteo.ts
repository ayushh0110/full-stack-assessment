import type { ForecastRequest, LatLon } from '../api/types';

/** One location's forecast as Open-Meteo returns it, trimmed to what the server needs. */
export interface OpenMeteoLocation {
  latitude: number;
  longitude: number;
  hourly_units: Record<string, string>;
  hourly: Record<string, (number | null)[]>;
}

const MAX_PARALLEL = 4;
const MAX_RETRIES = 2;
/** Open-Meteo counts each location as a call and allows 600 a minute on the free tier. */
const MINUTE_LIMIT_WAIT_S = 62;

const cache = new Map<string, OpenMeteoLocation>();
/** Shared by every fetch in this tab, so concurrent fetches all back off together. */
let pausedUntil = 0;

type Limit = { retryAfterS: number } | { blocked: string };
type BatchResult =
  { items: (OpenMeteoLocation | null)[]; blocked?: string } | { retryAfterS: number };

export interface ForecastEvents {
  /** The per-minute limit was hit; fetching resumes at `retryAtMs`. */
  onPause?: (retryAtMs: number) => void;
  /** After each fetch: Open-Meteo's reason if a longer (hourly/daily) limit blocked it, else null. */
  onBlocked?: (reason: string | null) => void;
}

function cacheKey([lat, lon]: LatLon, params: Record<string, string>): string {
  return `${lat},${lon}|${params.models}|${params.start_hour}|${params.end_hour}`;
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'));
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      },
      { once: true },
    );
  });
}

/** How to handle a 429: wait and retry (per-minute limit), or give up (hourly/daily limit). */
async function readLimit(response: Response): Promise<Limit> {
  const header = Number(response.headers.get('Retry-After'));
  if (header > 0) return { retryAfterS: header };
  const body = await response.json().catch(() => null);
  const reason: string = body?.reason ?? 'The weather service rate limit was reached.';
  return /minute/i.test(reason) ? { retryAfterS: MINUTE_LIMIT_WAIT_S } : { blocked: reason };
}

async function fetchBatch(
  request: ForecastRequest,
  locations: LatLon[],
  signal?: AbortSignal,
): Promise<BatchResult> {
  const missing = { items: locations.map(() => null) };
  const query = new URLSearchParams({
    ...request.params,
    latitude: locations.map(([lat]) => lat).join(','),
    longitude: locations.map(([, lon]) => lon).join(','),
  });
  try {
    const response = await fetch(`${request.url}?${query}`, { signal });
    if (response.status === 429) {
      const limit = await readLimit(response);
      return 'blocked' in limit ? { ...missing, blocked: limit.blocked } : limit;
    }
    if (!response.ok) return missing;
    const data = await response.json();
    const items: OpenMeteoLocation[] = Array.isArray(data) ? data : [data];
    if (items.length !== locations.length) return missing;
    return {
      items: items.map(({ latitude, longitude, hourly_units, hourly }) => ({
        latitude,
        longitude,
        hourly_units,
        hourly,
      })),
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    return missing;
  }
}

/**
 * Fetches the forecasts the server asked for, from the visitor's browser.
 *
 * Open-Meteo's free tier is limited per IP address, and a shared hosting IP runs out because of
 * other tenants, so each visitor uses their own quota instead. The browser only relays the raw
 * responses: the server checks them and does all the risk scoring. Returns one entry per
 * requested location, in order, with null where a batch failed (scored as "no data", never Low).
 *
 * When Open-Meteo's per-minute limit is hit, fetching pauses and retries (`onPause` gets the time
 * the retry is due, for a countdown). An hourly or daily limit isn't retried; `onBlocked` gets
 * Open-Meteo's reason so the UI can say what happened.
 */
export async function fetchForecasts(
  request: ForecastRequest,
  signal?: AbortSignal,
  events: ForecastEvents = {},
): Promise<(OpenMeteoLocation | null)[]> {
  const results = request.locations.map((loc) => cache.get(cacheKey(loc, request.params)) ?? null);
  const missing = results.flatMap((found, index) => (found ? [] : [index]));
  const batches: number[][] = [];
  for (let i = 0; i < missing.length; i += request.batch_size) {
    batches.push(missing.slice(i, i + request.batch_size));
  }

  let next = 0;
  let blocked: string | null = null;
  const worker = async () => {
    while (next < batches.length) {
      const batch = batches[next++];
      const locations = batch.map((index) => request.locations[index]);
      let items: (OpenMeteoLocation | null)[] = locations.map(() => null);
      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        if (pausedUntil > Date.now()) await wait(pausedUntil - Date.now(), signal);
        const result = await fetchBatch(request, locations, signal);
        if ('items' in result) {
          items = result.items;
          blocked = result.blocked ?? blocked;
          break;
        }
        if (attempt < MAX_RETRIES) {
          pausedUntil = Math.max(pausedUntil, Date.now() + result.retryAfterS * 1000);
          events.onPause?.(pausedUntil);
        }
      }
      batch.forEach((index, k) => {
        results[index] = items[k];
        if (items[k]) cache.set(cacheKey(request.locations[index], request.params), items[k]);
      });
    }
  };
  await Promise.all(Array.from({ length: Math.min(MAX_PARALLEL, batches.length) }, worker));
  events.onBlocked?.(blocked);
  return results;
}

export function resetForecastState() {
  cache.clear();
  pausedUntil = 0;
}
