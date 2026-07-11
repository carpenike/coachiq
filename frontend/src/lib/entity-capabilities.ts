import type {
  ControlCommandSchema,
  EntityCommand,
  EntitySchema
} from "@/api/types/domains";

export type EntityCapability =
  | "power"
  | "brightness"
  | "climate"
  | "climate_mode"
  | "fan"
  | "setpoint"
  | "heat_only"
  | "lighting"
  | "read_only";

export type EntityCapabilitySource = "server" | "compatibility-fallback";

export interface IEntityCapabilityPolicy {
  source: EntityCapabilitySource;
  isCompatibilityFallback: boolean;
  capabilities: ReadonlySet<EntityCapability>;
  rawCapabilities: readonly string[];
  supportedCommands: ReadonlySet<EntityCommand>;
  rawSupportedCommands: readonly string[];
}

const ENTITY_COMMANDS = new Set<EntityCommand>([
  "set",
  "toggle",
  "brightness_up",
  "brightness_down"
]);

const CAPABILITY_ALIASES = new Map<string, EntityCapability>([
  ["on_off", "power"],
  ["on/off", "power"],
  ["power", "power"],
  ["switch", "power"],
  ["controllable", "power"],
  ["brightness", "brightness"],
  ["dimmable", "brightness"],
  ["dimming", "brightness"],
  ["climate", "climate"],
  ["thermostat", "climate"],
  ["climate_mode", "climate_mode"],
  ["mode", "climate_mode"],
  ["fan", "fan"],
  ["fan_speed", "fan"],
  ["setpoint", "setpoint"],
  ["temperature_setpoint", "setpoint"],
  ["heat_only", "heat_only"],
  ["heating_only", "heat_only"],
  ["light", "lighting"],
  ["lighting", "lighting"],
  ["read_only", "read_only"],
  ["readonly", "read_only"]
]);

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
}

function normalizeCapabilities(values: readonly string[]): Set<EntityCapability> {
  const capabilities = new Set<EntityCapability>();
  values.forEach((value) => {
    const capability = CAPABILITY_ALIASES.get(normalizeToken(value));
    if (capability) capabilities.add(capability);
  });
  return capabilities;
}

function normalizeCommands(values: readonly string[]): Set<EntityCommand> {
  const commands = new Set<EntityCommand>();
  values.forEach((value) => {
    const command = normalizeToken(value) as EntityCommand;
    if (ENTITY_COMMANDS.has(command)) commands.add(command);
  });
  return commands;
}

function compatibilityFallback(entity: EntitySchema): IEntityCapabilityPolicy {
  const capabilities = new Set<EntityCapability>();
  const supportedCommands = new Set<EntityCommand>();
  const state = entity.state ?? {};

  if (entity.device_type === "light") {
    capabilities.add("lighting");
    capabilities.add("power");
    supportedCommands.add("set");
    supportedCommands.add("toggle");
    if (typeof state.brightness === "number" || typeof state.operating_status === "number") {
      capabilities.add("brightness");
    }
  } else if (entity.device_type === "climate") {
    capabilities.add("climate");
    capabilities.add("climate_mode");
    capabilities.add("setpoint");
    capabilities.add("fan");
    supportedCommands.add("set");
    if (entity.entity_id.includes("_heat")) capabilities.add("heat_only");
  } else if (entity.device_type === "ac_load") {
    capabilities.add("power");
    supportedCommands.add("set");
  }

  return {
    source: "compatibility-fallback",
    isCompatibilityFallback: true,
    capabilities,
    rawCapabilities: [],
    supportedCommands,
    rawSupportedCommands: []
  };
}

/**
 * Resolve server-declared entity control metadata.
 *
 * An explicitly empty server field is authoritative. The conservative legacy
 * policy is used only when both new fields are absent from the payload.
 */
export function getEntityCapabilityPolicy(entity: EntitySchema): IEntityCapabilityPolicy {
  const hasCapabilities = Object.hasOwn(entity, "capabilities");
  const hasSupportedCommands = Object.hasOwn(entity, "supported_commands");

  if (!hasCapabilities && !hasSupportedCommands) return compatibilityFallback(entity);

  const rawCapabilities = Array.isArray(entity.capabilities) ? entity.capabilities : [];
  const rawSupportedCommands = Array.isArray(entity.supported_commands)
    ? entity.supported_commands
    : [];

  return {
    source: "server",
    isCompatibilityFallback: false,
    capabilities: normalizeCapabilities(rawCapabilities),
    rawCapabilities,
    supportedCommands: normalizeCommands(rawSupportedCommands),
    rawSupportedCommands
  };
}

export function entityHasCapability(
  entity: EntitySchema,
  capability: EntityCapability
): boolean {
  return getEntityCapabilityPolicy(entity).capabilities.has(capability);
}

export function entitySupportsCommand(
  entity: EntitySchema,
  command: EntityCommand | ControlCommandSchema
): boolean {
  const commandName = typeof command === "string" ? command : command.command;
  return getEntityCapabilityPolicy(entity).supportedCommands.has(commandName);
}

export function entitySupportsPowerControl(entity: EntitySchema): boolean {
  const policy = getEntityCapabilityPolicy(entity);
  return (
    policy.capabilities.has("power") &&
    (policy.supportedCommands.has("set") || policy.supportedCommands.has("toggle"))
  );
}

export function entitySupportsBrightnessControl(entity: EntitySchema): boolean {
  const policy = getEntityCapabilityPolicy(entity);
  return (
    policy.capabilities.has("brightness") &&
    (policy.supportedCommands.has("set") ||
      policy.supportedCommands.has("brightness_up") ||
      policy.supportedCommands.has("brightness_down"))
  );
}
