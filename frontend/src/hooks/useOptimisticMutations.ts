/**
 * Optimistic Mutations Hook
 *
 * Provides optimistic UI updates for entity collections returned by the
 * canonical /api/v1 entities domain hooks.
 */

/* eslint-disable sonarjs/cognitive-complexity */

import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { bulkControlEntitiesV2, controlEntityV2 } from "@/api/domains/entities";
import type { ControlCommand, ControlEntityResponse } from "@/api/types";
import type {
  BulkControlRequestSchema,
  BulkOperationResultSchema,
  ControlCommandSchema,
  EntityCollectionSchema,
  EntitySchema,
  OperationResultSchema
} from "@/api/types/domains";
import { entitiesQueryKeys } from "@/hooks/useEntities";

type EntityCollectionSnapshot = [QueryKey, EntityCollectionSchema | undefined][];

function toDomainCommand(command: ControlCommand): ControlCommandSchema {
  const parameterState = command.parameters?.state;
  const parameterBrightness = command.parameters?.brightness;

  if (command.command === "on") {
    return { command: "set", state: true };
  }
  if (command.command === "off") {
    return { command: "set", state: false };
  }
  if (command.command === "set") {
    return {
      command: "set",
      ...(typeof command.state === "boolean" && { state: command.state }),
      ...(typeof parameterState === "boolean" && { state: parameterState }),
      ...(typeof command.brightness === "number" && { brightness: command.brightness }),
      ...(typeof parameterBrightness === "number" && { brightness: parameterBrightness })
    };
  }
  if (command.command === "brightness_up" || command.command === "brightness_down") {
    return { command: command.command };
  }
  return { command: "toggle" };
}

function toLegacyControlResponse(
  result: OperationResultSchema,
  command: ControlCommand
): ControlEntityResponse {
  return {
    success: result.status === "success",
    message: result.error_message ?? "Command executed successfully",
    entity_id: result.entity_id,
    entity_type: "unknown",
    command,
    timestamp: new Date().toISOString(),
    ...(result.execution_time_ms !== undefined && result.execution_time_ms !== null && {
      execution_time_ms: result.execution_time_ms
    })
  };
}

function applyCommandState(entity: EntitySchema, command: ControlCommandSchema): EntitySchema {
  const state = { ...(entity.state ?? {}) };

  if (command.command === "set") {
    if (command.state !== undefined && command.state !== null) {
      state.state = command.state ? "on" : "off";
    }
    if (command.brightness !== undefined && command.brightness !== null) {
      state.brightness = Math.max(0, Math.min(100, command.brightness));
      if (command.state === undefined) {
        state.state = command.brightness > 0 ? "on" : "off";
      }
    }
  } else if (command.command === "toggle") {
    state.state = state.state === "on" ? "off" : "on";
  } else if (command.command === "brightness_up") {
    const currentBrightness = typeof state.brightness === "number" ? state.brightness : 0;
    const nextBrightness = Math.min(100, currentBrightness + 10);
    state.brightness = nextBrightness;
    state.state = nextBrightness > 0 ? "on" : "off";
  } else if (command.command === "brightness_down") {
    const currentBrightness = typeof state.brightness === "number" ? state.brightness : 0;
    const nextBrightness = Math.max(0, currentBrightness - 10);
    state.brightness = nextBrightness;
    state.state = nextBrightness > 0 ? "on" : "off";
  }

  return {
    ...entity,
    state,
    last_updated: new Date().toISOString()
  };
}

function snapshotEntityCollections(queryClient: QueryClient): EntityCollectionSnapshot {
  return queryClient.getQueriesData<EntityCollectionSchema>({
    queryKey: entitiesQueryKeys.collections()
  });
}

function restoreEntityCollections(
  queryClient: QueryClient,
  snapshot: EntityCollectionSnapshot | undefined
) {
  snapshot?.forEach(([queryKey, data]) => {
    queryClient.setQueryData(queryKey, data);
  });
}

function updateEntityCollections(
  queryClient: QueryClient,
  entityIds: string[],
  command: ControlCommandSchema
) {
  const ids = new Set(entityIds);
  queryClient.setQueriesData<EntityCollectionSchema>(
    { queryKey: entitiesQueryKeys.collections() },
    (collection) => {
      if (!collection) {
        return collection;
      }
      return {
        ...collection,
        entities: collection.entities.map((entity) =>
          ids.has(entity.entity_id) ? applyCommandState(entity, command) : entity
        )
      };
    }
  );
}

async function runEntityControl(
  entityId: string,
  command: ControlCommand
): Promise<ControlEntityResponse> {
  const result = await controlEntityV2(entityId, toDomainCommand(command));
  return toLegacyControlResponse(result, command);
}

function bulkRequestToDomain(request: {
  entity_ids: string[];
  command: string;
  parameters: Record<string, unknown>;
  ignore_errors?: boolean;
}): BulkControlRequestSchema {
  const command = toDomainCommand({
    command: request.command,
    parameters: request.parameters
  });
  return {
    entity_ids: request.entity_ids,
    command,
    ignore_errors: request.ignore_errors ?? true
  };
}

/** Hook for optimistic entity control with immediate UI updates. */
export function useOptimisticEntityControl() {
  const queryClient = useQueryClient();

  return useMutation<
    ControlEntityResponse,
    Error,
    { entityId: string; command: ControlCommand },
    { previousEntities?: EntityCollectionSnapshot; previousDashboard?: unknown }
  >({
    mutationFn: async ({ entityId, command }) => runEntityControl(entityId, command),

    onMutate: async ({ entityId, command }) => {
      await queryClient.cancelQueries({ queryKey: entitiesQueryKeys.collections() });
      await queryClient.cancelQueries({ queryKey: ["dashboard", "summary"] });

      const previousEntities = snapshotEntityCollections(queryClient);
      const previousDashboard = queryClient.getQueryData(["dashboard", "summary"]);
      updateEntityCollections(queryClient, [entityId], toDomainCommand(command));

      return { previousEntities, previousDashboard };
    },

    onError: (_err, variables, context) => {
      restoreEntityCollections(queryClient, context?.previousEntities);
      if (context?.previousDashboard) {
        queryClient.setQueryData(["dashboard", "summary"], context.previousDashboard);
      }
      toast.error("Control Failed", {
        description: `Failed to control ${variables.entityId}: ${_err.message}`
      });
    },

    onSuccess: (data) => {
      toast.success("Control Successful", {
        description: data.message
      });
    },

    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.collections() });
      void queryClient.invalidateQueries({ queryKey: ["dashboard", "summary"] });
    }
  });
}

/** Hook for optimistic light control with immediate brightness updates. */
export function useOptimisticLightControl() {
  const queryClient = useQueryClient();

  const useLightMutation = (
    commandFactory: (variables: { entityId: string; brightness?: number }) => ControlCommand
  ) =>
    useMutation<
      ControlEntityResponse,
      Error,
      { entityId: string; brightness?: number },
      { previousEntities?: EntityCollectionSnapshot }
    >({
      mutationFn: async (variables) => runEntityControl(variables.entityId, commandFactory(variables)),
      onMutate: async (variables) => {
        await queryClient.cancelQueries({ queryKey: entitiesQueryKeys.collections() });
        const previousEntities = snapshotEntityCollections(queryClient);
        updateEntityCollections(queryClient, [variables.entityId], toDomainCommand(commandFactory(variables)));
        return { previousEntities };
      },
      onError: (_err, variables, context) => {
        restoreEntityCollections(queryClient, context?.previousEntities);
        toast.error("Light Control Failed", {
          description: `Failed to control ${variables.entityId}`
        });
      },
      onSuccess: (data) => {
        toast.success("Light Control Complete", {
          description: data.message
        });
      },
      onSettled: () => {
        void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.collections() });
      }
    });

  const toggle = useLightMutation(() => ({ command: "toggle" }));
  const setBrightness = useLightMutation(({ brightness = 0 }) => ({
    command: "set",
    state: true,
    brightness
  }));
  const brightnessUp = useLightMutation(() => ({ command: "brightness_up" }));
  const brightnessDown = useLightMutation(() => ({ command: "brightness_down" }));

  return { toggle, setBrightness, brightnessUp, brightnessDown };
}

/** Hook for optimistic bulk operations. */
export function useOptimisticBulkControl() {
  const queryClient = useQueryClient();

  return useMutation<
    BulkOperationResultSchema,
    Error,
    { entity_ids: string[]; command: string; parameters: Record<string, unknown>; ignore_errors?: boolean },
    { previousEntities?: EntityCollectionSnapshot }
  >({
    mutationFn: async (request) => bulkControlEntitiesV2(bulkRequestToDomain(request)),

    onMutate: async (request) => {
      const domainRequest = bulkRequestToDomain(request);
      await queryClient.cancelQueries({ queryKey: entitiesQueryKeys.collections() });
      const previousEntities = snapshotEntityCollections(queryClient);
      updateEntityCollections(queryClient, request.entity_ids, domainRequest.command);
      return { previousEntities };
    },

    onError: (err, _variables, context) => {
      restoreEntityCollections(queryClient, context?.previousEntities);
      toast.error("Bulk Operation Failed", {
        description: err.message
      });
    },

    onSuccess: (data) => {
      toast.success("Bulk Operation Complete", {
        description: `${data.success_count} successful, ${data.failed_count} failed`
      });
    },

    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.collections() });
      void queryClient.invalidateQueries({ queryKey: ["dashboard", "summary"] });
    }
  });
}

/** Generic optimistic update helper for any mutation. */
export function useOptimisticMutation<TData, TError, TVariables>({
  mutationFn,
  onOptimisticUpdate,
  queryKeys = [],
  successMessage,
  errorMessage
}: {
  mutationFn: (variables: TVariables) => Promise<TData>;
  onOptimisticUpdate: (variables: TVariables, queryClient: ReturnType<typeof useQueryClient>) => unknown;
  queryKeys?: string[][];
  successMessage?: string | ((data: TData, variables: TVariables) => string);
  errorMessage?: string | ((error: TError, variables: TVariables) => string);
}) {
  const queryClient = useQueryClient();

  return useMutation<TData, TError, TVariables, { previousStates?: Record<string, unknown>; rollback?: () => void }>({
    mutationFn,

    onMutate: async (variables) => {
      await Promise.all(queryKeys.map(key => queryClient.cancelQueries({ queryKey: key })));

      const previousStates = queryKeys.reduce((acc, key) => {
        acc[key.join(".")] = queryClient.getQueryData(key);
        return acc;
      }, {} as Record<string, unknown>);

      const rollback = onOptimisticUpdate(variables, queryClient) as (() => void) | undefined;
      const result: { previousStates?: Record<string, unknown>; rollback?: () => void } = {
        previousStates
      };

      if (rollback) {
        result.rollback = rollback;
      }

      return result;
    },

    onError: (error, variables, context) => {
      if (context?.rollback) {
        context.rollback();
      } else if (context?.previousStates) {
        Object.entries(context.previousStates).forEach(([keyString, data]) => {
          const key = keyString.split(".");
          queryClient.setQueryData(key, data);
        });
      }

      const message = typeof errorMessage === "function"
        ? errorMessage(error, variables)
        : errorMessage || "Operation failed";

      toast.error("Operation Failed", {
        description: message
      });
    },

    onSuccess: (data, variables) => {
      if (successMessage) {
        const message = typeof successMessage === "function"
          ? successMessage(data, variables)
          : successMessage;
        toast.success("Operation Successful", {
          description: message
        });
      }
    },

    onSettled: () => {
      queryKeys.forEach(key => {
        void queryClient.invalidateQueries({ queryKey: key });
      });
    }
  });
}
