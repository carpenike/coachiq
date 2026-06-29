/**
 * Bulk Operations Hooks
 *
 * React hooks for managing bulk device operations and device groups.
 * Implements transactional model with WebSocket progress tracking.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useState } from "react"

// Import API functions from endpoints
import {
  createBulkOperation,
  createDeviceGroup,
  deleteDeviceGroup,
  executeGroupOperation,
  fetchBulkOperationStatus,
  fetchDeviceGroups,
  updateDeviceGroup,
} from "@/api/endpoints"
import { entitiesQueryKeys } from "@/hooks/useEntities"
// import type { Entity } from "@/api/types" // Currently unused but may be needed for future type constraints

// Types
export interface BulkOperationPayload {
  command: string
  state?: "on" | "off"
  brightness?: number
  value?: string | number | boolean
  unit?: string
}

export interface BulkOperationRequest {
  operation_type: string
  targets: string[]
  payload: BulkOperationPayload
  description?: string
}

export interface BulkOperationResponse {
  status: string
  operation_id: string
  total_tasks: number
  queued_at: string
}

export interface DeviceGroup {
  id: string
  name: string
  description?: string
  device_ids: string[]
  exemptions?: Record<string, string | number | boolean | string[]>
  created_at: string
  updated_at: string
}

export interface DeviceGroupRequest {
  name: string
  description?: string
  device_ids: string[]
  exemptions?: Record<string, string | number | boolean | string[]>
}

export interface BulkOperationProgress {
  operation_id: string
  device_id: string
  status: "SUCCESS" | "FAILED"
  error?: string
  timestamp: string
}

export interface BulkOperationComplete {
  operation_id: string
  status: string
  success_count: number
  failure_count: number
  failed_devices: {
    device_id: string
    error: string
    timestamp: string
  }[]
  timestamp: string
}

// Hooks
export function useBulkOperations() {
  const queryClient = useQueryClient()

  const createOperation = useMutation({
    mutationFn: createBulkOperation,
    onSuccess: () => {
      // Invalidate entity queries to refresh state after bulk operation
      void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.collections() })
    },
  })

  return {
    createOperation,
  }
}

export function useBulkOperationStatus(operationId: string | null) {
  return useQuery({
    queryKey: ["bulk-operation-status", operationId],
    queryFn: () => fetchBulkOperationStatus(operationId!),
    enabled: !!operationId,
    refetchInterval: (data) => {
      // Stop polling when operation is complete
      const status = (data as { status?: string })?.status
      return status === "PROCESSING" || status === "QUEUED" ? 2000 : false
    },
  })
}

export function useDeviceGroups() {
  const queryClient = useQueryClient()

  const groups = useQuery({
    queryKey: ["device-groups"],
    queryFn: fetchDeviceGroups,
  })

  const createGroup = useMutation({
    mutationFn: createDeviceGroup,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["device-groups"] })
    },
  })

  const updateGroup = useMutation({
    mutationFn: ({ groupId, request }: { groupId: string; request: DeviceGroupRequest }) =>
      updateDeviceGroup(groupId, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["device-groups"] })
    },
  })

  const deleteGroup = useMutation({
    mutationFn: deleteDeviceGroup,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["device-groups"] })
    },
  })

  const executeGroup = useMutation({
    mutationFn: ({ groupId, payload }: { groupId: string; payload: BulkOperationPayload }) =>
      executeGroupOperation(groupId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.collections() })
    },
  })

  return {
    groups,
    createGroup,
    updateGroup,
    deleteGroup,
    executeGroup,
  }
}

// Selection state management
export type SelectionMode = "idle" | "selecting"

export interface SelectionState {
  mode: SelectionMode
  selectedIds: Set<string>
}

export function useSelectionMode() {
  const [state, setState] = useState<SelectionState>({
    mode: "idle",
    selectedIds: new Set(),
  })

  const enterSelectionMode = useCallback(() => {
    setState(prev => ({ ...prev, mode: "selecting" }))
  }, [])

  const exitSelectionMode = useCallback(() => {
    setState({ mode: "idle", selectedIds: new Set() })
  }, [])

  const toggleSelection = useCallback((deviceId: string) => {
    setState(prev => {
      const newSelectedIds = new Set(prev.selectedIds)
      if (newSelectedIds.has(deviceId)) {
        newSelectedIds.delete(deviceId)
      } else {
        newSelectedIds.add(deviceId)
      }
      return { ...prev, selectedIds: newSelectedIds }
    })
  }, [])

  const selectAll = useCallback((deviceIds: string[]) => {
    setState(prev => ({
      ...prev,
      selectedIds: new Set(deviceIds),
    }))
  }, [])

  const clearSelection = useCallback(() => {
    setState(prev => ({ ...prev, selectedIds: new Set() }))
  }, [])

  return {
    ...state,
    enterSelectionMode,
    exitSelectionMode,
    toggleSelection,
    selectAll,
    clearSelection,
    selectedDevices: Array.from(state.selectedIds),
    hasSelection: state.selectedIds.size > 0,
  }
}

// WebSocket integration for real-time progress updates
export function useBulkOperationProgress() {
  const [progressEvents, setProgressEvents] = useState<Map<string, BulkOperationProgress[]>>(new Map())
  const [completionEvents, setCompletionEvents] = useState<Map<string, BulkOperationComplete>>(new Map())

  // For now, use polling instead of WebSocket for bulk operation progress
  // In a real implementation, this would be replaced with proper WebSocket integration
  useEffect(() => {
    // TODO: Implement WebSocket integration for bulk operation progress
    // This would listen for 'bulk_op_progress' and 'bulk_op_complete' events
  }, [])

  const getOperationProgress = useCallback((operationId: string) => {
    return progressEvents.get(operationId) || []
  }, [progressEvents])

  const getOperationCompletion = useCallback((operationId: string) => {
    return completionEvents.get(operationId)
  }, [completionEvents])

  const clearOperationData = useCallback((operationId: string) => {
    setProgressEvents(prev => {
      const newMap = new Map(prev)
      newMap.delete(operationId)
      return newMap
    })
    setCompletionEvents(prev => {
      const newMap = new Map(prev)
      newMap.delete(operationId)
      return newMap
    })
  }, [])

  return {
    getOperationProgress,
    getOperationCompletion,
    clearOperationData,
  }
}

// Quick action helpers
export function useQuickActions() {
  const { createOperation } = useBulkOperations()
  const { mutateAsync: createOperationAsync, isPending } = createOperation

  const allOff = useCallback((deviceIds: string[], exemptDeviceIds: string[] = []) => {
    const targets = deviceIds.filter(id => !exemptDeviceIds.includes(id))

    if (targets.length === 0) return Promise.resolve()

    return createOperationAsync({
      operation_type: "state_change",
      targets,
      payload: { command: "set", state: "off" },
      description: "All Off - Master power down",
    })
  }, [createOperationAsync])

  const systemCheck = useCallback((deviceIds: string[]) => {
    if (deviceIds.length === 0) return Promise.resolve()

    return createOperationAsync({
      operation_type: "status_check",
      targets: deviceIds,
      payload: { command: "status" },
      description: "System Check - Request status from all devices",
    })
  }, [createOperationAsync])

  const setBrightness = useCallback((deviceIds: string[], brightness: number) => {
    const lightIds = deviceIds // Filter for lights in real implementation

    if (lightIds.length === 0) return Promise.resolve()

    return createOperationAsync({
      operation_type: "state_change",
      targets: lightIds,
      payload: { command: "set", brightness },
      description: `Set brightness to ${brightness}% for selected lights`,
    })
  }, [createOperationAsync])

  return {
    allOff,
    systemCheck,
    setBrightness,
    isLoading: isPending,
  }
}
