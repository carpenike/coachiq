/**
 * Unit tests for the SSE log stream entry mapping (GET /api/logs/stream).
 *
 * Contract: each `logs` event's data is a JSON array of entries shaped
 * { timestamp, level, message, logger, service, thread } (thread may be
 * null); the viewer maps service -> service_name and thread -> pid.
 */

import { describe, expect, it } from "vitest";

import { mapStreamEntry } from "../log-stream";

describe("mapStreamEntry", () => {
  it("maps a full stream entry to the LogEntry shape", () => {
    const raw = {
      timestamp: "2026-07-08T12:34:56.789Z",
      level: "WARNING",
      message: "something happened",
      logger: "backend.foo",
      service: "coachiq",
      thread: 123,
    };

    const entry = mapStreamEntry(raw);

    expect(entry.timestamp).toBe("2026-07-08T12:34:56.789Z");
    expect(entry.level).toBe("WARNING");
    expect(entry.message).toBe("something happened");
    expect(entry.logger).toBe("backend.foo");
    expect(entry.service_name).toBe("coachiq");
    expect(entry.pid).toBe(123);
    expect(entry.extra).toMatchObject(raw);
  });

  it("omits pid when thread is null", () => {
    const entry = mapStreamEntry({
      timestamp: "2026-07-08T00:00:00Z",
      level: "INFO",
      message: "no thread",
      logger: "backend.bar",
      service: "coachiq",
      thread: null,
    });

    expect(entry.pid).toBeUndefined();
    expect("pid" in entry).toBe(false);
  });

  it("applies defaults for missing fields", () => {
    const entry = mapStreamEntry({});

    expect(typeof entry.timestamp).toBe("string");
    expect(entry.timestamp.length).toBeGreaterThan(0);
    expect(entry.level).toBe("INFO");
    expect(entry.message).toBe("");
    expect(entry.logger).toBeUndefined();
    expect(entry.service_name).toBeUndefined();
    expect(entry.pid).toBeUndefined();
  });

  it("tolerates non-object entries", () => {
    const entry = mapStreamEntry("garbage");

    expect(entry.level).toBe("INFO");
    expect(entry.message).toBe("");
  });
});
