import { Badge } from "@/components/ui/badge";
import {
  AlertCircle,
  AlertTriangle,
  Bell,
  Bug,
  Info,
  Zap
} from "lucide-react";
import { InfiniteLogLoader } from "./InfiniteLogLoader";
import type { LogEntry } from "./log-viewer-context";
import { useLogViewer } from "./useLogViewer";

// Log level icon mapping for accessibility
function getLogIcon(level?: string) {
  const normalizedLevel = level?.toLowerCase();
  switch (normalizedLevel) {
    case "error":
    case "3":
      return AlertCircle;
    case "warn":
    case "warning":
    case "4":
      return AlertTriangle;
    case "info":
    case "6":
      return Info;
    case "debug":
    case "7":
      return Bug;
    case "critical":
    case "2":
      return Zap;
    case "notice":
    case "5":
      return Bell;
    default:
      return Info;
  }
}

// Get CSS custom properties for log levels with better contrast
function getLogStyle(level?: string): React.CSSProperties {
  const normalizedLevel = level?.toLowerCase();
  switch (normalizedLevel) {
    case "error":
    case "3":
      return {
        backgroundColor: 'var(--log-error)',
        color: 'white',
        borderColor: 'var(--log-error)',
        fontWeight: '600'
      };
    case "warn":
    case "warning":
    case "4":
      return {
        backgroundColor: 'var(--log-warning)',
        color: 'black',
        borderColor: 'var(--log-warning)',
        fontWeight: '600'
      };
    case "info":
    case "6":
      return {
        backgroundColor: 'var(--log-info)',
        color: 'white',
        borderColor: 'var(--log-info)',
        fontWeight: '500'
      };
    case "debug":
    case "7":
      return {
        backgroundColor: 'var(--log-debug)',
        color: 'white',
        borderColor: 'var(--log-debug)',
        fontWeight: '400'
      };
    case "critical":
    case "2":
      return {
        backgroundColor: 'var(--log-critical)',
        color: 'white',
        borderColor: 'var(--log-critical)',
        fontWeight: '700',
        boxShadow: '0 0 0 1px var(--log-critical), 0 0 8px var(--log-critical)'
      };
    case "notice":
    case "5":
      return {
        backgroundColor: 'var(--log-notice)',
        color: 'white',
        borderColor: 'var(--log-notice)',
        fontWeight: '500'
      };
    default:
      return {};
  }
}

// Row background for subtle visual grouping
function getLogRowBg(level?: string) {
  switch (level) {
    case "error":
    case "3":
      return "bg-log-error-bg border-l-2 border-log-error";
    case "warn":
    case "warning":
    case "4":
      return "bg-log-warning-bg border-l-2 border-log-warning";
    case "info":
    case "6":
      return "bg-log-info-bg border-l-2 border-log-info/50";
    case "debug":
    case "7":
      return "bg-log-debug-bg border-l-2 border-log-debug/50";
    case "critical":
    case "2":
      return "bg-log-critical-bg border-l-2 border-log-critical animate-pulse";
    case "notice":
    case "5":
      return "bg-log-notice-bg border-l-2 border-log-notice/50";
    default:
      return "";
  }
}

export function LogList() {
  const { logs, loading, error, clearError } = useLogViewer();


  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-40 p-4 text-center">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 max-w-lg">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-yellow-600 mt-0.5 flex-shrink-0" />
            <div className="text-left">
              <h3 className="text-sm font-medium text-yellow-800 mb-1">
                History Not Available
              </h3>
              <p className="text-sm text-yellow-700">
                {error}
              </p>
              <button
                onClick={clearError}
                className="mt-2 text-xs text-yellow-800 underline hover:text-yellow-900"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-foreground">
        Loading logs...
      </div>
    );
  }

  if (!logs.length) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-foreground">
        No logs to display.
      </div>
    );
  }

  return (
    <div className="overflow-y-auto flex-1 bg-background font-mono text-sm">
      {logs.map((log: LogEntry, i: number) => {
        const IconComponent = getLogIcon(log.level);
        const logStyle = getLogStyle(log.level);
        const isCritical = log.level === "critical" || log.level === "2";

        // Apply text color based on log level for improved readability
        const textColor = isCritical ? "text-log-critical" :
                          log.level === "error" || log.level === "3" ? "text-log-error" : "";

        return (
          <div
            key={i}
            className={`px-4 py-2 border-b flex items-start gap-2 transition-colors hover:bg-muted/50 ${getLogRowBg(log.level)} ${
              isCritical ? "animate-pulse" : ""
            }`}
          >
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              {log.timestamp}
            </span>
            <Badge
              variant="outline"
              className="shrink-0 flex items-center gap-1 border"
              style={logStyle}
            >
              <IconComponent className="w-3 h-3" aria-hidden="true" />
              <span>{log.level}</span>
            </Badge>
            {log.logger && (
              <span className="text-xs bg-muted/50 rounded px-1 py-0.5">{log.logger}</span>
            )}
            <span className={`flex-1 ${isCritical ? "font-medium" : ""} ${textColor}`}>
              {log.message}
            </span>
          </div>
        );
      })}
      <InfiniteLogLoader />
    </div>
  );
}
