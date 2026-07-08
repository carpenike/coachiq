/**
 * Mapping helpers for the live log SSE stream (GET /api/logs/stream).
 *
 * Each `logs` event's data payload is a JSON array of entries shaped
 * { timestamp, level, message, logger, service, thread } (thread may be
 * null); the viewer stores them as LogEntry objects.
 */

import type { LogEntry } from "./log-viewer-context";

/** One entry in a `logs` SSE event from GET /api/logs/stream. */
export interface IStreamLogEntry {
  timestamp?: string;
  level?: string;
  message?: string;
  logger?: string;
  service?: string;
  thread?: number | null;
}

/**
 * Map one raw SSE stream entry to the viewer's LogEntry shape:
 * `service` -> `service_name`, `thread` -> `pid`, rest 1:1.
 */
export function mapStreamEntry(raw: unknown): LogEntry {
  const entry: IStreamLogEntry = raw && typeof raw === "object" ? (raw as IStreamLogEntry) : {};
  return {
    timestamp: entry.timestamp ?? new Date().toISOString(),
    level: entry.level ?? "INFO",
    message: entry.message ?? "",
    ...(entry.logger != null ? { logger: entry.logger } : {}),
    ...(entry.service != null ? { service_name: entry.service } : {}),
    ...(entry.thread != null ? { pid: entry.thread } : {}),
    extra: { ...entry },
  };
}
