/**
 * Power — Victron power system telemetry and controls.
 *
 * Telemetry reuses the home page's PowerSection cards. Controls write to the
 * Cerbo GX through the admin-gated /api/victron endpoints: VE.Bus mode
 * changes require an explicit confirmation dialog (they can cut AC output);
 * the shore input current limit applies from presets or a custom value and
 * is validated server-side against the range the Cerbo reports.
 */

import { IconAlertTriangle, IconPlugConnected, IconPlugConnectedX } from "@tabler/icons-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import type { EntitySchema } from "@/api/types/domains"
import {
  fetchVictronStatus,
  setGeneratorManual,
  setInputCurrentLimit,
  setInverterMode,
  type InverterMode,
} from "@/api/victron"
import { PowerSection } from "@/components/power-section"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { toast } from "@/hooks/use-toast"
import { entitiesQueryKeys, useEntities } from "@/hooks/useEntities"
import { cn } from "@/lib/utils"

const MODE_OPTIONS: {
  mode: InverterMode
  code: number
  label: string
  description: string
}[] = [
  {
    mode: "on",
    code: 3,
    label: "On",
    description:
      "Normal operation: charge the batteries when shore power is present, invert from the batteries when it is not.",
  },
  {
    mode: "charger_only",
    code: 1,
    label: "Charger only",
    description:
      "Inverting stops. AC loads are only powered while shore or generator power is present; charging continues.",
  },
  {
    mode: "inverter_only",
    code: 2,
    label: "Inverter only",
    description:
      "Charging stops. The batteries will not charge from shore power; loads run from the inverter.",
  },
  {
    mode: "off",
    code: 4,
    label: "Off",
    description:
      "The inverter and charger both stop. Coach AC output shuts down and the batteries stop charging.",
  },
]

const LIMIT_PRESETS = [15, 20, 30, 50]

/** Shared status query — controls gate on the Cerbo MQTT link, not the CAN bus. */
function useVictronStatus() {
  return useQuery({
    queryKey: ["victron", "status"],
    queryFn: fetchVictronStatus,
    refetchInterval: 30_000,
    retry: false,
  })
}

function VictronStatusChip() {
  const { data } = useVictronStatus()

  if (!data) return null
  const connected = data.connected
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm",
        connected
          ? "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300"
          : "border-red-300 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
      )}
    >
      {connected ? (
        <IconPlugConnected className="size-4" aria-hidden />
      ) : (
        <IconPlugConnectedX className="size-4" aria-hidden />
      )}
      <span className="font-medium">
        {connected ? "Cerbo GX connected" : "Cerbo GX unreachable"}
      </span>
      {data.portal_id && (
        <span className="text-xs opacity-70">portal {data.portal_id}</span>
      )}
    </div>
  )
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

interface IControlsProps {
  inverter: EntitySchema | undefined
  controlsDisabled: boolean
}

function InverterModeCard({ inverter, controlsDisabled }: Readonly<IControlsProps>) {
  const queryClient = useQueryClient()
  const [pendingMode, setPendingMode] = useState<(typeof MODE_OPTIONS)[number] | null>(null)

  const state = inverter?.state ?? {}
  const currentCode = num(state.mode)
  const modeAdjustable = num(state.mode_adjustable) !== 0

  const mutation = useMutation({
    mutationFn: (mode: InverterMode) => setInverterMode(mode),
    onSuccess: (result) => {
      toast({
        title: `Inverter/charger set to ${result.mode_name.replace(/_/g, " ")}`,
      })
      void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.all })
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Mode change failed",
        description: error.message,
      })
    },
    onSettled: () => setPendingMode(null),
  })

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Inverter/charger mode</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          {MODE_OPTIONS.map((option) => {
            const isCurrent = currentCode === option.code
            return (
              <Button
                key={option.mode}
                variant={isCurrent ? "default" : "outline"}
                disabled={
                  controlsDisabled || !modeAdjustable || mutation.isPending || isCurrent
                }
                onClick={() => setPendingMode(option)}
              >
                {option.label}
              </Button>
            )
          })}
        </div>
        {!modeAdjustable && (
          <p className="text-xs text-muted-foreground">
            The Cerbo reports the mode as not adjustable (check the physical switch
            position on the Quattros).
          </p>
        )}
      </CardContent>

      <Dialog open={pendingMode !== null} onOpenChange={(open) => !open && setPendingMode(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <IconAlertTriangle className="size-5 text-amber-500" aria-hidden />
              Switch to {pendingMode?.label}?
            </DialogTitle>
            <DialogDescription>{pendingMode?.description}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingMode(null)}>
              Cancel
            </Button>
            <Button
              disabled={mutation.isPending}
              onClick={() => pendingMode && mutation.mutate(pendingMode.mode)}
            >
              {mutation.isPending ? "Sending…" : `Switch to ${pendingMode?.label}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

function ShoreLimitCard({ inverter, controlsDisabled }: Readonly<IControlsProps>) {
  const queryClient = useQueryClient()
  const [customAmps, setCustomAmps] = useState("")

  const state = inverter?.state ?? {}
  const currentLimit = num(state.input_current_limit)
  const limitAdjustable = num(state.input_current_limit_adjustable) !== 0

  const mutation = useMutation({
    mutationFn: (amps: number) => setInputCurrentLimit(amps),
    onSuccess: (result) => {
      toast({ title: `Shore input limit set to ${result.input_current_limit} A` })
      setCustomAmps("")
      void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.all })
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Limit change failed",
        description: error.message,
      })
    },
  })

  const disabled = controlsDisabled || !limitAdjustable || mutation.isPending
  const customValue = Number(customAmps)
  const customValid = customAmps !== "" && Number.isFinite(customValue) && customValue >= 0

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-base">
          Shore input limit
          <Badge variant="secondary" className="tabular-nums">
            {currentLimit === null ? "—" : `${currentLimit} A`}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Match this to the pedestal breaker. The Quattros draw at most this much from
          shore and make up the difference from the batteries.
        </p>
        <div className="flex flex-wrap gap-2">
          {LIMIT_PRESETS.map((amps) => (
            <Button
              key={amps}
              variant={currentLimit === amps ? "default" : "outline"}
              size="sm"
              disabled={disabled || currentLimit === amps}
              onClick={() => mutation.mutate(amps)}
            >
              {amps} A
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            inputMode="decimal"
            min={0}
            placeholder="Custom amps"
            value={customAmps}
            disabled={disabled}
            onChange={(event) => setCustomAmps(event.target.value)}
            className="max-w-32"
            aria-label="Custom shore input limit in amps"
          />
          <Button
            size="sm"
            disabled={disabled || !customValid}
            onClick={() => mutation.mutate(customValue)}
          >
            Apply
          </Button>
        </div>
        {!limitAdjustable && (
          <p className="text-xs text-muted-foreground">
            The Cerbo reports the input limit as not adjustable.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

const GENERATOR_RUNNING_STATES = new Set(["running", "warm_up"])

function generatorConfirmLabel(pending: boolean, confirming: "start" | "stop" | null): string {
  if (pending) return "Sending…"
  return confirming === "start" ? "Start Generator" : "Stop Generator"
}

function GeneratorControlCard({
  generator,
  controlsDisabled,
}: Readonly<{ generator: EntitySchema | undefined; controlsDisabled: boolean }>) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState<"start" | "stop" | null>(null)

  const state = generator?.state ?? {}
  const statusLabel = typeof state.status === "string" ? state.status.replace(/_/g, " ") : "unknown"
  const isRunning = GENERATOR_RUNNING_STATES.has(String(state.status))

  const mutation = useMutation({
    mutationFn: (run: boolean) => setGeneratorManual(run),
    onSuccess: (result) => {
      toast({
        title: result.manual_start
          ? "Generator start requested"
          : "Generator stop requested",
        description: "The Cerbo's genset controller is handling the sequence.",
      })
      void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.all })
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Generator command failed",
        description: error.message,
      })
    },
    onSettled: () => setConfirming(null),
  })

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-base">
          Generator
          <Badge variant="secondary" className="capitalize">
            {statusLabel}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Manual run via the Cerbo&apos;s genset controller — its own stop conditions
          (autostart rules, quiet hours) still apply.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <Button
            disabled={controlsDisabled || mutation.isPending || isRunning}
            onClick={() => setConfirming("start")}
          >
            Start
          </Button>
          <Button
            variant="outline"
            disabled={controlsDisabled || mutation.isPending || !isRunning}
            onClick={() => setConfirming("stop")}
          >
            Stop
          </Button>
        </div>
      </CardContent>

      <Dialog open={confirming !== null} onOpenChange={(open) => !open && setConfirming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <IconAlertTriangle className="size-5 text-amber-500" aria-hidden />
              {confirming === "start" ? "Start the generator?" : "Stop the generator?"}
            </DialogTitle>
            <DialogDescription>
              {confirming === "start"
                ? "The generator will crank and start producing AC power. Make sure nothing is blocking the exhaust and the coach is clear to run it."
                : "The generator will shut down. AC loads fall back to shore power or the inverter."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
            <Button
              variant={confirming === "start" ? "default" : "destructive"}
              disabled={mutation.isPending}
              onClick={() => mutation.mutate(confirming === "start")}
            >
              {generatorConfirmLabel(mutation.isPending, confirming)}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

export default function PowerPage() {
  const { data: victronStatus } = useVictronStatus()
  const { data: entityCollection } = useEntities({ page_size: 100 })

  const entities = entityCollection?.entities ?? []
  const inverter = entities.find((entity) => entity.device_type === "inverter_charger")
  const generator = entities.find((entity) => entity.device_type === "generator")

  // Victron commands travel over the Cerbo's MQTT link (IP), independent of
  // the RV-C CAN bus — so gate on that link, not on coach CAN liveness.
  const controlsDisabled = victronStatus?.connected !== true

  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      <VictronStatusChip />

      <div className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Controls</h2>
        {controlsDisabled && (
          <p className="text-sm text-muted-foreground">
            Controls are disabled — the Cerbo GX is not reachable.
          </p>
        )}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          <InverterModeCard inverter={inverter} controlsDisabled={controlsDisabled} />
          <ShoreLimitCard inverter={inverter} controlsDisabled={controlsDisabled} />
          <GeneratorControlCard generator={generator} controlsDisabled={controlsDisabled} />
        </div>
      </div>

      <div className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Telemetry</h2>
        <PowerSection entities={entities} showTitle={false} />
      </div>
    </div>
  )
}
