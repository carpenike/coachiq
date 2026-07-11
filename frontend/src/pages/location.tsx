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
  IconArrowMerge,
  IconCurrentLocation,
  IconDownload,
  IconPlayerPause,
  IconPlayerPlay,
  IconRoute,
  IconSatellite,
  IconTrash,
} from "@tabler/icons-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react"
import { CircleMarker, MapContainer, Polyline, TileLayer, useMap } from "react-leaflet"
import { toast } from "sonner"

import {
  deleteTrip,
  downloadTripGpx,
  fetchCurrentLocation,
  fetchTripPoints,
  fetchTrips,
  fetchTripSummary,
  mergeTripWithPrevious,
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

function fmtMilesLong(meters: number): string {
  return `${Math.round(meters / METERS_PER_MILE).toLocaleString()} mi`
}

/** "Nags Head, North Carolina" -> "Nags Head" (for compact A -> B titles). */
function localityOnly(place: string): string {
  return place.split(",")[0]?.trim() ?? place
}

function tripTitle(trip: ITrip): string {
  if (trip.start_place && trip.end_place) {
    return trip.start_place === trip.end_place
      ? trip.start_place
      : `${localityOnly(trip.start_place)} → ${localityOnly(trip.end_place)}`
  }
  return fmtTripDate(trip.started_at)
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

/** Keep the map centered on the coach while follow mode is on. */
function FollowHere({ here }: Readonly<{ here: [number, number] | null }>) {
  const map = useMap()
  useEffect(() => {
    if (!here) return
    map.setView(here, Math.max(map.getZoom(), 13), { animate: true })
  }, [map, here])
  return null
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
function useTripReplay(points: ITripPoint[], tripKey: number | null): ITripReplay {
  const [playing, setPlaying] = useState(false)
  const [speedIndex, setSpeedIndex] = useState(1) // 30x
  const [elapsed, setElapsed] = useState(0)

  const startTs = points[0]?.timestamp ?? 0
  const duration =
    points.length > 1 ? (points[points.length - 1] as ITripPoint).timestamp - startTs : 0
  const multiplier = REPLAY_SPEEDS.at(speedIndex) ?? 30
  const active = duration > 0

  // A different trip was selected: rewind. Keyed on the trip id, not the
  // points array identity, so background refetches don't reset the cursor.
  useEffect(() => {
    setElapsed(0)
    setPlaying(false)
  }, [tripKey])

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
    <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-2 border-t bg-card px-3 py-2 sm:grid-cols-[auto_auto_1fr_auto_auto_auto]">
      <Button
        variant={replay.playing ? "secondary" : "ghost"}
        size="icon"
        className="size-11 shrink-0"
        aria-label={replay.playing ? "Pause replay" : "Play replay"}
        aria-pressed={replay.playing}
        onClick={replay.toggle}
      >
        {replay.playing ? (
          <IconPlayerPause className="size-4" />
        ) : (
          <IconPlayerPlay className="size-4" />
        )}
      </Button>
      <span className="shrink-0 text-xs tabular-nums text-muted-foreground sm:block">
        {fmtClock(replay.startTs + replay.elapsed)}
      </span>
      <Slider
        value={[replay.elapsed]}
        max={replay.duration}
        step={1}
        onValueChange={(values) => replay.seek(values[0] ?? 0)}
        className="col-span-3 min-h-11 py-4 sm:col-span-1"
        aria-label="Replay position"
      />
      <span className="hidden shrink-0 text-xs tabular-nums text-muted-foreground sm:block">
        {fmtClock(replay.startTs + replay.duration)}
      </span>
      <span className="w-16 shrink-0 text-right text-sm font-medium tabular-nums sm:block">
        {fmtMph(replay.position?.speedMps ?? null)}
      </span>
      <Button
        variant="outline"
        size="sm"
        className="h-11 w-14 shrink-0 tabular-nums"
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
  follow,
}: Readonly<{
  trail: [number, number][]
  here: [number, number] | null
  replay: ITripReplay
  follow: boolean
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
      {follow ? <FollowHere here={here} /> : <FitBounds positions={fitTargets} />}
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
  canMerge: boolean
  onSelect: () => void
  onDelete: () => void
  onMerge: () => void
}

/** Icon button whose action needs a second tap to confirm. */
export function ConfirmingIconButton({
  icon,
  label,
  confirmLabel,
  onConfirm,
}: Readonly<{
  icon: ReactNode
  label: string
  confirmLabel: string
  onConfirm: () => void
}>) {
  const [confirming, setConfirming] = useState(false)

  // Un-arm if the second tap doesn't come.
  useEffect(() => {
    if (!confirming) return
    const id = setTimeout(() => setConfirming(false), 3_000)
    return () => clearTimeout(id)
  }, [confirming])

  return (
    <Button
      variant="ghost"
      size={confirming ? "sm" : "icon"}
      className={cn(
        "h-11 min-w-11 text-muted-foreground",
        confirming && "bg-destructive/10 text-destructive"
      )}
      aria-label={confirming ? confirmLabel : label}
      title={confirming ? confirmLabel : label}
      onClick={() => {
        if (confirming) {
          setConfirming(false)
          onConfirm()
        } else {
          setConfirming(true)
        }
      }}
    >
      {icon}
      {confirming && <span className="ml-1.5">{confirmLabel}</span>}
    </Button>
  )
}

function TripRow({
  trip,
  selected,
  canMerge,
  onSelect,
  onDelete,
  onMerge,
}: Readonly<ITripRowProps>) {
  const handleDownload = async () => {
    try {
      await downloadTripGpx(trip.id)
    } catch (error) {
      toast.error(
        `GPX download failed: ${error instanceof Error ? error.message : String(error)}`
      )
    }
  }

  const named = Boolean(trip.start_place && trip.end_place)
  return (
    <div
      className={cn(
        "flex w-full flex-col gap-2 rounded-md px-2 py-3 text-sm transition-colors hover:bg-muted sm:flex-row sm:items-center sm:justify-between",
        selected && "bg-muted"
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        className="min-h-11 min-w-0 flex-1 py-1 text-left"
      >
        <p className="break-words font-medium leading-snug">
          {tripTitle(trip)}
          {trip.active && (
            <Badge variant="default" className="ml-2 text-xs">
              live
            </Badge>
          )}
        </p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          {named && `${fmtTripDate(trip.started_at)} · `}
          {fmtDuration(trip.started_at, trip.ended_at)} · max {fmtMph(trip.max_speed_mps)}
        </p>
      </button>
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-1 self-stretch sm:shrink-0 sm:self-auto">
        <span className="mr-auto font-medium tabular-nums sm:mr-1">
          {fmtMiles(trip.distance_m)}
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="size-11 text-muted-foreground"
          aria-label="Download GPX"
          onClick={() => void handleDownload()}
        >
          <IconDownload className="size-4" />
        </Button>
        {!trip.active && canMerge && (
          <ConfirmingIconButton
            icon={<IconArrowMerge className="size-4" />}
            label="Merge into previous trip"
            confirmLabel="Tap again to merge into previous trip"
            onConfirm={onMerge}
          />
        )}
        {!trip.active && (
          <ConfirmingIconButton
            icon={<IconTrash className="size-4" />}
            label="Delete trip"
            confirmLabel="Tap again to delete trip"
            onConfirm={onDelete}
          />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const EMPTY_POINTS: ITripPoint[] = []

/** Parse a trip's stored snap-to-road geometry ("[[lat, lon], ...]") into Leaflet points. */
function parseMatchedGeometry(raw: string | null | undefined): [number, number][] | null {
  if (!raw) return null
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    const coords = parsed.filter(
      (point): point is [number, number] =>
        Array.isArray(point) &&
        point.length === 2 &&
        typeof point[0] === "number" &&
        typeof point[1] === "number"
    )
    return coords.length > 1 ? coords : null
  } catch {
    return null
  }
}

/** Map card with the follow-the-coach toggle and (for finished trips) replay. */
function MapCard({
  trail,
  here,
  replay,
  follow,
  onToggleFollow,
  hasSnapped,
  showRaw,
  onToggleRaw,
}: Readonly<{
  trail: [number, number][]
  here: [number, number] | null
  replay: ITripReplay
  follow: boolean
  onToggleFollow: () => void
  hasSnapped: boolean
  showRaw: boolean
  onToggleRaw: () => void
}>) {
  return (
    <Card className="overflow-hidden lg:col-span-2">
      <div className="relative">
        <TrailMap trail={trail} here={here} replay={replay} follow={follow} />
        {hasSnapped && (
          <Button
            variant={showRaw ? "secondary" : "default"}
            size="sm"
            className="absolute left-2 top-2 z-[1000] h-11 gap-1 px-3 shadow"
            aria-label={showRaw ? "Show snapped-to-road track" : "Show raw GPS track"}
            title={showRaw ? "Showing raw GPS — tap for snapped" : "Showing snapped — tap for raw"}
            onClick={onToggleRaw}
          >
            <IconRoute className="size-4" />
            {showRaw ? "Raw" : "Snapped"}
          </Button>
        )}
        {here && (
          <Button
            variant={follow ? "default" : "secondary"}
            size="icon"
            className="absolute right-2 top-2 z-[1000] size-11 shadow"
            aria-label={follow ? "Stop following position" : "Follow position"}
            title={follow ? "Stop following" : "Follow the coach"}
            onClick={onToggleFollow}
          >
            <IconCurrentLocation className="size-4" />
          </Button>
        )}
      </div>
      {replay.active && <ReplayBar replay={replay} />}
    </Card>
  )
}

/** Trips card: odometer summary line plus the trip list. */
function TripsCard({
  trips,
  shownTripId,
  onSelect,
  onDelete,
  onMerge,
}: Readonly<{
  trips: ITrip[]
  shownTripId: number | null
  onSelect: (tripId: number) => void
  onDelete: (tripId: number) => void
  onMerge: (tripId: number) => void
}>) {
  const { data: summary } = useQuery({
    queryKey: ["location", "trip-summary"],
    queryFn: fetchTripSummary,
    refetchInterval: 300_000,
    retry: false,
  })

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <IconRoute className="size-4 text-muted-foreground" aria-hidden />
          Trips
        </CardTitle>
        {summary && summary.all_time.trip_count > 0 && (
          <p className="text-xs text-muted-foreground">
            {fmtMilesLong(summary.all_time.distance_m)} over {summary.all_time.trip_count}{" "}
            trips
            {summary.year.trip_count > 0 &&
              ` · ${fmtMilesLong(summary.year.distance_m)} this year`}
          </p>
        )}
      </CardHeader>
      <CardContent className="max-h-[50vh] space-y-1 overflow-y-auto">
        {trips.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No trips recorded yet — breadcrumbs start the next time the coach moves.
          </p>
        )}
        {trips.map((trip, index) => (
          <TripRow
            key={trip.id}
            trip={trip}
            selected={shownTripId === trip.id}
            canMerge={index < trips.length - 1}
            onSelect={() => onSelect(trip.id)}
            onDelete={() => onDelete(trip.id)}
            onMerge={() => onMerge(trip.id)}
          />
        ))}
      </CardContent>
    </Card>
  )
}

/** Delete/merge mutations with cache invalidation and selection fix-up. */
function useTripActions(setSelectedTripId: Dispatch<SetStateAction<number | null>>) {
  const queryClient = useQueryClient()
  const invalidateTrips = () => {
    void queryClient.invalidateQueries({ queryKey: ["location", "trips"] })
    void queryClient.invalidateQueries({ queryKey: ["location", "trip-summary"] })
  }

  const deleteMutation = useMutation({
    mutationFn: deleteTrip,
    onSuccess: (_data, tripId) => {
      setSelectedTripId((prev) => (prev === tripId ? null : prev))
      invalidateTrips()
    },
    onError: (error) => {
      toast.error(
        `Failed to delete trip: ${error instanceof Error ? error.message : String(error)}`
      )
    },
  })

  const mergeMutation = useMutation({
    mutationFn: mergeTripWithPrevious,
    onSuccess: (merged, tripId) => {
      // The merged-from trip is gone; keep the combined trip on screen.
      setSelectedTripId((prev) => (prev === tripId ? merged.id : prev))
      invalidateTrips()
      void queryClient.invalidateQueries({ queryKey: ["location", "trip-points"] })
      toast.success("Merged into the previous trip")
    },
    onError: (error) => {
      toast.error(
        `Failed to merge trip: ${error instanceof Error ? error.message : String(error)}`
      )
    },
  })

  return { deleteMutation, mergeMutation }
}

/** Derived snapped/raw trail state for the shown trip (snapped preferred when available). */
function useSnappedTrail(
  rawTrail: [number, number][],
  matchedGeometry: string | null | undefined,
  tripKey: number | null,
  isLiveTrail: boolean
): {
  displayTrail: [number, number][]
  hasSnapped: boolean
  showRaw: boolean
  onToggleRaw: () => void
} {
  const [showRaw, setShowRaw] = useState(false)
  // Reset to the preferred snapped view whenever the shown trip changes.
  useEffect(() => setShowRaw(false), [tripKey])
  const snappedTrail = useMemo(() => parseMatchedGeometry(matchedGeometry), [matchedGeometry])
  // A live trail is still growing, so it is never shown snapped.
  const hasSnapped = snappedTrail !== null && !isLiveTrail
  const displayTrail =
    snappedTrail !== null && !isLiveTrail && !showRaw ? snappedTrail : rawTrail
  return { displayTrail, hasSnapped, showRaw, onToggleRaw: () => setShowRaw((prev) => !prev) }
}

export default function LocationPage() {
  const [selectedTripId, setSelectedTripId] = useState<number | null>(null)
  const [follow, setFollow] = useState(false)

  // SSE pushes location_update events straight into this cache entry;
  // the interval is only a fallback for when the stream is down.
  const { data: current } = useQuery({
    queryKey: ["location", "current"],
    queryFn: fetchCurrentLocation,
    refetchInterval: 15_000,
    retry: false,
  })
  const { data: tripData } = useQuery({
    queryKey: ["location", "trips"],
    queryFn: () => fetchTrips(50),
    refetchInterval: 60_000,
    retry: false,
  })

  // With nothing selected, show the trip being recorded right now (if any)
  // as a live, growing trail.
  const activeTripId = current?.active_trip_id ?? null
  const shownTripId = selectedTripId ?? activeTripId
  const isLiveTrail = shownTripId !== null && shownTripId === activeTripId

  const { data: pointData } = useQuery({
    queryKey: ["location", "trip-points", shownTripId],
    queryFn: () => fetchTripPoints(shownTripId as number),
    enabled: shownTripId !== null,
    refetchInterval: isLiveTrail ? 15_000 : false,
  })

  const { deleteMutation, mergeMutation } = useTripActions(setSelectedTripId)

  const points = useMemo(
    () => (shownTripId !== null ? (pointData?.points ?? EMPTY_POINTS) : EMPTY_POINTS),
    [shownTripId, pointData]
  )
  // Memoized so FitBounds doesn't re-fit on every poll/replay render.
  const trail = useMemo<[number, number][]>(
    () => points.map((point) => [point.latitude, point.longitude]),
    [points]
  )
  const { displayTrail, hasSnapped, showRaw, onToggleRaw } = useSnappedTrail(
    trail,
    pointData?.trip.matched_geometry,
    shownTripId,
    isLiveTrail
  )
  const here = useMemo<[number, number] | null>(
    () =>
      current?.fix && current.latitude !== null && current.longitude !== null
        ? [current.latitude, current.longitude]
        : null,
    [current?.fix, current?.latitude, current?.longitude]
  )

  // Replay applies to finished trips; a live trail has no fixed timeline yet.
  const replay = useTripReplay(isLiveTrail ? EMPTY_POINTS : points, shownTripId)

  return (
    <div className="flex-1 space-y-4 p-4 pt-6 lg:px-6">
      <CurrentPositionCard />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <MapCard
          trail={displayTrail}
          here={here}
          replay={replay}
          follow={follow}
          onToggleFollow={() => setFollow((prev) => !prev)}
          hasSnapped={hasSnapped}
          showRaw={showRaw}
          onToggleRaw={onToggleRaw}
        />
        <TripsCard
          trips={tripData?.trips ?? []}
          shownTripId={shownTripId}
          onSelect={(tripId) =>
            setSelectedTripId(selectedTripId === tripId ? null : tripId)
          }
          onDelete={(tripId) => deleteMutation.mutate(tripId)}
          onMerge={(tripId) => mergeMutation.mutate(tripId)}
        />
      </div>
    </div>
  )
}
