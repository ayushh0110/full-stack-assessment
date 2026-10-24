import type { Feature, FeatureCollection, LineString, Point, Polygon } from 'geojson';
import type { Assessment, Heatmap, LatLon, RouteOption } from '../api/types';

export type LngLat = [number, number];

export const toLngLat = ([lat, lon]: LatLon): LngLat => [lon, lat];

export const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };

/** Where the truck is `elapsedS` seconds after departure, or null before/after the trip. */
export function positionAtElapsed(route: RouteOption, elapsedS: number): LngLat | null {
  const times = route.elapsed_s;
  if (!times.length || elapsedS < 0 || elapsedS > times[times.length - 1]) return null;
  let lo = 0;
  let hi = times.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= elapsedS) lo = mid;
    else hi = mid;
  }
  const span = times[hi] - times[lo];
  const t = span > 0 ? (elapsedS - times[lo]) / span : 0;
  const [lat1, lon1] = route.geometry[lo];
  const [lat2, lon2] = route.geometry[hi];
  return [lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t];
}

/** Halfway point by driving time — where the route's summary chip sits on the map. */
export function routeMidpoint(route: RouteOption): LngLat {
  return (
    positionAtElapsed(route, route.duration_s / 2) ??
    toLngLat(route.geometry[Math.floor(route.geometry.length / 2)])
  );
}

export function boundsOf(routes: RouteOption[]): [LngLat, LngLat] {
  let [west, south, east, north] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const route of routes) {
    for (const [lat, lon] of route.geometry) {
      west = Math.min(west, lon);
      east = Math.max(east, lon);
      south = Math.min(south, lat);
      north = Math.max(north, lat);
    }
  }
  return [
    [west, south],
    [east, north],
  ];
}

export function routeFeatures(routes: RouteOption[]): FeatureCollection<LineString> {
  return {
    type: 'FeatureCollection',
    features: routes.map((route) => ({
      type: 'Feature',
      properties: { id: route.id },
      geometry: { type: 'LineString', coordinates: route.geometry.map(toLngLat) },
    })),
  };
}

export function segmentFeatures(assessment: Assessment): FeatureCollection<LineString> {
  return {
    type: 'FeatureCollection',
    features: assessment.routes.flatMap((route) =>
      route.segments.map((segment): Feature<LineString> => ({
        type: 'Feature',
        properties: { routeId: route.id, level: segment.level ?? -1 },
        geometry: { type: 'LineString', coordinates: segment.coords.map(toLngLat) },
      })),
    ),
  };
}

export function checkpointFeatures(assessment: Assessment): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: assessment.routes.flatMap((route) =>
      route.checkpoints.map((cp, index): Feature<Point> => ({
        type: 'Feature',
        properties: { routeId: route.id, index, level: cp.level ?? -1 },
        geometry: { type: 'Point', coordinates: [cp.lon, cp.lat] },
      })),
    ),
  };
}

/** One square per corridor cell, with its risk for every forecast hour as r0…r48 (-1 = no data),
 * so the slider only has to change which property the paint expression reads. */
export function cellFeatures(heatmap: Heatmap): FeatureCollection<Polygon> {
  const [dLat, dLon] = heatmap.cell_deg;
  return {
    type: 'FeatureCollection',
    features: heatmap.cells.map(([lat, lon], i) => {
      const properties: Record<string, number> = {};
      heatmap.risk.forEach((frame, hour) => {
        properties[`r${hour}`] = frame[i] ?? -1;
      });
      const [s, n, w, e] = [lat - dLat / 2, lat + dLat / 2, lon - dLon / 2, lon + dLon / 2];
      return {
        type: 'Feature',
        properties,
        geometry: {
          type: 'Polygon',
          coordinates: [
            [
              [w, s],
              [e, s],
              [e, n],
              [w, n],
              [w, s],
            ],
          ],
        },
      };
    }),
  };
}
