/**
 * Enhanced Bulk Operations Modal V2 Component
 *
 * Complete bulk operations interface combining entity selection, operation controls,
 * and real-time progress tracking. Uses domain API v1 with optimistic updates.
 */

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useEntitySelection } from "@/hooks/useEntities";
import { useState, useCallback, useEffect } from "react";
import { EntitySelectorV2 } from "./EntitySelectorV2";
import { BulkOperationPanelV2 } from "./BulkOperationPanelV2";
import { BulkOperationResultsV2 } from "./BulkOperationResultsV2";

interface BulkOperationsModalV2Props {
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal open state changes */
  onOpenChange: (open: boolean) => void;
  /** Pre-selected entity IDs */
  initialSelection?: string[];
  /** Entity data for display names */
  entities?: Record<string, { name?: string; friendly_name?: string; [key: string]: unknown }>;
}

export function BulkOperationsModalV2({
  open,
  onOpenChange,
  initialSelection = [],
  entities = {}
}: BulkOperationsModalV2Props) {
  const [activeTab, setActiveTab] = useState<'select' | 'operate' | 'results'>('select');

  const {
    selectedEntityIds,
    selectedCount,
    selectEntity,
    deselectAll,
    bulkOperationState: { isLoading, data: operationResult, reset }
  } = useEntitySelection();

  // Initialize with pre-selected entities
  useEffect(() => {
    if (open && initialSelection.length > 0) {
      // Clear existing selection and set initial selection
      deselectAll();
      initialSelection.forEach(entityId => selectEntity(entityId));

      // If entities are pre-selected, skip to operation tab
      if (initialSelection.length > 0) {
        setActiveTab('operate');
      }
    }
  }, [open, initialSelection, deselectAll, selectEntity]);

  // Move to results tab when operation completes
  useEffect(() => {
    if (operationResult && !isLoading) {
      setActiveTab('results');
    }
  }, [operationResult, isLoading]);

  // Reset state when modal closes
  useEffect(() => {
    if (!open) {
      setActiveTab('select');
      reset();
      // Don't clear selection here as user might want to keep it
    }
  }, [open, reset]);

  // Handle entity selection changes
  const handleSelectionChange = useCallback(
    (entityIds: string[]) => {
      // Clear current selection
      deselectAll();
      // Add new selection
      entityIds.forEach(entityId => selectEntity(entityId));
    },
    [deselectAll, selectEntity]
  );

  // Handle tab changes with validation
  const handleTabChange = useCallback(
    (tab: string) => {
      if (tab === 'operate' && selectedCount === 0) {
        // Can't go to operate tab without selections
        return;
      }
      setActiveTab(tab as 'select' | 'operate' | 'results');
    },
    [selectedCount]
  );

  // Close modal with cleanup
  const handleClose = useCallback(() => {
    onOpenChange(false);
    deselectAll();
    reset();
    setActiveTab('select');
  }, [onOpenChange, deselectAll, reset]);

  // Navigation helpers
  const goToOperateTab = () => setActiveTab('operate');
  const goToSelectTab = () => setActiveTab('select');
  const goToResultsTab = () => setActiveTab('results');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-xl">Bulk Operations</DialogTitle>
          <DialogDescription>
            Select multiple entities and perform batch operations with real-time progress tracking
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-hidden">
          <Tabs value={activeTab} onValueChange={handleTabChange} className="h-full flex flex-col">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="select" className="relative">
                Select Entities
                {selectedCount > 0 && (
                  <span className="absolute -top-1 -right-1 bg-primary text-primary-foreground text-xs rounded-full h-5 w-5 flex items-center justify-center">
                    {selectedCount}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger
                value="operate"
                disabled={selectedCount === 0}
                className="relative"
              >
                Operations
                {isLoading && (
                  <span className="absolute -top-1 -right-1 bg-yellow-500 text-white text-xs rounded-full h-2 w-2 animate-pulse" />
                )}
              </TabsTrigger>
              <TabsTrigger
                value="results"
                disabled={!operationResult}
                className="relative"
              >
                Results
                {operationResult && (
                  <span className="absolute -top-1 -right-1 bg-green-500 text-white text-xs rounded-full h-2 w-2" />
                )}
              </TabsTrigger>
            </TabsList>

            <div className="flex-1 overflow-hidden">
              {/* Entity Selection Tab */}
              <TabsContent value="select" className="h-full overflow-hidden">
                <div className="h-full flex flex-col">
                  <div className="flex-1 overflow-hidden">
                    <EntitySelectorV2
                      selectedEntityIds={selectedEntityIds}
                      onSelectionChange={handleSelectionChange}
                      multiSelect
                      maxSelection={50}
                      bulkOperationsOnly
                    />
                  </div>

                  {/* Selection Summary */}
                  {selectedCount > 0 && (
                    <>
                      <Separator className="my-4" />
                      <div className="flex items-center justify-between">
                        <div className="text-sm text-muted-foreground">
                          {selectedCount} entities selected
                        </div>
                        <div className="flex gap-2">
                          <Button variant="outline" onClick={deselectAll}>
                            Clear All
                          </Button>
                          <Button onClick={goToOperateTab}>
                            Continue to Operations
                          </Button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </TabsContent>

              {/* Operations Tab */}
              <TabsContent value="operate" className="h-full overflow-hidden">
                <div className="h-full flex flex-col">
                  <div className="flex-1 overflow-auto">
                    <BulkOperationPanelV2
                      selectedEntityIds={selectedEntityIds}
                      onClearSelection={deselectAll}
                      onClose={handleClose}
                      entities={entities}
                    />
                  </div>

                  {/* Operations Navigation */}
                  <Separator className="my-4" />
                  <div className="flex items-center justify-between">
                    <Button variant="outline" onClick={goToSelectTab}>
                      Back to Selection
                    </Button>

                    <div className="text-sm text-muted-foreground">
                      {selectedCount} entities ready for operation
                    </div>

                    {operationResult && (
                      <Button onClick={goToResultsTab}>
                        View Results
                      </Button>
                    )}
                  </div>
                </div>
              </TabsContent>

              {/* Results Tab */}
              <TabsContent value="results" className="h-full overflow-hidden">
                <div className="h-full flex flex-col">
                  <div className="flex-1 overflow-auto">
                    {operationResult ? (
                      <BulkOperationResultsV2
                        operationResult={operationResult}
                        entities={entities}
                        onRetryFailed={(failedEntityIds) => {
                          // Clear current selection and set failed entities
                          deselectAll();
                          failedEntityIds.forEach(entityId => selectEntity(entityId));
                          setActiveTab('operate');
                        }}
                        onClose={handleClose}
                      />
                    ) : (
                      <div className="p-8 text-center text-muted-foreground">
                        No operation results available
                      </div>
                    )}
                  </div>

                  {/* Results Navigation */}
                  {operationResult && (
                    <>
                      <Separator className="my-4" />
                      <div className="flex items-center justify-between">
                        <Button variant="outline" onClick={goToOperateTab}>
                          New Operation
                        </Button>

                        <div className="text-sm text-muted-foreground">
                          Operation completed: {operationResult.success_count} succeeded, {operationResult.failed_count} failed
                        </div>

                        <Button onClick={handleClose}>
                          Close
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </DialogContent>
    </Dialog>
  );
}
