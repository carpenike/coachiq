/**
 * Victron power-system device types. These entities are telemetry, not
 * switches: they render in the home page's Power section and are excluded
 * from the zone grid (whose DeviceRow would give them a toggle switch).
 */
export const POWER_DEVICE_TYPES = new Set([
  "inverter_charger",
  "battery",
  "solar_controller",
  "power_system",
])
