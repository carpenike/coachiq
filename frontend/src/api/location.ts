/**
 * Location API client (/api/location) — current GPS position and trip log.
 */

import { apiDelete, apiGet, apiGetBlob, apiPost } from './client';

export interface ICurrentLocation {
  connected: boolean;
  fix: boolean;
  latitude: number | null;
  longitude: number | null;
  speed_mps: number | null;
  course_deg: number | null;
  altitude_m: number | null;
  fix_age_seconds: number | null;
  active_trip_id: number | null;
}

export interface ITrip {
  id: number;
  started_at: number;
  ended_at: number | null;
  start_latitude: number;
  start_longitude: number;
  end_latitude: number | null;
  end_longitude: number | null;
  distance_m: number;
  max_speed_mps: number;
  point_count: number;
  start_place: string | null;
  end_place: string | null;
  active: boolean;
}

export interface ITripSummaryBucket {
  trip_count: number;
  distance_m: number;
  duration_s: number;
  max_speed_mps: number;
}

export interface ITripSummary {
  all_time: ITripSummaryBucket;
  year: ITripSummaryBucket;
}

export interface ITripPoint {
  timestamp: number;
  latitude: number;
  longitude: number;
  speed_mps: number | null;
  course_deg: number | null;
  altitude_m: number | null;
}

export async function fetchCurrentLocation(): Promise<ICurrentLocation> {
  return apiGet<ICurrentLocation>('/api/location');
}

export async function fetchTrips(limit = 50): Promise<{ trips: ITrip[]; count: number }> {
  return apiGet(`/api/location/trips?limit=${limit}`);
}

export async function fetchTripPoints(
  tripId: number
): Promise<{ trip: ITrip; points: ITripPoint[] }> {
  return apiGet(`/api/location/trips/${tripId}/points`);
}

/** Fetch a trip's GPX (with auth headers) and hand it to the browser as a download. */
export async function downloadTripGpx(tripId: number): Promise<void> {
  const { blob, filename } = await apiGetBlob(`/api/location/trips/${tripId}/gpx`);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename ?? `coachiq-trip-${tripId}.gpx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export async function deleteTrip(tripId: number): Promise<void> {
  await apiDelete(`/api/location/trips/${tripId}`);
}

export async function fetchTripSummary(): Promise<ITripSummary> {
  return apiGet<ITripSummary>('/api/location/trips/summary');
}

/** Fold a trip into the one before it (a drive split by a long stop). */
export async function mergeTripWithPrevious(tripId: number): Promise<ITrip> {
  const result = await apiPost<{ merged: ITrip }>(
    `/api/location/trips/${tripId}/merge-previous`
  );
  return result.merged;
}
