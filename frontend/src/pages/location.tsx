/**
 * Location — where the RV is and where it has been.
 *
 * Live position from gpsd (via the trip log service) on a Leaflet map with
 * OpenStreetMap tiles, plus the recorded trip list. Selecting a trip draws
 * its breadcrumb polyline; every trip exports as GPX for other tools.
 */

import "leaflet/dist/leaflet.css"

import { IconDownload, IconRoute, IconSatellite } from "@tabler/icons-react"
import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { CircleMarker, MapContainer, Polyline, TileLayer, useMap } from "react-leaflet"

import {
  fetchCurrentLocation,
  fetchTripPoints,
  fetchTrips,
  tripGpxUrl,
  type ITrip,
} from "@/api/location"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

const METERS_PER_MILE = 1609.344
const MPS_TO_MPH = 2.23694

function fmtMiles(meters: number): string {
  const miles = meters / METERS_PER_MILE
  return miles >= 10 ? `${Math.round(miles)} mi` : `${miles.toFixed(1)} mi`
}

function fmtMph(mps: number | null): string {
  return mps === null ? "—" : `${Math.round(mps * MPS_TO_MPH)} mph`
}

function fmtDuration(startSeconds: number, endSeconds: number | null): string {
  if (endSeconds === null) return "in progress"
  const minutes = Math.round((endSeconds - startSeconds) / 60)
  if (minutes < 60) return `${minutes} min`
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

function fmtTripDate(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

/**
 * Keep Leaflet's internal size in sync with the container. Leaflet measures
 * once at init; if the tab/panel is laid out later (background tab, sidebar
 * toggle) it keeps painting a zero-size tile grid without this.
 */
function InvalidateOnResize() {
  const map = useMap()
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}

/** Re-fit the map when the drawn content changes. */
function FitBounds({ positions }: Readonly<{ positions: [number, number][] }>) {
  const map = useMap()
  useEffect(() => {
    map.invalidateSize()
    if (positions.length === 0) return
    if (positions.length === 1) {
      map.setView(positions[0] as [number, number], 13)
      return
    }
    map.fitBounds(positions, { padding: [30, 30] })
  }, [map, positions])
  return null
}

function gpsStatusLabel(fix: boolean, connected: boolean): string {
  if (fix) return "GPS fix"
  return connected ? "Waiting for fix" : "gpsd unreachable"
}

/** Map card: selected trail polyline + start/current markers. */
function TrailMap({
  trail,
  here,
}: Readonly<{ trail: [number, number][]; here: [number, number] | null }>) {
  let fitTargets: [number, number][] = trail
  if (fitTargets.length === 0 && here) fitTargets = [here]

  return (
    <MapContainer
      center={here ?? [39.5, -98.35]}
      zoom={here ? 13 : 4}
      className="z-0"
      style={{ height: "55vh", width: "100%" }}
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <InvalidateOnResize />
      <FitBounds positions={fitTargets} />
      {trail.length > 1 && (
        <Polyline positions={trail} pathOptions={{ color: "#2563eb", weight: 4 }} />
      )}
      {trail.length > 0 && (
        <CircleMarker
          center={trail[0] as [number, number]}
          radius={6}
          pathOptions={{ color: "#16a34a", fillColor: "#16a34a", fillOpacity: 0.9 }}
        />
      )}
      {here && (
        <CircleMarker
          center={here}
          radius={8}
          pathOptions={{ color: "#dc2626", fillColor: "#dc2626", fillOpacity: 0.9 }}
        />
      )}
    </MapContainer>
  )
}

function CurrentPositionCard() {
  const { data } = useQuery({
    queryKey: ["location", "current"],
    queryFn: fetchCurrentLocation,
    refetchInterval: 5_000,
    retry: false,
  })

  if (!data) return null
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border px-3 py-1.5 text-sm",
        data.fix
          ? "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300"
          : "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
      )}
    >
      <span className="flex items-center gap-1.5 font-medium">
        <IconSatellite className="size-4" aria-hidden />
        {gpsStatusLabel(data.fix, data.connected)}
      </span>
      {data.fix && data.latitude !== null && data.longitude !== null && (
        <>
          <span className="tabular-nums">
            {data.latitude.toFixed(5)}, {data.longitude.toFixed(5)}
          </span>
          <span className="tabular-nums">{fmtMph(data.speed_mps)}</span>
          <span>{data.active_trip_id !== null ? "Recording trip" : "Parked"}</span>
        </>
      )}
    </div>
  )
}

interface ITripRowProps {
  trip: ITrip
  selected: boolean
  onSelect: () => void
}

function TripRow({ trip, selected, onSelect }: Readonly<ITripRowProps>) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-muted",
        selected && "bg-muted"
      )}
    >
      <div className="min-w-0">
        <p className="truncate font-medium">
          {fmtTripDate(trip.started_at)}
          {trip.active && (
            <Badge variant="default" className="ml-2 text-xs">
              live
            </Badge>
          )}
        </p>
        <p className="text-xs text-muted-foreground">
          {fmtDuration(trip.started_at, trip.ended_at)} · max {fmtMph(trip.max_speed_mps)}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="font-medium tabular-nums">{fmtMiles(trip.distance_m)}</span>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 text-muted-foreground"
          aria-label="Download GPX"
          asChild
          onClick={(event) => event.stopPropagation()}
        >
          <a href={tripGpxUrl(trip.id)} download>
            <IconDownload className="size-4" />
          </a>
        </Button>
      </div>
    </button>
  )
}

export default function LocationPage() {
  const [selectedTripId, setSelectedTripId] = useState<number | null>(null)

  const { data: current } = useQuery({
    queryKey: ["location", "current"],
    queryFn: fetchCurrentLocation,
    refetchInterval: 5_000,
    retry: false,
  })
  const { data: tripData } = useQuery({
    queryKey: ["location", "trips"],
    queryFn: () => fetchTrips(50),
    refetchInterval: 60_000,
    retry: false,
  })
  const { data: pointData } = useQuery({
    queryKey: ["location", "trip-points", selectedTripId],
    queryFn: () => fetchTripPoints(selectedTripId as number),
    enabled: selectedTripId !== null,
  })

  const trips = tripData?.trips ?? []
  const trail: [number, number][] = (pointData?.points ?? []).map((point) => [
    point.latitude,
    point.longitude,
  ])
  const here: [number, number] | null =
    current?.fix && current.latitude !== null && current.longitude !== null
      ? [current.latitude, current.longitude]
      : null

  return (
    <div className="flex-1 space-y-4 p-4 pt-6 lg:px-6">
      <CurrentPositionCard />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="overflow-hidden lg:col-span-2">
          <TrailMap trail={trail} here={here} />
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <IconRoute className="size-4 text-muted-foreground" aria-hidden />
              Trips
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-[50vh] space-y-1 overflow-y-auto">
            {trips.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No trips recorded yet — breadcrumbs start the next time the coach moves.
              </p>
            )}
            {trips.map((trip) => (
              <TripRow
                key={trip.id}
                trip={trip}
                selected={selectedTripId === trip.id}
                onSelect={() =>
                  setSelectedTripId(selectedTripId === trip.id ? null : trip.id)
                }
              />
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
