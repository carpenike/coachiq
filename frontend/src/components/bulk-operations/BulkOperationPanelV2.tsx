/**
 * Enhanced Bulk Operation Panel V2 Component
 *
 * Modern bulk operations interface using domain API v1 with optimistic updates,
 * enhanced error handling, and real-time progress tracking.
 */

import type { ControlCommandSchema } from "@/api/types/domains";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useEntitySelection } from "@/hooks/domains/useEntitiesV2";
import {
  IconBulb,
  IconCheck,
  IconClock,
  IconExclamationCircle, // Fixed: was IconExclamationTriangle
  IconPower,
  IconRefresh,
  IconSettings,
  IconToggleLeft,
  IconX
} from "@tabler/icons-react";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

interface BulkOperationPanelV2Props {
  /** List of selected entity IDs */
  selectedEntityIds: string[];
  /** Callback when selection is cleared */
  onClearSelection: () => void;
  /** Callback when panel is closed */
  onClose: () => void;
  /** Optional entity data for display names */
  entities?: Record<string, { name?: string; friendly_name?: string; device_type?: string; [key: string]: unknown }>;
}

export function BulkOperationPanelV2({
  selectedEntityIds,
  onClearSelection,
  onClose,
  entities = {}
}: BulkOperationPanelV2Props) {
  const [showAdvancedControls, setShowAdvancedControls] = useState(false);
  const [brightness, setBrightness] = useState([75]);
  const [ignoreErrors, setIgnoreErrors] = useState(true);
  const [operationTimeout, setOperationTimeout] = useState([30]);

  const {
    executeBulkOperation,
    bulkOperationState: { isLoading, error, data, reset }
  } = useEntitySelection();

  // Derived state for UI display
  const selectedCount = selectedEntityIds.length;
  const hasSelection = selectedCount > 0;
  const operationInProgress = isLoading;
  const lastOperationResult = data;


  // Calculate entity type distribution for smart UI hints
  const entityTypeDistribution = useMemo(() => {
    const types: Record<string, number> = {};
    selectedEntityIds.forEach((id) => {
      const entity = entities[id];
      const deviceType = entity?.device_type || 'unknown';
      types[deviceType] = (types[deviceType] || 0) + 1;
    });
    return types;
  }, [selectedEntityIds, entities]);

  const hasLights = (entityTypeDistribution.light || 0) > 0;

  // Execute bulk operation with error handling
  const executeOperation = useCallback(
    async (command: ControlCommandSchema) => {
      if (!hasSelection) {
        toast.error("No entities selected for bulk operation");
        return;
      }

      try {
        reset(); // Clear previous operation state

        const options: { ignoreErrors: boolean; timeout?: number } = { ignoreErrors };
        if (operationTimeout[0] !== undefined) {
          options.timeout = operationTimeout[0];
        }

        executeBulkOperation(command, options);

        toast.success(`Bulk operation initiated for ${selectedCount} entities`);
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : "Unknown error occurred";
        toast.error(`Bulk operation failed: ${errorMessage}`);
      }
    },
    [hasSelection, selectedCount, executeBulkOperation, ignoreErrors, operationTimeout, reset]
  );

  // Quick action handlers
  const handleTurnAllOn = () => void executeOperation({ command: 'set', state: true });
  const handleTurnAllOff = () => void executeOperation({ command: 'set', state: false });
  const handleToggleAll = () => void executeOperation({ command: 'toggle' });
  const handleSetBrightness = () => {
    const command: ControlCommandSchema = { command: 'set' };
    if (brightness[0] !== undefined) {
      command.brightness = brightness[0];
    }
    void executeOperation(command);
  };
  const handleBrightnessUp = () => void executeOperation({ command: 'brightness_up' });
  const handleBrightnessDown = () => void executeOperation({ command: 'brightness_down' });

  // Operation result display
  const getOperationStatusDisplay = () => {
    if (!lastOperationResult) return null;

    const { success_count, failed_count, total_count } = lastOperationResult;
    const successRate = (success_count / total_count) * 100;

    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span>Last Operation Result</span>
          <Badge
            variant={failed_count === 0 ? "default" : failed_count < total_count ? "secondary" : "destructive"}
          >
            {failed_count === 0 ? "Success" : failed_count < total_count ? "Partial" : "Failed"}
          </Badge>
        </div>
        <Progress value={successRate} className="h-2" />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{success_count} succeeded, {failed_count} failed</span>
          <span>{successRate.toFixed(1)}%</span>
        </div>
      </div>
    );
  };

  if (!hasSelection) return null;

  return (
    <TooltipProvider>
      <div className="fixed bottom-4 left-1/2 transform -translate-x-1/2 z-50 w-[600px]">
        <Card className="shadow-xl border-2">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <IconCheck className="h-5 w-5 text-green-600" />
                  Bulk Operations
                </CardTitle>
                <Badge variant="secondary" className="gap-1">
                  {selectedCount} selected
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowAdvancedControls(!showAdvancedControls)}
                    >
                      <IconSettings className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Advanced Settings</TooltipContent>
                </Tooltip>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onClose}
                  className="h-8 w-8 p-0"
                >
                  <IconX className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <CardDescription>
              Control multiple entities simultaneously with enhanced error handling
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-4">
            {/* Entity Type Summary */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>Selected:</span>
              {Object.entries(entityTypeDistribution).map(([type, count]) => (
                <Badge key={type} variant="outline" className="text-xs">
                  {count} {type}{count > 1 ? 's' : ''}
                </Badge>
              ))}
            </div>

            {/* Quick Actions */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium min-w-0">Power Control:</span>
                <div className="flex gap-2">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handleTurnAllOn()}
                        disabled={operationInProgress}
                        className="gap-2"
                      >
                        <IconPower className="h-4 w-4 text-green-600" />
                        On
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Turn all selected entities on</TooltipContent>
                  </Tooltip>

                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handleTurnAllOff()}
                        disabled={operationInProgress}
                        className="gap-2"
                      >
                        <IconPower className="h-4 w-4 text-red-600" />
                        Off
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Turn all selected entities off</TooltipContent>
                  </Tooltip>

                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handleToggleAll()}
                        disabled={operationInProgress}
                        className="gap-2"
                      >
                        <IconToggleLeft className="h-4 w-4" />
                        Toggle
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Toggle all selected entities</TooltipContent>
                  </Tooltip>
                </div>
              </div>

              {/* Brightness Controls (only show if lights are selected) */}
              {hasLights && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Brightness Control:</span>
                    <div className="flex gap-2">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleBrightnessDown()}
                            disabled={operationInProgress}
                          >
                            <IconBulb className="h-4 w-4" />
                            -
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Decrease brightness</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleBrightnessUp()}
                            disabled={operationInProgress}
                          >
                            <IconBulb className="h-4 w-4" />
                            +
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Increase brightness</TooltipContent>
                      </Tooltip>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <span className="text-sm min-w-0">Set to {brightness[0]}%:</span>
                    <div className="flex-1">
                      <Slider
                        value={brightness}
                        onValueChange={setBrightness}
                        max={100}
                        step={5}
                        disabled={operationInProgress}
                        className="w-full"
                      />
                    </div>
                    <Button
                      size="sm"
                      onClick={() => void handleSetBrightness()}
                      disabled={operationInProgress}
                      variant="default"
                    >
                      Apply
                    </Button>
                  </div>
                </div>
              )}
            </div>

            {/* Advanced Controls */}
            {showAdvancedControls && (
              <>
                <Separator />
                <div className="space-y-3">
                  <h4 className="text-sm font-medium">Advanced Settings</h4>

                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <label htmlFor="ignore-errors-switch" className="text-sm">Ignore Errors</label>
                      <p className="text-xs text-muted-foreground">
                        Continue operation even if some entities fail
                      </p>
                    </div>
                    <Switch
                      id="ignore-errors-switch"
                      checked={ignoreErrors}
                      onCheckedChange={setIgnoreErrors}
                      disabled={operationInProgress}
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm">Operation Timeout: {operationTimeout[0]}s</label>
                    <Slider
                      value={operationTimeout}
                      onValueChange={setOperationTimeout}
                      min={5}
                      max={120}
                      step={5}
                      disabled={operationInProgress}
                      className="w-full"
                    />
                  </div>
                </div>
              </>
            )}

            {/* Operation Status */}
            {operationInProgress && (
              <>
                <Separator />
                <div className="flex items-center gap-2 text-sm">
                  <IconClock className="h-4 w-4 animate-spin" />
                  <span>Operation in progress...</span>
                </div>
              </>
            )}

            {/* Error Display */}
            {error && (
              <>
                <Separator />
                <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-md">
                  <IconExclamationCircle className="h-4 w-4 text-red-600" />
                  <span className="text-sm text-red-700 dark:text-red-300">
                    {error instanceof Error ? error.message : "Operation failed"}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={reset}
                    className="ml-auto h-6 w-6 p-0"
                  >
                    <IconX className="h-3 w-3" />
                  </Button>
                </div>
              </>
            )}

            {/* Last Operation Result */}
            {lastOperationResult && !operationInProgress && (
              <>
                <Separator />
                {getOperationStatusDisplay()}
              </>
            )}

            {/* Action Bar */}
            <Separator />
            <div className="flex items-center justify-between">
              <Button
                variant="ghost"
                size="sm"
                onClick={onClearSelection}
                disabled={operationInProgress}
              >
                Clear Selection
              </Button>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void executeOperation({ command: 'toggle' })}
                  disabled={operationInProgress || !hasSelection}
                  className="gap-2"
                >
                  <IconRefresh className="h-4 w-4" />
                  Refresh Status
                </Button>

                <Button
                  variant="default"
                  size="sm"
                  onClick={onClose}
                  disabled={operationInProgress}
                >
                  Done
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  );
}
