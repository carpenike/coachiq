/**
 * Victron power system API client (/api/victron).
 *
 * Control endpoints are admin-gated on the backend and write to the Cerbo GX
 * over MQTT. Validation errors (e.g. current limit outside the adjustable
 * range) come back as 422 with a human-readable detail message.
 */

import { apiGet, apiPost } from './client';

export interface IVictronStatus {
  service: string;
  healthy: boolean;
  running: boolean;
  connected: boolean;
  portal_id: string | null;
  bound_devices: Record<string, string>;
}

/** VE.Bus switch positions (vebus /Mode). */
export type InverterMode = 'on' | 'off' | 'charger_only' | 'inverter_only';

export const INVERTER_MODE_CODES: Record<InverterMode, number> = {
  charger_only: 1,
  inverter_only: 2,
  on: 3,
  off: 4,
};

export async function fetchVictronStatus(): Promise<IVictronStatus> {
  return apiGet<IVictronStatus>('/api/victron/status');
}

export async function setInverterMode(
  mode: InverterMode
): Promise<{ success: boolean; mode: number; mode_name: string }> {
  return apiPost('/api/victron/inverter/mode', { mode });
}

export async function setInputCurrentLimit(
  amps: number
): Promise<{ success: boolean; input_current_limit: number }> {
  return apiPost('/api/victron/inverter/input-current-limit', { amps });
}

export async function setGeneratorManual(
  run: boolean
): Promise<{ success: boolean; manual_start: boolean }> {
  return apiPost('/api/victron/generator/manual', { run });
}
