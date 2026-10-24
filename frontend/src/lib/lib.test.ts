import { describe, expect, it } from 'vitest';
import type { Heatmap, RouteOption } from '../api/types';
import { formatCriterion, formatDuration, formatMiles, formatTime } from './format';
import { boundsOf, cellFeatures, positionAtElapsed } from './geo';
import { cellColor, cellOpacity } from './mapStyle';
import { RISK_COLORS } from './risk';

const route: RouteOption = {
  id: 'A',
  via: 'I-80',
  distance_mi: 100,
  duration_s: 7200,
  arrival_utc: '2026-10-25T14:00:00Z',
  eta_source: 'progress',
  geometry: [
    [40, -100],
    [40, -99],
    [41, -99],
  ],
  elapsed_s: [0, 3600, 7200],
};

describe('format', () => {
  it('formats durations and miles', () => {
    expect(formatDuration(45 * 60)).toBe('45 m');
    expect(formatDuration(12 * 3600 + 5 * 60)).toBe('12 h 05 m');
    expect(formatMiles(1003.4)).toBe('1,003 mi');
    expect(formatMiles(2.46)).toBe('2.5 mi');
    expect(formatMiles(0)).toBe('0 mi');
  });

  it('always shows the time zone', () => {
    const plain = (s: string) => s.replace(/\s/g, ' ');
    expect(plain(formatTime('2026-10-25T13:00:00Z', 'America/Denver'))).toBe('Sun, 7:00 AM MDT');
    expect(plain(formatTime('2026-12-25T13:00:00Z', 'America/Denver'))).toBe('Fri, 6:00 AM MST');
  });

  it('formats comparison values per criterion', () => {
    expect(formatCriterion('coverage', 0.856)).toBe('86%');
    expect(formatCriterion('risk_index', 0.1)).toBe('0.10');
    expect(formatCriterion('duration_s', 3600)).toBe('1 h 00 m');
    expect(formatCriterion('severe_mi', 25)).toBe('25 mi');
    expect(formatCriterion('high_mi', null)).toBe('—');
  });
});

describe('geo', () => {
  it('places the truck by elapsed time', () => {
    expect(positionAtElapsed(route, 0)).toEqual([-100, 40]);
    expect(positionAtElapsed(route, 1800)).toEqual([-99.5, 40]);
    expect(positionAtElapsed(route, 5400)).toEqual([-99, 40.5]);
    expect(positionAtElapsed(route, -1)).toBeNull();
    expect(positionAtElapsed(route, 7201)).toBeNull();
  });

  it('computes bounds as [west, south], [east, north]', () => {
    expect(boundsOf([route])).toEqual([
      [-100, 40],
      [-99, 41],
    ]);
  });

  it('builds one square cell per centre with a property per hour', () => {
    const heatmap: Heatmap = {
      route_set_id: 'rs',
      start_utc: '2026-10-25T13:00:00Z',
      hours: 2,
      cell_deg: [0.2, 0.4],
      cells: [[40, -100]],
      risk: [[2], [null]],
    };
    const [cell] = cellFeatures(heatmap).features;
    expect(cell.properties).toEqual({ r0: 2, r1: -1 });
    expect(cell.geometry.coordinates[0][0]).toEqual([-100.2, 39.9]);
    expect(cell.geometry.coordinates[0][2]).toEqual([-99.8, 40.1]);
  });
});

describe('map style', () => {
  it('reads the selected hour and colours each exact risk class', () => {
    const expr = cellColor(7);
    expect(expr[1]).toEqual(['get', 'r7']);
    expect(expr).toContain(RISK_COLORS.severe);
    expect(expr[expr.length - 1]).toBe(RISK_COLORS.unknown);
    expect(cellOpacity(7)[1]).toEqual(['get', 'r7']);
  });
});
