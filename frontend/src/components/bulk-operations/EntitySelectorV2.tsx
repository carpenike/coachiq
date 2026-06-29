/**
 * Enhanced Entity Selector V2 Component
 *
 * Advanced entity selection interface with filtering, grouping, and bulk selection
 * capabilities. Integrates with domain API v1 for optimized performance.
 */

import type { EntitySchema } from "@/api/types/domains";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  useEntitiesV2,
  useEntityFilters,
  useEntityPagination
} from "@/hooks/domains/useEntitiesV2";
import {
  IconBulb,
  IconCheck,
  IconFilter,
  IconLock,
  IconSearch,
  IconSelector,
  IconThermometer,
  IconWifi,
  IconX
} from "@tabler/icons-react";
import { useCallback, useMemo, useState } from "react";

interface EntitySelectorV2Props {
  /** Currently selected entity IDs */
  selectedEntityIds: string[];
  /** Callback when entity selection changes */
  onSelectionChange: (entityIds: string[]) => void;
  /** Whether selector is in multi-select mode */
  multiSelect?: boolean;
  /** Maximum number of entities that can be selected */
  maxSelection?: number;
  /** Hide entities that don't support bulk operations */
  bulkOperationsOnly?: boolean;
}

export function EntitySelectorV2({
  selectedEntityIds,
  onSelectionChange,
  multiSelect = true,
  maxSelection = 50,
  bulkOperationsOnly = false
}: EntitySelectorV2Props) {
  const [searchQuery, setSearchQuery] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [groupBy, setGroupBy] = useState<'area' | 'device_type' | 'protocol' | 'none'>('area');

  // Pagination and filtering
  const { page, pageSize, nextPage, prevPage, resetPagination, paginationParams } = useEntityPagination(25);
  const { filters, setFilter, removeFilter, clearFilters, hasActiveFilters } = useEntityFilters();

  // Apply search to filters
  const searchFilters = useMemo(() => ({
    ...filters,
    ...(searchQuery ? { search: searchQuery } : {})
  }), [filters, searchQuery]);

  // Fetch entities with pagination and filtering
  const { data: entityCollection, isLoading, error } = useEntitiesV2({
    ...searchFilters,
    ...paginationParams
  });

  // Filter entities for bulk operations if needed
  const filteredEntities = useMemo(() => {
    const entities = entityCollection?.entities || [];
    if (!bulkOperationsOnly) return entities;

    // Only include entities that support common bulk operations
    return entities.filter(entity =>
      ['light', 'lock', 'switch', 'fan'].includes(entity.device_type.toLowerCase())
    );
  }, [entityCollection?.entities, bulkOperationsOnly]);

  // Group entities based on groupBy setting
  const groupedEntities = useMemo(() => {
    if (groupBy === 'none') {
      return { 'All Entities': filteredEntities };
    }

    const groups: Record<string, EntitySchema[]> = {};
    filteredEntities.forEach(entity => {
      const groupKey = entity[groupBy] || 'Unknown';
      if (!groups[groupKey]) {
        groups[groupKey] = [];
      }
      groups[groupKey].push(entity);
    });

    return groups;
  }, [filteredEntities, groupBy]);

  // Selection handlers
  const isEntitySelected = useCallback(
    (entityId: string) => selectedEntityIds.includes(entityId),
    [selectedEntityIds]
  );

  const toggleEntitySelection = useCallback(
    (entityId: string) => {
      const isSelected = isEntitySelected(entityId);

      if (isSelected) {
        onSelectionChange(selectedEntityIds.filter(id => id !== entityId));
      } else if (multiSelect) {
        if (selectedEntityIds.length >= maxSelection) {
          return; // Max selection reached
        }
        onSelectionChange([...selectedEntityIds, entityId]);
      } else {
        onSelectionChange([entityId]);
      }
    },
    [isEntitySelected, selectedEntityIds, onSelectionChange, multiSelect, maxSelection]
  );

  const selectAllInGroup = useCallback(
    (groupEntities: EntitySchema[]) => {
      const groupEntityIds = groupEntities.map(e => e.entity_id);
      const newSelection = [
        ...selectedEntityIds.filter(id => !groupEntityIds.includes(id)),
        ...groupEntityIds.slice(0, maxSelection - selectedEntityIds.length + groupEntityIds.filter(id => selectedEntityIds.includes(id)).length)
      ];
      onSelectionChange(newSelection);
    },
    [selectedEntityIds, onSelectionChange, maxSelection]
  );

  const deselectAllInGroup = useCallback(
    (groupEntities: EntitySchema[]) => {
      const groupEntityIds = groupEntities.map(e => e.entity_id);
      onSelectionChange(selectedEntityIds.filter(id => !groupEntityIds.includes(id)));
    },
    [selectedEntityIds, onSelectionChange]
  );

  // Get entity icon based on device type
  const getEntityIcon = (entity: EntitySchema) => {
    const deviceType = entity.device_type.toLowerCase();
    switch (deviceType) {
      case 'light':
        return <IconBulb className="h-4 w-4" />;
      case 'lock':
        return <IconLock className="h-4 w-4" />;
      case 'temperature':
      case 'thermostat':
        return <IconThermometer className="h-4 w-4" />;
      default:
        return <IconWifi className="h-4 w-4" />;
    }
  };

  // Get entity status display
  const getEntityStatus = (entity: EntitySchema) => {
    if (!entity.available) {
      return <Badge variant="destructive" className="text-xs">Offline</Badge>;
    }

    const state = entity.state?.state;
    if (state === 'on') {
      return <Badge variant="default" className="text-xs bg-green-600">On</Badge>;
    } else if (state === 'off') {
      return <Badge variant="outline" className="text-xs">Off</Badge>;
    }

    return <Badge variant="secondary" className="text-xs">Unknown</Badge>;
  };

  return (
    <TooltipProvider>
      <Card className="w-full max-w-2xl">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <IconSelector className="h-5 w-5" />
              Select Entities
            </CardTitle>
            <div className="flex items-center gap-2">
              <Badge variant="secondary">
                {selectedEntityIds.length} / {maxSelection}
              </Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowFilters(!showFilters)}
                className={showFilters ? "bg-accent" : ""}
              >
                <IconFilter className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Search */}
          <div className="relative">
            <IconSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search entities..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                resetPagination();
              }}
              className="pl-10"
            />
          </div>

          {/* Filters */}
          {showFilters && (
            <div className="space-y-3 pt-3 border-t">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="device-type-filter" className="text-sm font-medium">Device Type</label>
                  <Select
                    value={filters.device_type || ""}
                    onValueChange={(value) =>
                      value ? setFilter('device_type', value) : removeFilter('device_type')
                    }
                  >
                    <SelectTrigger id="device-type-filter">
                      <SelectValue placeholder="All types" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">All types</SelectItem>
                      <SelectItem value="light">Lights</SelectItem>
                      <SelectItem value="lock">Locks</SelectItem>
                      <SelectItem value="temperature">Temperature</SelectItem>
                      <SelectItem value="switch">Switches</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label htmlFor="area-filter" className="text-sm font-medium">Area</label>
                  <Select
                    value={filters.area || ""}
                    onValueChange={(value) =>
                      value ? setFilter('area', value) : removeFilter('area')
                    }
                  >
                    <SelectTrigger id="area-filter">
                      <SelectValue placeholder="All areas" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">All areas</SelectItem>
                      <SelectItem value="living_room">Living Room</SelectItem>
                      <SelectItem value="bedroom">Bedroom</SelectItem>
                      <SelectItem value="kitchen">Kitchen</SelectItem>
                      <SelectItem value="bathroom">Bathroom</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label htmlFor="group-by-select" className="text-sm font-medium">Group by</label>
                  <Select value={groupBy} onValueChange={(value: 'area' | 'device_type' | 'protocol' | 'none') => setGroupBy(value)}>
                    <SelectTrigger id="group-by-select" className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="area">Area</SelectItem>
                      <SelectItem value="device_type">Type</SelectItem>
                      <SelectItem value="protocol">Protocol</SelectItem>
                      <SelectItem value="none">None</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {hasActiveFilters && (
                  <Button variant="outline" size="sm" onClick={clearFilters}>
                    Clear Filters
                  </Button>
                )}
              </div>
            </div>
          )}
        </CardHeader>

        <CardContent className="p-0">
          <ScrollArea className="h-96">
            {isLoading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="flex items-center space-x-3">
                    <Skeleton className="h-4 w-4" />
                    <Skeleton className="h-4 w-6" />
                    <Skeleton className="h-4 flex-1" />
                    <Skeleton className="h-4 w-16" />
                  </div>
                ))}
              </div>
            ) : error ? (
              <div className="p-4 text-center text-red-600">
                Error loading entities: {error.message}
              </div>
            ) : Object.keys(groupedEntities).length === 0 ? (
              <div className="p-4 text-center text-muted-foreground">
                No entities found matching your criteria
              </div>
            ) : (
              <div className="space-y-1">
                {Object.entries(groupedEntities).map(([groupName, groupEntities]) => (
                  <div key={groupName}>
                    {/* Group Header */}
                    {groupBy !== 'none' && (
                      <div className="sticky top-0 bg-background border-b px-4 py-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <h4 className="font-medium text-sm">{groupName}</h4>
                          <Badge variant="outline" className="text-xs">
                            {groupEntities.length}
                          </Badge>
                        </div>
                        {multiSelect && (
                          <div className="flex gap-1">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => selectAllInGroup(groupEntities)}
                                  className="h-6 px-2"
                                >
                                  <IconCheck className="h-3 w-3" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Select all in group</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => deselectAllInGroup(groupEntities)}
                                  className="h-6 px-2"
                                >
                                  <IconX className="h-3 w-3" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Deselect all in group</TooltipContent>
                            </Tooltip>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Group Entities */}
                    {groupEntities.map((entity) => (
                      <div
                        key={entity.entity_id}
                        className="flex items-center space-x-3 px-4 py-2 hover:bg-accent cursor-pointer"
                        onClick={() => toggleEntitySelection(entity.entity_id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            toggleEntitySelection(entity.entity_id);
                          }
                        }}
                        role="button"
                        tabIndex={0}
                      >
                        <Checkbox
                          checked={isEntitySelected(entity.entity_id)}
                          onChange={() => undefined} // Read-only behavior
                        />

                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          {getEntityIcon(entity)}
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium truncate">
                              {entity.name}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                              {entity.entity_id}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {getEntityStatus(entity)}
                          {entity.area && (
                            <Badge variant="outline" className="text-xs">
                              {entity.area}
                            </Badge>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>

          {/* Pagination */}
          {entityCollection && entityCollection.total_count > pageSize && (
            <>
              <Separator />
              <div className="p-4 flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, entityCollection.total_count)} of {entityCollection.total_count}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={prevPage}
                    disabled={page === 1}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={nextPage}
                    disabled={!entityCollection.has_next}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
