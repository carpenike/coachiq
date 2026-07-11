import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LogLevelFilter } from "./LogLevelFilter";
import { ModuleFilter } from "./ModuleFilter";
// Import new enhanced components
import { AdvancedLogSearch } from "./AdvancedLogSearch";
import { EnhancedLogLevelFilter } from "./EnhancedLogLevelFilter";
import { LogExportActions } from "./LogExportActions";
import { LogPerformanceMonitor } from "./LogPerformanceMonitor";
import { useLogViewer } from "./useLogViewer";

export function LogToolbar() {
  const {
    logs,
    clearLogs,
    pauseStream,
    resumeStream,
    isPaused,
    mode,
    setMode,
    connectionStatus,
    reconnect,
  } = useLogViewer();

  // Connection status badge
  const getConnectionStatusBadge = () => {
    switch (connectionStatus) {
      case "connected":
        return <Badge variant="secondary">Connected</Badge>;
      case "connecting":
        return <Badge>Connecting...</Badge>;
      case "disconnected":
        return <Badge variant="outline">Disconnected</Badge>;
      case "error":
        return <Badge variant="destructive">Connection Error</Badge>;
      default:
        return null;
    }
  };

  const showReconnectButton = connectionStatus === "disconnected" || connectionStatus === "error";
  const streamConnected = connectionStatus === "connected";
  const shouldShowPerformanceMonitor = logs.length > 100; // Show performance monitor for larger datasets
  const shouldUseEnhancedFilters = logs.length > 50; // Use enhanced filters for better UX with more logs

  return (
    <div className="flex flex-wrap gap-2 p-2 bg-background border-b items-center">
      {/* Advanced Search Component */}
      <div className="w-full sm:w-auto sm:min-w-64">
        <AdvancedLogSearch />
      </div>

      {/* Filter Components - Use enhanced versions for larger datasets */}
      {shouldUseEnhancedFilters ? (
        <EnhancedLogLevelFilter />
      ) : (
        <LogLevelFilter />
      )}
      <ModuleFilter />

      {/* Performance Monitor - Only show for larger datasets */}
      {shouldShowPerformanceMonitor && <LogPerformanceMonitor />}

      <div className="flex-grow" />

      {/* Connection Status and Controls */}
      {mode === "live" && (
        <div className="flex gap-2 items-center">
          {getConnectionStatusBadge()}
          {showReconnectButton && (
            <Button
              variant="outline"
              size="sm"
              onClick={reconnect}
              aria-label="Reconnect live stream"
            >
              Reconnect
            </Button>
          )}
        </div>
      )}

      {/* Stream Controls */}
      {mode === "live" && streamConnected && (
        <Button
          variant="outline"
          size="sm"
          onClick={isPaused ? resumeStream : pauseStream}
          aria-label={isPaused ? "Resume log stream" : "Pause log stream"}
        >
          {isPaused ? "Resume" : "Pause"}
        </Button>
      )}

      {(mode === "history" || streamConnected) && (
        <Button
          variant="outline"
          size="sm"
          onClick={clearLogs}
          aria-label="Clear logs"
          disabled={logs.length === 0}
        >
          Clear
        </Button>
      )}

      {/* Mode Toggle */}
      <Button
        variant={mode === "live" ? "default" : "outline"}
        size="sm"
        onClick={() => setMode("live")}
        aria-pressed={mode === "live"}
      >
        Live
      </Button>
      <Button
        variant={mode === "history" ? "default" : "outline"}
        size="sm"
        onClick={() => setMode("history")}
        aria-pressed={mode === "history"}
      >
        History
      </Button>

      {/* Export Actions */}
      <LogExportActions />
    </div>
  );
}
