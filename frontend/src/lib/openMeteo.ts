import type { ForecastRequest, LatLon } from '../api/types';

/** One location's forecast as Open-Meteo returns it, trimmed to what the server needs. */
export interface OpenMeteoLocation {
  latitude: number;
  longitude: number;
  hourly_units: Record<string, string>;
  hourly: Record<string, (number | null)[]>;
}

const MAX_PARALLEL = 4;
const cache = new Map<string, OpenMeteoLocation>();

function cacheKey([lat, lon]: LatLon, params: Record<string, string>): string {
  return `${lat},${lon}|${params.models}|${params.start_hour}|${params.end_hour}`;
}

async function fetchBatch(
  request: ForecastRequest,
  locations: LatLon[],
  signal?: AbortSignal,
): Promise<(OpenMeteoLocation | null)[]> {
  const query = new URLSearchParams({
    ...request.params,
    latitude: locations.map(([lat]) => lat).join(','),
    longitude: locations.map(([, lon]) => lon).join(','),
  });
  try {
    const response = await fetch(`${request.url}?${query}`, { signal });
    if (!response.ok) return locations.map(() => null);
    const data = await response.json();
    const items: OpenMeteoLocation[] = Array.isArray(data) ? data : [data];
    if (items.length !== locations.length) return locations.map(() => null);
    return items.map(({ latitude, longitude, hourly_units, hourly }) => ({
      latitude,
      longitude,
      hourly_units,
      hourly,
    }));
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    return locations.map(() => null);
  }
}

/**
 * Fetches the forecasts the server asked for, from the visitor's browser.
 *
 * Open-Meteo's free tier is limited per IP address, and a shared hosting IP runs out because of
 * other tenants, so each visitor uses their own quota instead. The browser only relays the raw
 * responses: the server checks them and does all the risk scoring. Returns one entry per
 * requested location, in order, with null where a batch failed (scored as "no data", never Low).
 */
export async function fetchForecasts(
  request: ForecastRequest,
  signal?: AbortSignal,
): Promise<(OpenMeteoLocation | null)[]> {
  const results = request.locations.map((loc) => cache.get(cacheKey(loc, request.params)) ?? null);
  const missing = results.flatMap((found, index) => (found ? [] : [index]));
  const batches: number[][] = [];
  for (let i = 0; i < missing.length; i += request.batch_size) {
    batches.push(missing.slice(i, i + request.batch_size));
  }

  let next = 0;
  const worker = async () => {
    while (next < batches.length) {
      const batch = batches[next++];
      const items = await fetchBatch(
        request,
        batch.map((index) => request.locations[index]),
        signal,
      );
      batch.forEach((index, k) => {
        results[index] = items[k];
        if (items[k]) cache.set(cacheKey(request.locations[index], request.params), items[k]);
      });
    }
  };
  await Promise.all(Array.from({ length: Math.min(MAX_PARALLEL, batches.length) }, worker));
  return results;
}

export function clearForecastCache() {
  cache.clear();
}
