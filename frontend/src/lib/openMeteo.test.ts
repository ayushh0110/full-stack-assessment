import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ForecastRequest, LatLon } from '../api/types';
import { clearForecastCache, fetchForecasts } from './openMeteo';

const item = (lat: number, lon: number) => ({
  latitude: lat,
  longitude: lon,
  generationtime_ms: 1,
  hourly_units: { wind_speed_10m: 'mp/h' },
  hourly: { time: [0], wind_speed_10m: [5] },
});

function request(locations: LatLon[], batchSize = 2): ForecastRequest {
  return {
    url: 'https://api.open-meteo.com/v1/forecast',
    params: {
      models: 'gfs_seamless',
      start_hour: '2026-10-25T00:00',
      end_hour: '2026-10-25T05:00',
    },
    batch_size: batchSize,
    locations,
  };
}

/** Answers like Open-Meteo: a list for several coordinates, an object for one. */
function openMeteoFetch(failLatitude?: number) {
  return vi.fn(async (url: string) => {
    const query = new URL(url).searchParams;
    const lats = query.get('latitude')!.split(',').map(Number);
    const lons = query.get('longitude')!.split(',').map(Number);
    if (lats.includes(failLatitude ?? NaN)) return new Response('{}', { status: 429 });
    const items = lats.map((lat, i) => item(lat, lons[i]));
    return new Response(JSON.stringify(items.length === 1 ? items[0] : items));
  });
}

describe('fetchForecasts', () => {
  beforeEach(() => clearForecastCache());
  afterEach(() => vi.unstubAllGlobals());

  it('fetches in batches and keeps the requested order', async () => {
    const fetchMock = openMeteoFetch();
    vi.stubGlobal('fetch', fetchMock);
    const locations: LatLon[] = [
      [40, -100],
      [41, -100],
      [42, -100],
    ];
    const result = await fetchForecasts(request(locations));
    expect(fetchMock).toHaveBeenCalledTimes(2); // batches of 2 and 1
    expect(result.map((r) => r?.latitude)).toEqual([40, 41, 42]);
    expect(result[0]).not.toHaveProperty('generationtime_ms'); // trimmed before relaying
    const firstUrl = new URL(fetchMock.mock.calls[0][0]);
    expect(firstUrl.searchParams.get('models')).toBe('gfs_seamless');
  });

  it('marks a failed batch as missing instead of failing everything', async () => {
    vi.stubGlobal('fetch', openMeteoFetch(42));
    const result = await fetchForecasts(
      request([
        [40, -100],
        [41, -100],
        [42, -100],
      ]),
    );
    expect(result.map((r) => r?.latitude ?? null)).toEqual([40, 41, null]);
  });

  it('reuses forecasts already fetched in this session', async () => {
    const fetchMock = openMeteoFetch();
    vi.stubGlobal('fetch', fetchMock);
    await fetchForecasts(request([[40, -100]]));
    await fetchForecasts(
      request([
        [40, -100],
        [41, -100],
      ]),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(new URL(fetchMock.mock.calls[1][0]).searchParams.get('latitude')).toBe('41');
  });
});
