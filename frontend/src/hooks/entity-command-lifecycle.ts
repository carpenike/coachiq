import type { QueryClient, QueryKey } from "@tanstack/react-query";

import type {
  ControlCommandSchema,
  EntityCollectionSchema,
  EntitySchema
} from "@/api/types/domains";

export type EntityCommandPhase =
  | "pending"
  | "accepted"
  | "confirmed"
  | "rejected"
  | "timeout";

export type EntityCommandOperation =
  | "power"
  | "brightness"
  | "mode"
  | "setpoint"
  | "fan"
  | "set"
  | `parameters:${string}`;

export type EntityCommandConfirmationSource = "sse" | "refetch";

interface IEntityCommandExpectation {
  command: ControlCommandSchema;
  targetPower?: boolean;
  targetBrightness?: number;
}

export interface IEntityCommandLifecycle {
  entityId: string;
  operation: EntityCommandOperation;
  phase: EntityCommandPhase;
  requestId: string;
  startedAt: string;
  updatedAt: string;
  operationId?: string;
  confirmationSource?: EntityCommandConfirmationSource;
  error?: string;
}

interface IEntityDetailSnapshot {
  entityId: string;
  queryKey: QueryKey;
  data: EntitySchema | undefined;
}

interface IEntityCacheSnapshot {
  collections: [QueryKey, EntityCollectionSchema | undefined][];
  details: IEntityDetailSnapshot[];
}

interface IEntityCommandTransactionItem {
  entityId: string;
  operation: EntityCommandOperation;
  requestId: string;
  expectation: IEntityCommandExpectation;
}

export interface IEntityCommandTransaction {
  items: IEntityCommandTransactionItem[];
  snapshot: IEntityCacheSnapshot;
  confirmationTimeoutMs: number;
}

const ENTITY_COLLECTIONS_KEY = ["entities", "collections"] as const;
const ENTITY_DETAILS_KEY = ["entities", "entity"] as const;
const ENTITY_COMMANDS_KEY = ["entities", "command-lifecycle"] as const;
const DEFAULT_CONFIRMATION_TIMEOUT_MS = 8_000;
const confirmationTimers = new WeakMap<
  QueryClient,
  Map<string, ReturnType<typeof setTimeout>>
>();
const lifecycleExpectations = new WeakMap<
  QueryClient,
  Map<string, IEntityCommandTransactionItem>
>();
let requestSequence = 0;

export const entityCommandQueryKeys = {
  all: ENTITY_COMMANDS_KEY,
  entity: (entityId: string) => [...ENTITY_COMMANDS_KEY, entityId] as const,
  operation: (entityId: string, operation: EntityCommandOperation) =>
    [...ENTITY_COMMANDS_KEY, entityId, operation] as const
};

function nextRequestId(): string {
  requestSequence += 1;
  return `${Date.now()}-${requestSequence}`;
}

function timerKey(entityId: string, operation: EntityCommandOperation): string {
  return `${entityId}:${operation}`;
}

function clearConfirmationTimer(
  client: QueryClient,
  entityId: string,
  operation: EntityCommandOperation
): void {
  const timers = confirmationTimers.get(client);
  const key = timerKey(entityId, operation);
  const timer = timers?.get(key);
  if (timer) clearTimeout(timer);
  timers?.delete(key);
}

function setLifecycle(
  client: QueryClient,
  item: IEntityCommandTransactionItem,
  phase: EntityCommandPhase,
  updates: Partial<IEntityCommandLifecycle> = {}
): boolean {
  const queryKey = entityCommandQueryKeys.operation(item.entityId, item.operation);
  const current = client.getQueryData<IEntityCommandLifecycle>(queryKey);
  if (current?.requestId !== item.requestId) return false;

  client.setQueryData<IEntityCommandLifecycle>(queryKey, {
    ...current,
    ...updates,
    phase,
    updatedAt: new Date().toISOString()
  });
  return true;
}

function readPower(entity: EntitySchema | undefined): boolean | undefined {
  const state = entity?.state ?? {};
  if (typeof state.state === "boolean") return state.state;
  if (typeof state.state === "string") {
    const value = state.state.toLowerCase();
    if (["on", "true", "active", "shed"].includes(value)) return true;
    if (["off", "false", "inactive"].includes(value)) return false;
  }
  if (typeof state.operating_status === "number") return state.operating_status > 0;
  return undefined;
}

function readBrightness(entity: EntitySchema | undefined): number | undefined {
  const state = entity?.state ?? {};
  if (typeof state.brightness === "number") return state.brightness;
  if (typeof state.operating_status === "number") return (state.operating_status / 200) * 100;
  return undefined;
}

function clampBrightness(value: number): number {
  return Math.max(0, Math.min(100, value));
}

export function getEntityCommandOperation(
  command: ControlCommandSchema
): EntityCommandOperation {
  const parameterKeys = Object.keys(command.parameters ?? {}).sort((left, right) =>
    left.localeCompare(right)
  );
  if (parameterKeys.some((key) => key.includes("setpoint"))) return "setpoint";
  if (parameterKeys.some((key) => key === "mode" || key === "operating_mode")) return "mode";
  if (parameterKeys.some((key) => key.startsWith("fan_"))) return "fan";
  if (parameterKeys.length > 0) return `parameters:${parameterKeys.join("+")}`;
  if (
    command.brightness !== undefined ||
    command.command === "brightness_up" ||
    command.command === "brightness_down"
  ) {
    return "brightness";
  }
  if (command.state !== undefined || command.command === "toggle") return "power";
  return "set";
}

function createExpectation(
  entity: EntitySchema | undefined,
  command: ControlCommandSchema
): IEntityCommandExpectation {
  let targetPower: boolean | undefined;
  let targetBrightness: number | undefined;
  const currentBrightness = readBrightness(entity);

  if (command.command === "toggle") {
    const currentPower = readPower(entity);
    if (currentPower !== undefined) targetPower = !currentPower;
  } else if (command.state !== undefined && command.state !== null) {
    targetPower = command.state;
  }

  if (command.brightness !== undefined && command.brightness !== null) {
    targetBrightness = clampBrightness(command.brightness);
    if (targetPower === undefined) targetPower = targetBrightness > 0;
  } else if (command.command === "brightness_up" && currentBrightness !== undefined) {
    targetBrightness = clampBrightness(currentBrightness + 10);
    targetPower = targetBrightness > 0;
  } else if (command.command === "brightness_down" && currentBrightness !== undefined) {
    targetBrightness = clampBrightness(currentBrightness - 10);
    targetPower = targetBrightness > 0;
  }

  return {
    command,
    ...(targetPower !== undefined && { targetPower }),
    ...(targetBrightness !== undefined && { targetBrightness })
  };
}

const MODE_CODES = new Map<string, number>([
  ["off", 0],
  ["cool", 1],
  ["heat", 2],
  ["auto", 3],
  ["fan_only", 4],
  ["aux_heat", 5]
]);

function normalizedParameterEntries(
  parameters: Record<string, string | number | boolean> | null | undefined
): [string, unknown][] {
  return Object.entries(parameters ?? {}).flatMap(([key, value]) => {
    if (key === "mode" && typeof value === "string") {
      const code = MODE_CODES.get(value);
      return code === undefined ? [[key, value]] : [["operating_mode", code]];
    }
    if (key === "setpoint_f") {
      return [
        ["setpoint_cool_f", value],
        ["setpoint_heat_f", value]
      ];
    }
    if (key === "fan_mode" && typeof value === "string") {
      return [["fan_mode", value === "auto" ? 0 : 1]];
    }
    return [[key, value]];
  });
}

export function applyEntityCommandOptimistically(
  entity: EntitySchema,
  command: ControlCommandSchema
): EntitySchema {
  const expectation = createExpectation(entity, command);
  const parameterState = Object.fromEntries(normalizedParameterEntries(command.parameters));
  const state = { ...(entity.state ?? {}), ...parameterState };

  if (expectation.targetPower !== undefined) {
    state.state = expectation.targetPower ? "on" : "off";
  }
  if (expectation.targetBrightness !== undefined) {
    state.brightness = expectation.targetBrightness;
  }

  return { ...entity, state };
}

function findCachedEntity(client: QueryClient, entityId: string): EntitySchema | undefined {
  const detail = client
    .getQueriesData<EntitySchema>({ queryKey: [...ENTITY_DETAILS_KEY, entityId] })
    .find(([, entity]) => entity !== undefined)?.[1];
  if (detail) return detail;

  const collections = client.getQueriesData<EntityCollectionSchema>({
    queryKey: ENTITY_COLLECTIONS_KEY
  });
  for (const [, collection] of collections) {
    const entity = collection?.entities.find((candidate) => candidate.entity_id === entityId);
    if (entity) return entity;
  }
  return undefined;
}

function snapshotEntityCaches(client: QueryClient, entityIds: readonly string[]): IEntityCacheSnapshot {
  const details = entityIds.flatMap((entityId) =>
    client
      .getQueriesData<EntitySchema>({ queryKey: [...ENTITY_DETAILS_KEY, entityId] })
      .map(([queryKey, data]) => ({ entityId, queryKey, data }))
  );
  return {
    collections: client.getQueriesData<EntityCollectionSchema>({
      queryKey: ENTITY_COLLECTIONS_KEY
    }),
    details
  };
}

function patchEntityCaches(
  client: QueryClient,
  entityIds: readonly string[],
  command: ControlCommandSchema
): void {
  const ids = new Set(entityIds);
  client.setQueriesData<EntityCollectionSchema>(
    { queryKey: ENTITY_COLLECTIONS_KEY },
    (collection) => {
      if (!collection || !collection.entities.some((entity) => ids.has(entity.entity_id))) {
        return collection;
      }
      return {
        ...collection,
        entities: collection.entities.map((entity) =>
          ids.has(entity.entity_id) ? applyEntityCommandOptimistically(entity, command) : entity
        )
      };
    }
  );
  entityIds.forEach((entityId) => {
    client.setQueriesData<EntitySchema>(
      { queryKey: [...ENTITY_DETAILS_KEY, entityId] },
      (entity) => (entity ? applyEntityCommandOptimistically(entity, command) : entity)
    );
  });
}

function restoreEntityCaches(
  client: QueryClient,
  transaction: IEntityCommandTransaction,
  failedEntityIds: readonly string[]
): void {
  const failedIds = new Set(failedEntityIds);
  const restoreEverything = failedIds.size === transaction.items.length;

  transaction.snapshot.details.forEach(({ entityId, queryKey, data }) => {
    if (failedIds.has(entityId)) client.setQueryData(queryKey, data);
  });

  transaction.snapshot.collections.forEach(([queryKey, previous]) => {
    if (restoreEverything) {
      client.setQueryData(queryKey, previous);
      return;
    }
    if (!previous) return;
    const previousById = new Map(previous.entities.map((entity) => [entity.entity_id, entity]));
    client.setQueryData<EntityCollectionSchema>(queryKey, (current) => {
      if (!current) return current;
      return {
        ...current,
        entities: current.entities.map((entity) => {
          if (!failedIds.has(entity.entity_id)) return entity;
          return previousById.get(entity.entity_id) ?? entity;
        })
      };
    });
  });
}

export async function beginEntityCommandLifecycle(
  client: QueryClient,
  entityIds: readonly string[],
  command: ControlCommandSchema,
  confirmationTimeoutMs = DEFAULT_CONFIRMATION_TIMEOUT_MS
): Promise<IEntityCommandTransaction> {
  await Promise.all([
    client.cancelQueries({ queryKey: ENTITY_COLLECTIONS_KEY }),
    ...entityIds.map((entityId) =>
      client.cancelQueries({ queryKey: [...ENTITY_DETAILS_KEY, entityId] })
    )
  ]);

  const snapshot = snapshotEntityCaches(client, entityIds);
  const now = new Date().toISOString();
  const operation = getEntityCommandOperation(command);
  const expectations = lifecycleExpectations.get(client) ?? new Map();
  lifecycleExpectations.set(client, expectations);
  const items = entityIds.map((entityId) => {
    const previousLifecycle = client.getQueryData<IEntityCommandLifecycle>(
      entityCommandQueryKeys.operation(entityId, operation)
    );
    if (previousLifecycle) expectations.delete(previousLifecycle.requestId);
    clearConfirmationTimer(client, entityId, operation);
    const item: IEntityCommandTransactionItem = {
      entityId,
      operation,
      requestId: nextRequestId(),
      expectation: createExpectation(findCachedEntity(client, entityId), command)
    };
    client.setQueryData<IEntityCommandLifecycle>(
      entityCommandQueryKeys.operation(entityId, operation),
      {
        entityId,
        operation,
        phase: "pending",
        requestId: item.requestId,
        startedAt: now,
        updatedAt: now
      }
    );
    expectations.set(item.requestId, item);
    return item;
  });

  patchEntityCaches(client, entityIds, command);
  return { items, snapshot, confirmationTimeoutMs };
}

function itemForEntity(
  transaction: IEntityCommandTransaction,
  entityId: string
): IEntityCommandTransactionItem | undefined {
  return transaction.items.find((item) => item.entityId === entityId);
}

export function acceptEntityCommandLifecycle(
  client: QueryClient,
  transaction: IEntityCommandTransaction,
  entityId: string,
  operationId?: string
): void {
  const item = itemForEntity(transaction, entityId);
  const current = item
    ? client.getQueryData<IEntityCommandLifecycle>(
        entityCommandQueryKeys.operation(item.entityId, item.operation)
      )
    : undefined;
  if (current?.phase === "confirmed") return;
  if (
    !item ||
    !setLifecycle(
      client,
      item,
      "accepted",
      operationId === undefined ? {} : { operationId }
    )
  ) {
    return;
  }

  const timers = confirmationTimers.get(client) ?? new Map();
  confirmationTimers.set(client, timers);
  const key = timerKey(item.entityId, item.operation);
  const timer = setTimeout(() => {
    const current = client.getQueryData<IEntityCommandLifecycle>(
      entityCommandQueryKeys.operation(item.entityId, item.operation)
    );
    if (current?.requestId !== item.requestId || current.phase !== "accepted") return;
    restoreEntityCaches(client, transaction, [item.entityId]);
    setLifecycle(client, item, "timeout", {
      error: "No matching entity state was observed before the confirmation timeout."
    });
    lifecycleExpectations.get(client)?.delete(item.requestId);
    timers.delete(key);
  }, transaction.confirmationTimeoutMs);
  timers.set(key, timer);
}

export function failEntityCommandLifecycle(
  client: QueryClient,
  transaction: IEntityCommandTransaction,
  entityIds: readonly string[],
  phase: "rejected" | "timeout",
  error?: string
): void {
  const currentIds = entityIds.filter((entityId) => {
    const item = itemForEntity(transaction, entityId);
    if (!item) return false;
    const current = client.getQueryData<IEntityCommandLifecycle>(
      entityCommandQueryKeys.operation(item.entityId, item.operation)
    );
    return (
      current?.requestId === item.requestId &&
      (current.phase === "pending" || current.phase === "accepted")
    );
  });
  if (currentIds.length === 0) return;

  restoreEntityCaches(client, transaction, currentIds);
  currentIds.forEach((entityId) => {
    const item = itemForEntity(transaction, entityId);
    if (!item) return;
    clearConfirmationTimer(client, item.entityId, item.operation);
    setLifecycle(client, item, phase, error ? { error } : {});
    lifecycleExpectations.get(client)?.delete(item.requestId);
  });
}

function numbersMatch(actual: unknown, expected: number): boolean {
  return typeof actual === "number" && Math.abs(actual - expected) < 0.6;
}

function parameterMatches(
  state: Record<string, unknown>,
  key: string,
  expected: string | number | boolean
): boolean {
  if (key === "mode" && typeof expected === "string") {
    const code = MODE_CODES.get(expected);
    return state.mode === expected || (code !== undefined && state.operating_mode === code);
  }
  if (key === "setpoint_f" && typeof expected === "number") {
    return (
      numbersMatch(state.setpoint_cool_f, expected) ||
      numbersMatch(state.setpoint_heat_f, expected)
    );
  }
  if (key === "fan_mode" && typeof expected === "string") {
    return state.fan_mode === expected || state.fan_mode === (expected === "auto" ? 0 : 1);
  }
  const actual = Reflect.get(state, key);
  return typeof expected === "number" ? numbersMatch(actual, expected) : actual === expected;
}

function entityMatchesExpectation(
  entity: EntitySchema,
  expectation: IEntityCommandExpectation
): boolean {
  const state = entity.state ?? {};
  const checks: boolean[] = [];
  if (expectation.targetPower !== undefined) {
    checks.push(readPower(entity) === expectation.targetPower);
  }
  if (expectation.targetBrightness !== undefined) {
    const brightness = readBrightness(entity);
    checks.push(
      brightness !== undefined && Math.abs(brightness - expectation.targetBrightness) < 2.6
    );
  }
  Object.entries(expectation.command.parameters ?? {}).forEach(([key, value]) => {
    checks.push(parameterMatches(state, key, value));
  });
  return checks.length > 0 && checks.every(Boolean);
}

export function reconcileEntityCommandLifecycle(
  client: QueryClient,
  entity: EntitySchema,
  source: EntityCommandConfirmationSource
): void {
  const expectations = lifecycleExpectations.get(client);
  const lifecycles = client.getQueriesData<IEntityCommandLifecycle>({
    queryKey: entityCommandQueryKeys.entity(entity.entity_id)
  });
  lifecycles.forEach(([, lifecycle]) => {
    if (!lifecycle || !["pending", "accepted"].includes(lifecycle.phase)) return;
    const item: IEntityCommandTransactionItem = {
      entityId: lifecycle.entityId,
      operation: lifecycle.operation,
      requestId: lifecycle.requestId,
      expectation: { command: { command: "set" } }
    };
    const transactionItem = expectations?.get(lifecycle.requestId);
    if (!transactionItem || !entityMatchesExpectation(entity, transactionItem.expectation)) return;
    clearConfirmationTimer(client, lifecycle.entityId, lifecycle.operation);
    setLifecycle(client, item, "confirmed", { confirmationSource: source });
    expectations?.delete(lifecycle.requestId);
  });
}
