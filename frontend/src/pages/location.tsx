/**
 * Location — where the RV is and where it has been.
 *
 * Live position from gpsd (via the trip log service) on a Leaflet map with
 * OpenStreetMap tiles, plus the recorded trip list. Selecting a trip draws
 * its breadcrumb polyline and offers a timeline replay; every trip exports
 * as GPX for other tools.
 */

import "leaflet/dist/leaflet.css"

import {
  IconDownload,
  IconPlayerPause,
  IconPlayerPlay,
  IconRoute,
  IconSatellite,
  IconTrash,
} from "@tabler/icons-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { CircleMarker, MapContainer, Polyline, TileLayer, useMap } from "react-leaflet"
import { toast } from "sonner"

import {
  deleteTrip,
  downloadTripGpx,
  fetchCurrentLocation,
  fetchTripPoints,
  fetchTrips,
  type ITrip,
  type ITripPoint,
} from "@/api/location"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Slider } from "@/components/ui/slider"
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

function fmtClock(seconds: number): string {
  return new Date(seconds * 1000).toLocaleTimeString([], {
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

// ---------------------------------------------------------------------------
// Trip replay
// ---------------------------------------------------------------------------

const REPLAY_SPEEDS = [10, 30, 60, 120]
const REPLAY_TICK_MS = 100

interface IReplayPosition {
  lat: number
  lon: number
  speedMps: number | null
  /** Index of the breadcrumb at or before the replay cursor. */
  index: number
}

/** Position along the trail at an absolute timestamp, interpolated between breadcrumbs. */
function interpolatePosition(points: ITripPoint[], atTimestamp: number): IReplayPosition {
  let lo = 0
  let hi = points.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if ((points.at(mid) as ITripPoint).timestamp <= atTimestamp) lo = mid
    else hi = mid - 1
  }
  const from = points.at(lo) as ITripPoint
  const to = points.at(lo + 1)
  if (!to || atTimestamp <= from.timestamp) {
    return { lat: from.latitude, lon: from.longitude, speedMps: from.speed_mps, index: lo }
  }
  const span = to.timestamp - from.timestamp
  const frac = span > 0 ? Math.min(1, (atTimestamp - from.timestamp) / span) : 1
  return {
    lat: from.latitude + (to.latitude - from.latitude) * frac,
    lon: from.longitude + (to.longitude - from.longitude) * frac,
    speedMps: to.speed_mps ?? from.speed_mps,
    index: lo,
  }
}

interface ITripReplay {
  active: boolean
  playing: boolean
  elapsed: number
  duration: number
  startTs: number
  multiplier: number
  position: IReplayPosition | null
  traveled: [number, number][]
  toggle: () => void
  seek: (seconds: number) => void
  cycleSpeed: () => void
}

/** Replay cursor over a trip's breadcrumbs, advanced on a wall-clock interval. */
function useTripReplay(points: ITripPoint[]): ITripReplay {
  const [playing, setPlaying] = useState(false)
  const [speedIndex, setSpeedIndex] = useState(1) // 30x
  const [elapsed, setElapsed] = useState(0)

  const startTs = points[0]?.timestamp ?? 0
  const duration =
    points.length > 1 ? (points[points.length - 1] as ITripPoint).timestamp - startTs : 0
  const multiplier = REPLAY_SPEEDS.at(speedIndex) ?? 30
  const active = duration > 0

  // A different trip was selected: rewind.
  useEffect(() => {
    setElapsed(0)
    setPlaying(false)
  }, [points])

  useEffect(() => {
    if (!playing || duration <= 0) return
    // Advance by measured wall time, not the nominal tick, so replay speed
    // stays accurate when the browser throttles timers.
    let lastTick = performance.now()
    const id = window.setInterval(() => {
      const now = performance.now()
      const wallSeconds = (now - lastTick) / 1000
      lastTick = now
      setElapsed((prev) => Math.min(prev + wallSeconds * multiplier, duration))
    }, REPLAY_TICK_MS)
    return () => window.clearInterval(id)
  }, [playing, duration, multiplier])

  // Pause at the end of the trail.
  useEffect(() => {
    if (playing && duration > 0 && elapsed >= duration) setPlaying(false)
  }, [playing, elapsed, duration])

  const position = useMemo(
    () => (active ? interpolatePosition(points, startTs + elapsed) : null),
    [active, points, startTs, elapsed]
  )

  const traveled = useMemo<[number, number][]>(() => {
    if (!position) return []
    const path: [number, number][] = points
      .slice(0, position.index + 1)
      .map((point) => [point.latitude, point.longitude])
    path.push([position.lat, position.lon])
    return path
  }, [points, position])

  return {
    active,
    playing,
    elapsed,
    duration,
    startTs,
    multiplier,
    position,
    traveled,
    toggle: () => {
      if (!playing && elapsed >= duration) setElapsed(0) // replay from the top
      setPlaying((prev) => !prev)
    },
    seek: (seconds: number) => setElapsed(Math.min(Math.max(seconds, 0), duration)),
    cycleSpeed: () => setSpeedIndex((prev) => (prev + 1) % REPLAY_SPEEDS.length),
  }
}

function ReplayBar({ replay }: Readonly<{ replay: ITripReplay }>) {
  return (
    <div className="flex items-center gap-3 border-t bg-card px-3 py-2">
      <Button
        variant="ghost"
        size="icon"
        className="size-8 shrink-0"
        aria-label={replay.playing ? "Pause replay" : "Play replay"}
        onClick={replay.toggle}
      >
        {replay.playing ? (
          <IconPlayerPause className="size-4" />
        ) : (
          <IconPlayerPlay className="size-4" />
        )}
      </Button>
      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
        {fmtClock(replay.startTs + replay.elapsed)}
      </span>
      <Slider
        value={[replay.elapsed]}
        max={replay.duration}
        step={1}
        onValueChange={(values) => replay.seek(values[0] ?? 0)}
        className="flex-1"
        aria-label="Replay position"
      />
      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
        {fmtClock(replay.startTs + replay.duration)}
      </span>
      <span className="w-16 shrink-0 text-right text-sm font-medium tabular-nums">
        {fmtMph(replay.position?.speedMps ?? null)}
      </span>
      <Button
        variant="outline"
        size="sm"
        className="w-14 shrink-0 tabular-nums"
        onClick={replay.cycleSpeed}
        aria-label={`Replay speed ${replay.multiplier}x`}
      >
        {replay.multiplier}×
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Map
// ---------------------------------------------------------------------------

/** Map card: selected trail polyline, replay overlay, start/current markers. */
function TrailMap({
  trail,
  here,
  replay,
}: Readonly<{
  trail: [number, number][]
  here: [number, number] | null
  replay: ITripReplay
}>) {
  let fitTargets: [number, number][] = trail
  if (fitTargets.length === 0 && here) fitTargets = [here]
  const replaying = replay.active && replay.position !== null

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
        <Polyline
          positions={trail}
          pathOptions={{ color: replaying ? "#93c5fd" : "#2563eb", weight: 4 }}
        />
      )}
      {replaying && replay.traveled.length > 1 && (
        <Polyline positions={replay.traveled} pathOptions={{ color: "#2563eb", weight: 4 }} />
      )}
      {trail.length > 0 && (
        <CircleMarker
          center={trail[0] as [number, number]}
          radius={6}
          pathOptions={{ color: "#16a34a", fillColor: "#16a34a", fillOpacity: 0.9 }}
        />
      )}
      {replaying && replay.position && (
        <CircleMarker
          center={[replay.position.lat, replay.position.lon]}
          radius={7}
          pathOptions={{ color: "#7c3aed", fillColor: "#7c3aed", fillOpacity: 0.9 }}
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

// ---------------------------------------------------------------------------
// Trip list
// ---------------------------------------------------------------------------

interface ITripRowProps {
  trip: ITrip
  selected: boolean
  onSelect: () => void
  onDelete: () => void
}

function TripRow({ trip, selected, onSelect, onDelete }: Readonly<ITripRowProps>) {
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  // Un-arm the delete confirmation if it isn't followed through.
  useEffect(() => {
    if (!confirmingDelete) return
    const id = setTimeout(() => setConfirmingDelete(false), 3_000)
    return () => clearTimeout(id)
  }, [confirmingDelete])

  const handleDownload = async () => {
    try {
      await downloadTripGpx(trip.id)
    } catch (error) {
      toast.error(
        `GPX download failed: ${error instanceof Error ? error.message : String(error)}`
      )
    }
  }

  return (
    <div
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted",
        selected && "bg-muted"
      )}
    >
      <button type="button" onClick={onSelect} className="min-w-0 flex-1 text-left">
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
      </button>
      <div className="flex shrink-0 items-center gap-1">
        <span className="mr-1 font-medium tabular-nums">{fmtMiles(trip.distance_m)}</span>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 text-muted-foreground"
          aria-label="Download GPX"
          onClick={() => void handleDownload()}
        >
          <IconDownload className="size-4" />
        </Button>
        {!trip.active && (
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              "size-7 text-muted-foreground",
              confirmingDelete && "bg-destructive/10 text-destructive"
            )}
            aria-label={confirmingDelete ? "Tap again to delete trip" : "Delete trip"}
            title={confirmingDelete ? "Tap again to delete" : "Delete trip"}
            onClick={() => {
              if (confirmingDelete) {
                setConfirmingDelete(false)
                onDelete()
              } else {
                setConfirmingDelete(true)
              }
            }}
          >
            <IconTrash className="size-4" />
          </Button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LocationPage() {
  const [selectedTripId, setSelectedTripId] = useState<number | null>(null)
  const queryClient = useQueryClient()

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

  const deleteMutation = useMutation({
    mutationFn: deleteTrip,
    onSuccess: (_data, tripId) => {
      setSelectedTripId((prev) => (prev === tripId ? null : prev))
      void queryClient.invalidateQueries({ queryKey: ["location", "trips"] })
    },
    onError: (error) => {
      toast.error(
        `Failed to delete trip: ${error instanceof Error ? error.message : String(error)}`
      )
    },
  })

  const trips = tripData?.trips ?? []
  const points = useMemo(
    () => (selectedTripId !== null ? (pointData?.points ?? []) : []),
    [selectedTripId, pointData]
  )
  // Memoized so FitBounds doesn't re-fit on every poll/replay render.
  const trail = useMemo<[number, number][]>(
    () => points.map((point) => [point.latitude, point.longitude]),
    [points]
  )
  const here = useMemo<[number, number] | null>(
    () =>
      current?.fix && current.latitude !== null && current.longitude !== null
        ? [current.latitude, current.longitude]
        : null,
    [current?.fix, current?.latitude, current?.longitude]
  )

  const replay = useTripReplay(points)

  return (
    <div className="flex-1 space-y-4 p-4 pt-6 lg:px-6">
      <CurrentPositionCard />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="overflow-hidden lg:col-span-2">
          <TrailMap trail={trail} here={here} replay={replay} />
          {replay.active && <ReplayBar replay={replay} />}
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
                onDelete={() => deleteMutation.mutate(trip.id)}
              />
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
