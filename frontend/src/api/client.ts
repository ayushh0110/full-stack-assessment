import type {
  Assessment,
  AssessmentForecastRequest,
  Heatmap,
  HeatmapForecastRequest,
  Interval,
  Place,
  RouteSet,
  TripInput,
} from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: Record<string, string>;

  constructor(status: number, code: string, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

/** DRF field errors can nest (`origin.lat`); keep the first message for each top-level field. */
function firstMessages(fields: unknown): Record<string, string> {
  const result: Record<string, string> = {};
  const first = (value: unknown): string | undefined => {
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return value.map(first).find(Boolean);
    if (value && typeof value === 'object') return Object.values(value).map(first).find(Boolean);
    return undefined;
  };
  if (fields && typeof fields === 'object') {
    for (const [key, value] of Object.entries(fields)) {
      const message = first(value);
      if (message) result[key] = message;
    }
  }
  return result;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(
      0,
      'network',
      "Can't reach the server. Check your connection and try again.",
    );
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(
      response.status,
      error?.code ?? 'error',
      error?.message ?? `Request failed (${response.status}).`,
      firstMessages(error?.fields),
    );
  }
  return body as T;
}

export const api = {
  geocode: (query: string, signal?: AbortSignal) =>
    request<Place[]>(`/geocode?q=${encodeURIComponent(query)}`, { signal }),
  createRouteSet: (input: TripInput) =>
    request<RouteSet>('/route-sets', { method: 'POST', body: JSON.stringify(input) }),
  assessmentForecastRequest: (id: string, interval: Interval, signal?: AbortSignal) =>
    request<AssessmentForecastRequest>(
      `/route-sets/${id}/assessment/forecast-request?interval_mi=${interval}`,
      { signal },
    ),
  assess: (id: string, interval: Interval, forecasts: unknown[], signal?: AbortSignal) =>
    request<Assessment>(`/route-sets/${id}/assessment`, {
      method: 'POST',
      body: JSON.stringify({ interval_mi: interval, forecasts }),
      signal,
    }),
  heatmapForecastRequest: (id: string, signal?: AbortSignal) =>
    request<HeatmapForecastRequest>(`/route-sets/${id}/heatmap/forecast-request`, { signal }),
  heatmap: (id: string, startUtc: string, forecasts: unknown[], signal?: AbortSignal) =>
    request<Heatmap>(`/route-sets/${id}/heatmap`, {
      method: 'POST',
      body: JSON.stringify({ start_utc: startUtc, forecasts }),
      signal,
    }),
};
