/**
 * Enhanced Bulk Operation Results V2 Component
 *
 * Detailed results display for bulk operations with per-entity status,
 * error analysis, and retry capabilities.
 */

import type { BulkOperationResultSchema, OperationResultSchema } from "@/api/types/domains";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
    IconAlertTriangle,
    IconCheck,
    IconClock,
    IconExclamationCircle, // Fixed: was IconExclamationTriangle
    IconRefresh,
    IconX
} from "@tabler/icons-react";
import { useMemo } from "react";

interface BulkOperationResultsV2Props {
  /** The bulk operation result data */
  operationResult: BulkOperationResultSchema;
  /** Entity data for display names */
  entities?: Record<string, { name?: string; friendly_name?: string; [key: string]: unknown }>;
  /** Callback when retry failed entities is requested */
  onRetryFailed?: (failedEntityIds: string[]) => void;
  /** Callback when component should be closed */
  onClose?: () => void;
}

export function BulkOperationResultsV2({
  operationResult,
  entities = {},
  onRetryFailed,
  onClose: _onClose
}: BulkOperationResultsV2Props) {
  const {
    operation_id,
    total_count,
    success_count,
    failed_count,
    results,
    total_execution_time_ms
  } = operationResult;

  // Calculate success rate and categorize results
  const successRate = total_count > 0 ? (success_count / total_count) * 100 : 0;
  const hasFailures = failed_count > 0;

  // Group results by status for easier analysis
  const groupedResults = useMemo(() => {
    const groups = {
      success: [] as OperationResultSchema[],
      failed: [] as OperationResultSchema[],
      timeout: [] as OperationResultSchema[],
      unauthorized: [] as OperationResultSchema[]
    };

    results.forEach(result => {
      const status = result.status as keyof typeof groups;
      if (status in groups) {
        groups[status].push(result);
      }
    });

    return groups;
  }, [results]);

  // Get failed entity IDs for retry functionality
  const failedEntityIds = useMemo(() => {
    return groupedResults.failed
      .concat(groupedResults.timeout)
      .concat(groupedResults.unauthorized)
      .map(result => result.entity_id);
  }, [groupedResults]);

  // Get display name for entity
  const getEntityDisplayName = (entityId: string) => {
    const entity = entities[entityId];
    return entity?.name || entity?.friendly_name || entityId;
  };

  // Get appropriate icon for operation status
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <IconCheck className="h-4 w-4 text-green-600" />;
      case 'failed':
        return <IconX className="h-4 w-4 text-red-600" />;
      case 'timeout':
        return <IconClock className="h-4 w-4 text-yellow-600" />;
      case 'unauthorized':
        return <IconExclamationCircle className="h-4 w-4 text-orange-600" />;
      default:
        return <IconAlertTriangle className="h-4 w-4 text-gray-600" />;
    }
  };

  // Get appropriate badge variant for status
  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'success':
        return 'default' as const;
      case 'failed':
        return 'destructive' as const;
      case 'timeout':
        return 'secondary' as const;
      case 'unauthorized':
        return 'outline' as const;
      default:
        return 'secondary' as const;
    }
  };

  // Overall operation status
  const getOverallStatus = () => {
    if (failed_count === 0) return { text: "Completed Successfully", variant: "default" as const };
    if (success_count === 0) return { text: "Failed", variant: "destructive" as const };
    return { text: "Partially Completed", variant: "secondary" as const };
  };

  const overallStatus = getOverallStatus();

  return (
    <TooltipProvider>
      <div className="space-y-6">
        {/* Operation Summary */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  {getStatusIcon(failed_count === 0 ? 'success' : 'failed')}
                  Bulk Operation Results
                </CardTitle>
                <CardDescription>
                  Operation ID: {operation_id}
                </CardDescription>
              </div>
              <Badge variant={overallStatus.variant} className="text-sm">
                {overallStatus.text}
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            {/* Progress Bar */}
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Success Rate</span>
                <span>{successRate.toFixed(1)}%</span>
              </div>
              <Progress
                value={successRate}
                className="h-3"
              />
            </div>

            {/* Statistics */}
            <div className="grid grid-cols-4 gap-4 text-center">
              <div className="space-y-1">
                <p className="text-2xl font-bold tracking-tight text-green-600">{success_count}</p>
                <p className="text-xs text-muted-foreground">Succeeded</p>
              </div>
              <div className="space-y-1">
                <p className="text-2xl font-bold tracking-tight text-red-600">{failed_count}</p>
                <p className="text-xs text-muted-foreground">Failed</p>
              </div>
              <div className="space-y-1">
                <p className="text-2xl font-bold tracking-tight">{total_count}</p>
                <p className="text-xs text-muted-foreground">Total</p>
              </div>
              <div className="space-y-1">
                <p className="text-2xl font-bold tracking-tight text-blue-600">
                  {(total_execution_time_ms / 1000).toFixed(1)}s
                </p>
                <p className="text-xs text-muted-foreground">Duration</p>
              </div>
            </div>

            {/* Quick Actions */}
            {hasFailures && (
              <div className="flex gap-2 pt-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onRetryFailed?.(failedEntityIds)}
                      className="gap-2"
                    >
                      <IconRefresh className="h-4 w-4" />
                      Retry Failed ({failed_count})
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    Retry the {failed_count} failed operations
                  </TooltipContent>
                </Tooltip>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Detailed Results */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Entity Results</CardTitle>
            <CardDescription>
              Detailed status for each entity in the operation
            </CardDescription>
          </CardHeader>

          <CardContent className="p-0">
            <ScrollArea className="h-80">
              <div className="space-y-1">
                {/* Successful Results */}
                {groupedResults.success.length > 0 && (
                  <>
                    <div className="sticky top-0 bg-background px-4 py-2 border-b">
                      <h4 className="text-sm font-medium text-green-600 flex items-center gap-2">
                        <IconCheck className="h-4 w-4" />
                        Successful ({groupedResults.success.length})
                      </h4>
                    </div>
                    {groupedResults.success.map((result) => (
                      <div
                        key={result.entity_id}
                        className="flex items-center justify-between px-4 py-2 hover:bg-accent"
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          {getStatusIcon(result.status)}
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium truncate">
                              {getEntityDisplayName(result.entity_id)}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                              {result.entity_id}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant={getStatusBadgeVariant(result.status)} className="text-xs">
                            {result.status}
                          </Badge>
                          {result.execution_time_ms && (
                            <span className="text-xs text-muted-foreground">
                              {result.execution_time_ms}ms
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </>
                )}

                {/* Failed Results */}
                {groupedResults.failed.length > 0 && (
                  <>
                    <Separator />
                    <div className="sticky top-0 bg-background px-4 py-2 border-b">
                      <h4 className="text-sm font-medium text-red-600 flex items-center gap-2">
                        <IconX className="h-4 w-4" />
                        Failed ({groupedResults.failed.length})
                      </h4>
                    </div>
                    {groupedResults.failed.map((result) => (
                      <div
                        key={result.entity_id}
                        className="flex items-center justify-between px-4 py-2 hover:bg-accent"
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          {getStatusIcon(result.status)}
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium truncate">
                              {getEntityDisplayName(result.entity_id)}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                              {result.entity_id}
                            </p>
                            {result.error_message && (
                              <p className="text-xs text-red-600 truncate">
                                {result.error_message}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant={getStatusBadgeVariant(result.status)} className="text-xs">
                            {result.status}
                          </Badge>
                          {result.error_code && (
                            <Badge variant="outline" className="text-xs">
                              {result.error_code}
                            </Badge>
                          )}
                        </div>
                      </div>
                    ))}
                  </>
                )}

                {/* Timeout Results */}
                {groupedResults.timeout.length > 0 && (
                  <>
                    <Separator />
                    <div className="sticky top-0 bg-background px-4 py-2 border-b">
                      <h4 className="text-sm font-medium text-yellow-600 flex items-center gap-2">
                        <IconClock className="h-4 w-4" />
                        Timed Out ({groupedResults.timeout.length})
                      </h4>
                    </div>
                    {groupedResults.timeout.map((result) => (
                      <div
                        key={result.entity_id}
                        className="flex items-center justify-between px-4 py-2 hover:bg-accent"
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          {getStatusIcon(result.status)}
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium truncate">
                              {getEntityDisplayName(result.entity_id)}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                              {result.entity_id}
                            </p>
                          </div>
                        </div>
                        <Badge variant={getStatusBadgeVariant(result.status)} className="text-xs">
                          {result.status}
                        </Badge>
                      </div>
                    ))}
                  </>
                )}

                {/* Unauthorized Results */}
                {groupedResults.unauthorized.length > 0 && (
                  <>
                    <Separator />
                    <div className="sticky top-0 bg-background px-4 py-2 border-b">
                      <h4 className="text-sm font-medium text-orange-600 flex items-center gap-2">
                        <IconExclamationCircle className="h-4 w-4" />
                        Unauthorized ({groupedResults.unauthorized.length})
                      </h4>
                    </div>
                    {groupedResults.unauthorized.map((result) => (
                      <div
                        key={result.entity_id}
                        className="flex items-center justify-between px-4 py-2 hover:bg-accent"
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          {getStatusIcon(result.status)}
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium truncate">
                              {getEntityDisplayName(result.entity_id)}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                              {result.entity_id}
                            </p>
                          </div>
                        </div>
                        <Badge variant={getStatusBadgeVariant(result.status)} className="text-xs">
                          {result.status}
                        </Badge>
                      </div>
                    ))}
                  </>
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  );
}
