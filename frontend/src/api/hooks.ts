import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
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
    queryFn: ({ signal }) => api.assessment(routeSetId!, interval, signal),
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
    queryFn: ({ signal }) => api.heatmap(routeSetId!, signal),
    enabled: Boolean(routeSetId),
    staleTime: 15 * MINUTE,
  });
}
