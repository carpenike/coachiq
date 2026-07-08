import { LogViewerProvider } from "./log-viewer-context";
import { LogList } from "./LogList";
import { LogToolbar } from "./LogToolbar";
import { VirtualizedLogList } from "./VirtualizedLogList";

export interface LogViewerProps {
  variant: "drawer" | "full-page";
  apiEndpoint: string;
  initialFilters?: Record<string, unknown>;
  useVirtualization?: boolean;
}

export function LogViewer({
  // variant is not used yet, so prefix with _ to avoid lint error
  variant: _variant,
  apiEndpoint,
  initialFilters,
  useVirtualization = false,
}: LogViewerProps) {
  return (
    <LogViewerProvider
      apiEndpoint={apiEndpoint}
      {...(initialFilters && { initialFilters })}
    >
      <div className="flex flex-col h-full">
        <LogToolbar />
        {useVirtualization ? <VirtualizedLogList /> : <LogList />}
      </div>
    </LogViewerProvider>
  );
}
