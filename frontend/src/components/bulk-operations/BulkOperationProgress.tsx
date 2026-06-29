/**
 * Bulk Operation Progress Component
 *
 * Real-time progress tracking for bulk operations with WebSocket updates.
 * Shows individual device status and overall operation progress.
 */

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { useBulkOperationProgress, useBulkOperationStatus } from "@/hooks/useBulkOperations"
import { useEntities } from "@/hooks/useEntities"
import { getEntityDisplayName } from "@/utils/entity-display"
import {
  IconAlertTriangle,
  IconCheck,
  IconClock,
  IconRefresh,
  IconX
} from "@tabler/icons-react"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

interface BulkOperationProgressProps {
  operationId: string
  onComplete?: () => void
}

export function BulkOperationProgress({ operationId, onComplete }: BulkOperationProgressProps) {
  const [isVisible, setIsVisible] = useState(true)
  const { data: operationStatus } = useBulkOperationStatus(operationId)
  const { getOperationProgress, getOperationCompletion, clearOperationData } = useBulkOperationProgress()
  const { data: entities } = useEntities()

  const progressEvents = getOperationProgress(operationId)
  const completionEvent = getOperationCompletion(operationId)

  const handleClose = useCallback(() => {
    setIsVisible(false)
    clearOperationData(operationId)
    onComplete?.()
  }, [clearOperationData, operationId, onComplete])

  // Handle completion
  useEffect(() => {
    if (completionEvent) {
      const { status, success_count, failure_count } = completionEvent

      if (status === "COMPLETED") {
        toast.success(`Bulk operation completed successfully (${success_count} devices)`)
      } else if (status === "PARTIAL_SUCCESS") {
        toast.warning(`Bulk operation partially completed: ${success_count} succeeded, ${failure_count} failed`)
      } else if (status === "FAILED") {
        toast.error(`Bulk operation failed: ${failure_count} devices failed`)
      }

      // Auto-hide after showing completion
      setTimeout(() => {
        handleClose()
      }, 3000)
    }
  }, [completionEvent, handleClose])

  const handleRetryFailed = () => {
    // TODO: Implement retry failed devices functionality
    toast.info("Retry functionality will be available in a future update")
  }

  if (!isVisible || !operationStatus) return null

  const {
    status,
    total_tasks,
    success_count,
    failure_count,
    progress_percentage,
    failed_devices,
    description
  } = operationStatus

  const isComplete = ["COMPLETED", "FAILED", "PARTIAL_SUCCESS"].includes(status)
  const hasFailures = failure_count > 0

  const getDeviceName = (deviceId: string) => {
    if (!entities) return deviceId
    const entity = entities.entities.find((item) => item.entity_id === deviceId)
    return entity ? getEntityDisplayName(entity) : deviceId
  }

  const getStatusIcon = (deviceStatus: string) => {
    switch (deviceStatus) {
      case "SUCCESS":
        return <IconCheck className="h-4 w-4 text-green-500" />
      case "FAILED":
        return <IconX className="h-4 w-4 text-red-500" />
      default:
        return <IconClock className="h-4 w-4 text-amber-500" />
    }
  }

  return (
    <div className="fixed top-4 right-4 z-50 w-96">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <IconRefresh className="h-5 w-5" />
              Bulk Operation
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClose}
              className="h-6 w-6 p-0"
            >
              <IconX className="h-4 w-4" />
            </Button>
          </div>
          <CardDescription className="truncate">
            {description || "Processing bulk operation..."}
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Overall Progress */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span>Progress</span>
              <Badge variant={isComplete ? (hasFailures ? "destructive" : "default") : "secondary"}>
                {status.replace("_", " ")}
              </Badge>
            </div>
            <Progress value={progress_percentage} className="h-2" />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{success_count + failure_count} of {total_tasks}</span>
              <span>{progress_percentage.toFixed(1)}%</span>
            </div>
          </div>

          {/* Success/Failure Summary */}
          {(success_count > 0 || failure_count > 0) && (
            <div className="flex gap-4 text-sm">
              {success_count > 0 && (
                <div className="flex items-center gap-1 text-green-600">
                  <IconCheck className="h-4 w-4" />
                  {success_count} succeeded
                </div>
              )}
              {failure_count > 0 && (
                <div className="flex items-center gap-1 text-red-600">
                  <IconX className="h-4 w-4" />
                  {failure_count} failed
                </div>
              )}
            </div>
          )}

          {/* Failed Devices Detail */}
          {hasFailures && failed_devices && failed_devices.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium flex items-center gap-2">
                  <IconAlertTriangle className="h-4 w-4 text-amber-500" />
                  Failed Devices
                </span>
                {isComplete && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRetryFailed}
                    className="text-xs"
                  >
                    Retry Failed
                  </Button>
                )}
              </div>
              <div className="max-h-32 overflow-y-auto space-y-1 border rounded-md p-2">
                {failed_devices.slice(0, 5).map((failure, index) => (
                  <div key={index} className="flex items-start gap-2 text-xs">
                    <IconX className="h-3 w-3 text-red-500 mt-0.5 flex-shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">
                        {getDeviceName(failure.device_id)}
                      </div>
                      <div className="text-muted-foreground truncate">
                        {failure.error}
                      </div>
                    </div>
                  </div>
                ))}
                {failed_devices.length > 5 && (
                  <div className="text-center text-xs text-muted-foreground py-1">
                    +{failed_devices.length - 5} more failures
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Recent Progress Events */}
          {progressEvents.length > 0 && !isComplete && (
            <div className="space-y-2">
              <span className="text-sm font-medium">Recent Updates</span>
              <div className="max-h-24 overflow-y-auto space-y-1 border rounded-md p-2">
                {progressEvents.slice(-5).reverse().map((event, index) => (
                  <div key={index} className="flex items-center gap-2 text-xs">
                    {getStatusIcon(event.status)}
                    <span className="truncate">
                      {getDeviceName(event.device_id)}
                    </span>
                    {event.error && (
                      <span className="text-red-500 truncate">
                        {event.error}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
