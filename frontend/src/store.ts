import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import type { Interval, RouteSet, TripInput } from './api/types';

export interface CheckpointRef {
  routeId: string;
  index: number;
}

interface AppState {
  routeSet: RouteSet | null;
  lastInput: TripInput | null;
  interval: Interval;
  selectedRouteId: string | null;
  /** Once the user picks a route themselves, the recommendation no longer moves the selection. */
  userSelectedRoute: boolean;
  /** Forecast hour on the slider, 0–48 from the start of the heatmap. */
  hour: number;
  playing: boolean;
  checkpoint: CheckpointRef | null;
  /** When the next forecast retry is due after hitting Open-Meteo's rate limit (ms), if any. */
  weatherRetryAt: number | null;

  setRouteSet: (routeSet: RouteSet, input: TripInput) => void;
  setInterval: (interval: Interval) => void;
  selectRoute: (routeId: string, byUser?: boolean) => void;
  setHour: (hour: number) => void;
  setPlaying: (playing: boolean) => void;
  openCheckpoint: (checkpoint: CheckpointRef | null) => void;
  setWeatherRetryAt: (retryAt: number) => void;
}

export const useAppStore = create<AppState>()(
  subscribeWithSelector((set) => ({
    routeSet: null,
    lastInput: null,
    interval: 25,
    selectedRouteId: null,
    userSelectedRoute: false,
    hour: 0,
    playing: false,
    checkpoint: null,
    weatherRetryAt: null,

    setRouteSet: (routeSet, input) =>
      set({
        routeSet,
        lastInput: input,
        selectedRouteId: routeSet.routes[0]?.id ?? null,
        userSelectedRoute: false,
        checkpoint: null,
      }),
    setInterval: (interval) => set({ interval, checkpoint: null }),
    selectRoute: (routeId, byUser = true) =>
      set((state) => ({
        selectedRouteId: routeId,
        userSelectedRoute: state.userSelectedRoute || byUser,
        checkpoint: state.checkpoint?.routeId === routeId ? state.checkpoint : null,
      })),
    setHour: (hour) => set({ hour }),
    setPlaying: (playing) => set({ playing }),
    openCheckpoint: (checkpoint) => set({ checkpoint }),
    setWeatherRetryAt: (weatherRetryAt) => set({ weatherRetryAt }),
  })),
);
