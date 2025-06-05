import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerTrigger } from "@/components/ui/drawer";
import { useId } from "react";
import { LogViewer } from "./LogViewer";

interface LogDrawerProps {
  websocketUrl: string;
  apiEndpoint: string;
  trigger?: React.ReactNode;
  initialFilters?: Record<string, unknown>;
  asChild?: boolean;
}

export function LogDrawer({ websocketUrl, apiEndpoint, trigger = "View Logs", initialFilters, asChild = false }: LogDrawerProps) {
  const drawerId = useId();
  const drawerDescId = `${drawerId}-description`;

  return (
    <Drawer>
      <DrawerTrigger asChild={asChild} aria-describedby={drawerDescId}>
        {asChild ? (
          trigger
        ) : (
          <Button variant="outline">{trigger}</Button>
        )}
      </DrawerTrigger>
      <DrawerContent className="h-[80vh]" aria-describedby={drawerDescId}>
        <DrawerHeader>
          <DrawerTitle>System Logs</DrawerTitle>
          <p id={drawerDescId} className="sr-only">
            View real-time system logs and search through log history
          </p>
        </DrawerHeader>
        <div className="p-4 h-[calc(80vh-4rem)]">
          <LogViewer
            variant="drawer"
            websocketUrl={websocketUrl}
            apiEndpoint={apiEndpoint}
            initialFilters={initialFilters}
            useVirtualization={true}
          />
        </div>
      </DrawerContent>
    </Drawer>
  );
}
