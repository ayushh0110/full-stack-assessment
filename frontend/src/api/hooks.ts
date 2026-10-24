import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { fetchForecasts } from '../lib/openMeteo';
import { useAppStore } from '../store';
import { api } from './client';
import type { Interval } from './types';

const MINUTE = 60_000;

export function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

/** True once `active` has stayed true for `delayMs`: a request this slow usually means the
 * free-tier server is waking up, which is worth telling the user. */
export function useSlow(active: boolean, delayMs = 6000): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    const timer = setTimeout(() => setSlow(true), delayMs);
    return () => clearTimeout(timer);
  }, [active, delayMs]);
  return active && slow;
}

/** Whole seconds left until `untilMs`, ticking once a second; 0 once it has passed. */
export function useCountdown(untilMs: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!untilMs) return;
    setNow(Date.now());
    const timer = setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= untilMs) clearInterval(timer);
    }, 1000);
    return () => clearInterval(timer);
  }, [untilMs]);
  return untilMs ? Math.max(0, Math.ceil((untilMs - now) / 1000)) : 0;
}

/** Seconds until forecasts are retried after hitting Open-Meteo's rate limit; 0 if not waiting. */
export function useWeatherRetryIn(): number {
  return useCountdown(useAppStore((s) => s.weatherRetryAt));
}

const forecastEvents = {
  onPause: (retryAt: number) => useAppStore.getState().setWeatherRetryAt(retryAt),
  onBlocked: (reason: string | null) => useAppStore.getState().setWeatherBlocked(reason),
};

export function usePlaceSearch(query: string) {
  const debounced = useDebounced(query.trim(), 300);
  return useQuery({
    queryKey: ['geocode', debounced.toLowerCase()],
    queryFn: ({ signal }) => api.geocode(debounced, signal),
    enabled: debounced.length >= 3,
    staleTime: 24 * 60 * MINUTE,
    placeholderData: keepPreviousData,
  });
}

export function useCreateRouteSet() {
  return useMutation({ mutationFn: api.createRouteSet });
}

export function useAssessment(routeSetId: string | undefined, interval: Interval) {
  return useQuery({
    queryKey: ['assessment', routeSetId, interval],
    // 1) ask the server which forecasts it needs, 2) fetch them from Open-Meteo in the browser,
    // 3) let the server score the routes.
    queryFn: async ({ signal }) => {
      const request = await api.assessmentForecastRequest(routeSetId!, interval, signal);
      const forecasts = await fetchForecasts(request.forecast, signal, forecastEvents);
      return api.assess(routeSetId!, interval, forecasts, signal);
    },
    enabled: Boolean(routeSetId),
    staleTime: 10 * MINUTE,
    // While switching interval, keep showing the previous result for the same route set.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === routeSetId ? previous : undefined,
  });
}

export function useHeatmap(routeSetId: string | undefined) {
  return useQuery({
    queryKey: ['heatmap', routeSetId],
    queryFn: async ({ signal }) => {
      const request = await api.heatmapForecastRequest(routeSetId!, signal);
      const forecasts = await fetchForecasts(request.forecast, signal, forecastEvents);
      return api.heatmap(routeSetId!, request.start_utc, forecasts, signal);
    },
    enabled: Boolean(routeSetId),
    staleTime: 15 * MINUTE,
  });
}
