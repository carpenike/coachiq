import { CoachEventStream, type StreamState } from "@/api/sse";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { mapStreamEntry } from "./log-stream";
import { LogViewerContext } from "./useLogViewer";

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  service_name?: string;
  logger?: string;
  pid?: number;
  extra?: Record<string, unknown>;
}

export interface LogFilters {
  search?: string;
  level?: string;
  module?: string;
}

// Add configuration interface for buffer management
export interface LogViewerConfig {
  maxBufferSize?: number;
  maxHistorySize?: number;
  autoScrollThreshold?: number;
  retentionTimeMs?: number;
}

export interface LogViewerContextType {
  logs: LogEntry[];
  rawLogs: LogEntry[];
  loading: boolean;
  filters: LogFilters;
  updateFilters: (filters: Partial<LogFilters>) => void;
  clearLogs: () => void;
  pauseStream: () => void;
  resumeStream: () => void;
  isPaused: boolean;
  fetchMore: () => Promise<void>;
  hasMore: boolean;
  mode: "live" | "history";
  setMode: (mode: "live" | "history") => void;
  connectionStatus: "connected" | "connecting" | "disconnected" | "error";
  reconnect: () => void;
  error: string | null;
  clearError: () => void;
}

interface LogViewerProviderProps {
  apiEndpoint: string;
  initialFilters?: LogFilters;
  config?: LogViewerConfig;
  children: React.ReactNode;
}

// Default configuration with memory-conscious settings
const DEFAULT_CONFIG: Required<LogViewerConfig> = {
  maxBufferSize: 1000,     // Maximum logs in live buffer
  maxHistorySize: 5000,    // Maximum logs in history mode
  autoScrollThreshold: 100, // Auto-scroll when within N items of bottom
  retentionTimeMs: 300000,  // 5 minutes retention for old logs
};

export function LogViewerProvider({
  apiEndpoint,
  initialFilters,
  config = DEFAULT_CONFIG,
  children,
}: LogViewerProviderProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<LogFilters>(initialFilters || {});
  const [isPaused, setIsPaused] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [mode, setMode] = useState<"live" | "history">("live");
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historyUnavailable, setHistoryUnavailable] = useState(false);

  // Use a ref to track historyUnavailable to avoid circular dependency
  const historyUnavailableRef = useRef(historyUnavailable);
  historyUnavailableRef.current = historyUnavailable;

  // Live log stream: SSE (GET `${apiEndpoint}/stream`) over the same
  // fetch-based client the app's /api/events channel uses (auth + reconnect
  // handled by CoachEventStream).
  const [streamState, setStreamState] = useState<StreamState>("closed");
  const streamRef = useRef<CoachEventStream | null>(null);

  // Refs keep the stream's event handler referentially stable while still
  // seeing the latest pause flag and buffer cap.
  const isPausedRef = useRef(isPaused);
  isPausedRef.current = isPaused;
  const maxBufferSizeRef = useRef(config.maxBufferSize);
  maxBufferSizeRef.current = config.maxBufferSize;

  // Each `logs` event carries a JSON array of entries (the first one on
  // connect is a backfill batch of up to 100 recent entries).
  const handleStreamEvent = useCallback((event: string, data: unknown) => {
    if (event !== "logs") return;
    if (isPausedRef.current) return;
    setLoading(false);
    if (!Array.isArray(data) || data.length === 0) return;

    const incoming = data.map(mapStreamEntry);
    // The live buffer is newest-first; batches arrive oldest-first, so
    // reverse before prepending (timestamp check keeps this defensive).
    const firstTs = incoming[0]?.timestamp ?? "";
    const lastTs = incoming[incoming.length - 1]?.timestamp ?? "";
    if (firstTs <= lastTs) incoming.reverse();

    setLogs((prev) => {
      const updatedLogs = [...incoming, ...prev];
      return updatedLogs.slice(0, maxBufferSizeRef.current);
    });
  }, []);

  const connectStream = useCallback(() => {
    streamRef.current ??= new CoachEventStream(
      { onEvent: handleStreamEvent, onStateChange: setStreamState },
      `${apiEndpoint}/stream`
    );
    streamRef.current.start();
  }, [apiEndpoint, handleStreamEvent]);

  const disconnectStream = useCallback(() => {
    streamRef.current?.stop();
  }, []);

  // Tear the stream down on unmount.
  useEffect(() => {
    return () => {
      streamRef.current?.stop();
      streamRef.current = null;
    };
  }, []);

  // Derive connection status from the SSE stream lifecycle
  const connectionStatus: "connecting" | "connected" | "disconnected" | "error" =
    streamState === "open" ? "connected" :
    streamState === "connecting" ? "connecting" :
    streamState === "down" || streamState === "auth-failed" ? "error" :
    "disconnected";

  // Fetch historical logs
  const fetchInitialLogs = useCallback(async () => {
    if (historyUnavailableRef.current) {
      setError("Historical logs are not available on this system. This feature requires systemd/journald, which is not available on macOS or Windows development environments.");
      setLogs([]);
      setHasMore(false);
      setCursor(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiEndpoint}/history?limit=100`);
      if (!response.ok) {
        if (response.status === 501) {
          setHistoryUnavailable(true);
          setError("Historical logs are not available on this system. This feature requires systemd/journald, which is not available on macOS or Windows development environments.");
          setLogs([]);
          setHasMore(false);
          setCursor(null);
          return;
        }
        if (response.status === 404) {
          setHistoryUnavailable(true);
          setError("Log history feature is not enabled or not available.");
          setLogs([]);
          setHasMore(false);
          setCursor(null);
          return;
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const data = await response.json();
      setLogs(data.entries?.slice(0, config.maxHistorySize) || []);
      setHasMore(data.has_more || false);
      setCursor(data.next_cursor || null);
      setHistoryUnavailable(false);
    } catch (error) {
      console.error("Error fetching logs:", error);
      if (error instanceof Error) {
        setError(`Failed to fetch logs: ${error.message}`);
      } else {
        setError("Failed to fetch logs: Unknown error occurred");
      }
      setLogs([]);
      setHasMore(false);
      setCursor(null);
    } finally {
      setLoading(false);
    }
  }, [apiEndpoint, config.maxHistorySize]);

  // Handle mode switching
  useEffect(() => {
    if (mode === "live") {
      setLogs([]);
      setCursor(null);
      setHasMore(true);
      setError(null);
      setHistoryUnavailable(false);
      connectStream();
    } else {
      disconnectStream();
      void fetchInitialLogs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, connectStream, disconnectStream]);

  // Filtering logic with useMemo (no setFilteredLogs or useEffect loop)
  const filteredLogs = useMemo(() => {
    let filtered = [...logs];
    if (filters.level) {
      const levelMap: Record<string, string[]> = {
        "0": ["0", "emerg", "emergency"],
        "1": ["1", "alert"],
        "2": ["2", "crit", "critical"],
        "3": ["3", "err", "error"],
        "4": ["4", "warn", "warning"],
        "5": ["5", "notice"],
        "6": ["6", "info"],
        "7": ["7", "debug"],
      };
      const textToNumericMap: Record<string, string> = {
        "emerg": "0", "emergency": "0",
        "alert": "1",
        "crit": "2", "critical": "2",
        "err": "3", "error": "3",
        "warn": "4", "warning": "4",
        "notice": "5",
        "info": "6",
        "debug": "7"
      };
      let allowedLevels: string[] = [];
      if (filters.level in levelMap) {
        allowedLevels = levelMap[filters.level] ?? [];
      } else {
        const normalizedFilter = filters.level.toLowerCase();
        const numericEquivalent = textToNumericMap[normalizedFilter];
        if (numericEquivalent) {
          allowedLevels = levelMap[numericEquivalent] ?? [];
        } else {
          allowedLevels = [filters.level];
        }
      }
      filtered = filtered.filter((log) => {
        const logLevelLower = log.level.toLowerCase();
        return allowedLevels.some(level => logLevelLower === level.toLowerCase());
      });
    }
    if (filters.module) {
      filtered = filtered.filter((log) => log.logger === filters.module);
    }
    if (filters.search) {
      const search = filters.search.toLowerCase();
      filtered = filtered.filter(
        (log) =>
          log.message.toLowerCase().includes(search) ||
          log.logger?.toLowerCase().includes(search)
      );
    }
    return filtered;
  }, [logs, filters]);

  const fetchMore = useCallback(async () => {
    if (!hasMore || loading || mode !== "history" || !cursor || historyUnavailable) return;
    setLoading(true);
    try {
      const response = await fetch(`${apiEndpoint}/history?cursor=${cursor}&limit=100`);
      if (!response.ok) {
        if (response.status === 501) {
          setHistoryUnavailable(true);
          setError("Historical logs are not available on this system. This feature requires systemd/journald, which is not available on macOS or Windows development environments.");
          setHasMore(false);
          return;
        }
        if (response.status === 404) {
          setHistoryUnavailable(true);
          setError("Log history feature is not enabled or not available.");
          setHasMore(false);
          return;
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const data = await response.json();
      setLogs((prev) => {
        const updatedLogs = [...prev, ...(data.entries || [])];
        return updatedLogs.slice(0, config.maxHistorySize);
      });
      setHasMore(data.has_more || false);
      setCursor(data.next_cursor || null);
    } catch (error) {
      console.error("Error fetching more logs:", error);
      if (error instanceof Error) {
        setError(`Failed to fetch more logs: ${error.message}`);
      } else {
        setError("Failed to fetch more logs: Unknown error occurred");
      }
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  }, [hasMore, loading, mode, cursor, historyUnavailable, apiEndpoint, config.maxHistorySize]);

  const updateFilters = useCallback((newFilters: Partial<LogFilters>) => {
    setFilters((prev) => ({ ...prev, ...newFilters }));
  }, []);

  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
    setHistoryUnavailable(false);
  }, []);

  const pauseStream = useCallback(() => {
    setIsPaused(true);
  }, []);

  const resumeStream = useCallback(() => {
    setIsPaused(false);
  }, []);

  const reconnect = useCallback(() => {
    // Drop any existing connection and redial immediately.
    if (streamRef.current) {
      streamRef.current.restart();
    } else {
      connectStream();
    }
  }, [connectStream]);

  const contextValue = useMemo(() => ({
    logs: filteredLogs,
    rawLogs: logs,
    loading,
    filters,
    updateFilters,
    clearLogs,
    pauseStream,
    resumeStream,
    isPaused,
    fetchMore,
    hasMore,
    mode,
    setMode,
    connectionStatus,
    reconnect,
    error,
    clearError,
  }), [filteredLogs, logs, loading, filters, updateFilters, clearLogs, pauseStream, resumeStream, isPaused, fetchMore, hasMore, mode, setMode, connectionStatus, reconnect, error, clearError]);

  return (
    <LogViewerContext.Provider value={contextValue}
    >
      {children}
    </LogViewerContext.Provider>
  );
}
