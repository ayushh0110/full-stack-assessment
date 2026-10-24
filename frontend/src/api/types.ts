/** Mirrors the Django API (`/api/v1`). Coordinates from the API are [lat, lon]. */

export type RiskLevel = 0 | 1 | 2 | 3 | 4;
export type Interval = 10 | 25 | 50;
export type LatLon = [number, number];

export interface Place {
  label: string;
  lat: number;
  lon: number;
  tz?: string;
}

export interface TripInput {
  origin: Place;
  destination: Place;
  departure_local: string;
  load_lb: number;
}

export interface RouteOption {
  id: string;
  via: string | null;
  distance_mi: number;
  duration_s: number;
  arrival_utc: string;
  /** How much longer than the fastest route, by time or distance (whichever is worse). */
  detour_pct: number;
  long_detour: boolean;
  eta_source: 'progress' | 'instructions' | 'proportional';
  geometry: LatLon[];
  elapsed_s: number[];
}

export interface RouteSet {
  id: string;
  origin: Place;
  destination: Place;
  origin_tz: string;
  departure_utc: string;
  load_lb: number;
  routing_gross_lb: number;
  provider: string;
  truck_aware: boolean;
  notes: string[];
  routes: RouteOption[];
}

export interface Checkpoint {
  mile: number;
  from_mi: number;
  to_mi: number;
  lat: number;
  lon: number;
  eta_utc: string;
  tz: string;
  wind_mph: number | null;
  rain_in_hr: number | null;
  snow_in_hr: number | null;
  levels: { wind: RiskLevel | null; rain: RiskLevel | null; snow: RiskLevel | null };
  level: RiskLevel | null;
  reasons: string[];
}

export interface Segment {
  level: RiskLevel | null;
  coords: LatLon[];
}

export type LevelKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel';

export interface RouteSummary {
  miles_by_level: Record<LevelKey, number>;
  unknown_mi: number;
  coverage: number;
  risk_index: number | null;
  max_level: RiskLevel | null;
}

export interface RouteAssessment {
  id: string;
  checkpoints: Checkpoint[];
  segments: Segment[];
  summary: RouteSummary;
}

export type RecommendationStatus = 'recommended' | 'no_safe_route' | 'insufficient_data';
export type Criterion =
  'no_travel_mi' | 'coverage' | 'severe_mi' | 'high_mi' | 'risk_index' | 'duration_s';

export interface ComparisonRow {
  criterion: Criterion;
  label: string;
  values: Record<string, number | null>;
  decisive: boolean;
}

export interface Exclusion {
  route_id: string;
  reason: 'incomplete' | 'no_travel';
  detail: string;
}

export interface Recommendation {
  status: RecommendationStatus;
  route_id: string | null;
  explanation: string;
  excluded: Exclusion[];
  comparison: ComparisonRow[];
}

export interface Assessment {
  route_set_id: string;
  interval_mi: Interval;
  routes: RouteAssessment[];
  recommendation: Recommendation;
}

/** What the browser should fetch from Open-Meteo; the server decides every parameter. */
export interface ForecastRequest {
  url: string;
  params: Record<string, string>;
  batch_size: number;
  locations: LatLon[];
}

export interface AssessmentForecastRequest {
  route_set_id: string;
  interval_mi: Interval;
  forecast: ForecastRequest;
}

export interface HeatmapForecastRequest {
  route_set_id: string;
  start_utc: string;
  forecast: ForecastRequest;
}

export interface Heatmap {
  route_set_id: string;
  start_utc: string;
  hours: number;
  cell_deg: [number, number];
  cells: LatLon[];
  risk: (RiskLevel | null)[][];
}
