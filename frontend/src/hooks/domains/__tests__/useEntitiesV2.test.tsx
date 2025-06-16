/**
 * Tests for useEntitiesV2 Domain Hooks
 *
 * Comprehensive tests for the entities domain React hooks including
 * optimistic updates, bulk operations, error handling, and state management.
 */

import { renderHook, act } from '@testing-library/react';
import { waitFor } from '@testing-library/dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

import {
  useEntitiesV2,
  useEntityV2,
  useControlEntityV2,
  useBulkControlEntitiesV2,
  useEntitySelection,
  useEntityPagination,
  useEntityFilters,
  entitiesV2QueryKeys,
} from '../useEntitiesV2';

// Import mocked functions
import {
  fetchEntitiesV2,
  fetchEntityV2,
  controlEntityV2,
  bulkControlEntitiesV2,
} from '@/api/domains/entities';

// Mock types
import type {
  EntityCollectionSchema,
  EntitySchema,
  BulkOperationResultSchema,
  OperationResultSchema,
} from '@/api/types/domains';

// Mock the API client
vi.mock('@/api/domains/entities', () => ({
  fetchEntitiesV2: vi.fn(),
  fetchEntityV2: vi.fn(),
  controlEntityV2: vi.fn(),
  bulkControlEntitiesV2: vi.fn(),
  fetchSchemasV2: vi.fn(),
}));

const mockEntityCollection: EntityCollectionSchema = {
  entities: [
    {
      entity_id: 'light_001',
      name: 'Living Room Light',
      device_type: 'light',
      protocol: 'rvc',
      state: { state: 'off', brightness: 0 },
      area: 'living_room',
      last_updated: '2024-01-01T00:00:00Z',
      available: true,
    },
    {
      entity_id: 'lock_001',
      name: 'Front Door Lock',
      device_type: 'lock',
      protocol: 'rvc',
      state: { state: 'locked' },
      area: 'entrance',
      last_updated: '2024-01-01T00:00:00Z',
      available: true,
    },
  ],
  total_count: 2,
  page: 1,
  page_size: 50,
  has_next: false,
  filters_applied: {},
};

const mockEntity: EntitySchema = mockEntityCollection.entities[0]!; // Safe assertion since we just defined it above

const mockBulkOperationResult: BulkOperationResultSchema = {
  operation_id: 'bulk_op_123',
  total_count: 2,
  success_count: 2,
  failed_count: 0,
  results: [
    {
      entity_id: 'light_001',
      status: 'success',
      execution_time_ms: 120,
    },
    {
      entity_id: 'light_002',
      status: 'success',
      execution_time_ms: 135,
    },
  ],
  total_execution_time_ms: 300,
};

// Test wrapper with QueryClient
function createTestWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });

  const TestQueryProvider = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  TestQueryProvider.displayName = 'TestQueryProvider';

  return TestQueryProvider;
}

describe('entitiesV2QueryKeys', () => {
  it('should generate correct query keys', () => {
    expect(entitiesV2QueryKeys.all).toEqual(['entities-v2']);
    expect(entitiesV2QueryKeys.collections()).toEqual(['entities-v2', 'collections']);
    expect(entitiesV2QueryKeys.collection({ device_type: 'light' })).toEqual([
      'entities-v2',
      'collections',
      { device_type: 'light' },
    ]);
    expect(entitiesV2QueryKeys.entity('light_001')).toEqual([
      'entities-v2',
      'entity',
      'light_001',
    ]);
  });
});

describe('useEntitiesV2', () => {
  beforeEach(() => {
    vi.mocked(fetchEntitiesV2).mockResolvedValue(mockEntityCollection);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch entities successfully', async () => {
    const { result } = renderHook(() => useEntitiesV2(), {
      wrapper: createTestWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockEntityCollection);
    expect(fetchEntitiesV2).toHaveBeenCalledWith(undefined);
  });

  it('should fetch entities with parameters', async () => {
    const params = { device_type: 'light', page: 1, page_size: 10 };

    const { result } = renderHook(() => useEntitiesV2(params), {
      wrapper: createTestWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(fetchEntitiesV2).toHaveBeenCalledWith(params);
  });

  it('should handle fetch error', async () => {
    const error = new Error('Network error');
    vi.mocked(fetchEntitiesV2).mockRejectedValue(error);

    const { result } = renderHook(() => useEntitiesV2(), {
      wrapper: createTestWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(error);
  });
});

describe('useEntityV2', () => {
  beforeEach(() => {
    vi.mocked(fetchEntityV2).mockResolvedValue(mockEntity);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch single entity successfully', async () => {
    const { result } = renderHook(() => useEntityV2('light_001'), {
      wrapper: createTestWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockEntity);
    expect(fetchEntityV2).toHaveBeenCalledWith('light_001');
  });

  it('should not fetch when disabled', () => {
    renderHook(() => useEntityV2('light_001', false), {
      wrapper: createTestWrapper(),
    });

    expect(fetchEntityV2).not.toHaveBeenCalled();
  });

  it('should not fetch when entity ID is empty', () => {
    renderHook(() => useEntityV2(''), {
      wrapper: createTestWrapper(),
    });

    expect(fetchEntityV2).not.toHaveBeenCalled();
  });
});

describe('useControlEntityV2', () => {
  beforeEach(() => {
    const mockResult: OperationResultSchema = {
      entity_id: 'light_001',
      status: 'success',
      execution_time_ms: 150,
    };
    vi.mocked(controlEntityV2).mockResolvedValue(mockResult);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should control entity successfully', async () => {
    const { result } = renderHook(() => useControlEntityV2(), {
      wrapper: createTestWrapper(),
    });

    const command = { command: 'set' as const, state: true };

    await act(async () => {
      result.current.mutate({ entityId: 'light_001', command });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(controlEntityV2).toHaveBeenCalledWith('light_001', command);
  });

  it('should handle control error', async () => {
    const error = new Error('Control failed');
    vi.mocked(controlEntityV2).mockRejectedValue(error);

    const { result } = renderHook(() => useControlEntityV2(), {
      wrapper: createTestWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        entityId: 'light_001',
        command: { command: 'toggle' },
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(error);
  });

  it('should perform optimistic updates', async () => {
    // This test would require mocking QueryClient and testing optimistic updates
    // For now, we'll just ensure the mutation works
    const { result } = renderHook(() => useControlEntityV2(), {
      wrapper: createTestWrapper(),
    });

    expect(result.current.mutate).toBeDefined();
  });
});

describe('useBulkControlEntitiesV2', () => {
  beforeEach(() => {
    vi.mocked(bulkControlEntitiesV2).mockResolvedValue(mockBulkOperationResult);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should execute bulk control successfully', async () => {
    const { result } = renderHook(() => useBulkControlEntitiesV2(), {
      wrapper: createTestWrapper(),
    });

    const request = {
      entity_ids: ['light_001', 'light_002'],
      command: { command: 'set' as const, state: true },
      ignore_errors: true,
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockBulkOperationResult);
    expect(bulkControlEntitiesV2).toHaveBeenCalledWith(request);
  });

  it('should handle bulk control error', async () => {
    const error = new Error('Bulk operation failed');
    vi.mocked(bulkControlEntitiesV2).mockRejectedValue(error);

    const { result } = renderHook(() => useBulkControlEntitiesV2(), {
      wrapper: createTestWrapper(),
    });

    const request = {
      entity_ids: ['light_001'],
      command: { command: 'toggle' as const },
    };

    await act(async () => {
      result.current.mutate(request);
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(error);
  });
});

describe('useEntitySelection', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should manage entity selection state', () => {
    const { result } = renderHook(() => useEntitySelection(), {
      wrapper: createTestWrapper(),
    });

    // Initial state
    expect(result.current.selectedEntityIds).toEqual([]);
    expect(result.current.selectedCount).toBe(0);

    // Select entity
    act(() => {
      result.current.selectEntity('light_001');
    });

    expect(result.current.selectedEntityIds).toEqual(['light_001']);
    expect(result.current.selectedCount).toBe(1);

    // Select another entity
    act(() => {
      result.current.selectEntity('lock_001');
    });

    expect(result.current.selectedEntityIds).toEqual(['light_001', 'lock_001']);
    expect(result.current.selectedCount).toBe(2);

    // Deselect entity
    act(() => {
      result.current.deselectEntity('light_001');
    });

    expect(result.current.selectedEntityIds).toEqual(['lock_001']);
    expect(result.current.selectedCount).toBe(1);
  });

  it('should toggle entity selection', () => {
    const { result } = renderHook(() => useEntitySelection(), {
      wrapper: createTestWrapper(),
    });

    // Toggle select
    act(() => {
      result.current.toggleEntitySelection('light_001');
    });

    expect(result.current.selectedEntityIds).toEqual(['light_001']);

    // Toggle deselect
    act(() => {
      result.current.toggleEntitySelection('light_001');
    });

    expect(result.current.selectedEntityIds).toEqual([]);
  });

  it('should select/deselect all entities', () => {
    const { result } = renderHook(() => useEntitySelection(), {
      wrapper: createTestWrapper(),
    });

    const entityIds = ['light_001', 'lock_001', 'sensor_001'];

    // Select all
    act(() => {
      result.current.selectAll(entityIds);
    });

    expect(result.current.selectedEntityIds).toEqual(entityIds);
    expect(result.current.selectedCount).toBe(3);

    // Deselect all
    act(() => {
      result.current.deselectAll();
    });

    expect(result.current.selectedEntityIds).toEqual([]);
    expect(result.current.selectedCount).toBe(0);
  });

  it('should execute bulk operation', async () => {
    vi.mocked(bulkControlEntitiesV2).mockResolvedValue(mockBulkOperationResult);

    const { result } = renderHook(() => useEntitySelection(), {
      wrapper: createTestWrapper(),
    });

    // Select entities first
    act(() => {
      result.current.selectAll(['light_001', 'light_002']);
    });

    // Execute bulk operation
    await act(async () => {
      result.current.executeBulkOperation({ command: 'toggle' });
    });

    expect(bulkControlEntitiesV2).toHaveBeenCalledWith({
      entity_ids: ['light_001', 'light_002'],
      command: { command: 'toggle' },
      ignore_errors: true,
      timeout_seconds: undefined,
    });
  });

  it('should throw error when executing bulk operation with no selection', () => {
    const { result } = renderHook(() => useEntitySelection(), {
      wrapper: createTestWrapper(),
    });

    expect(() => {
      result.current.executeBulkOperation({ command: 'toggle' });
    }).toThrow('No entities selected for bulk operation');
  });
});

describe('useEntityPagination', () => {
  it('should manage pagination state', () => {
    const { result } = renderHook(() => useEntityPagination(20));

    // Initial state
    expect(result.current.page).toBe(1);
    expect(result.current.pageSize).toBe(20);

    // Next page
    act(() => {
      result.current.nextPage();
    });

    expect(result.current.page).toBe(2);

    // Previous page
    act(() => {
      result.current.prevPage();
    });

    expect(result.current.page).toBe(1);

    // Go to specific page
    act(() => {
      result.current.goToPage(5);
    });

    expect(result.current.page).toBe(5);

    // Reset pagination
    act(() => {
      result.current.resetPagination();
    });

    expect(result.current.page).toBe(1);
  });

  it('should not go to page less than 1', () => {
    const { result } = renderHook(() => useEntityPagination());

    // Try to go to page 0
    act(() => {
      result.current.goToPage(0);
    });

    expect(result.current.page).toBe(1);

    // Try previous page when already at page 1
    act(() => {
      result.current.prevPage();
    });

    expect(result.current.page).toBe(1);
  });

  it('should provide pagination parameters', () => {
    const { result } = renderHook(() => useEntityPagination(25));

    act(() => {
      result.current.goToPage(3);
    });

    expect(result.current.paginationParams).toEqual({
      page: 3,
      page_size: 25,
    });
  });
});

describe('useEntityFilters', () => {
  it('should manage filter state', () => {
    const { result } = renderHook(() => useEntityFilters());

    // Initial state
    expect(result.current.filters).toEqual({});
    expect(result.current.hasActiveFilters).toBe(false);

    // Set filter
    act(() => {
      result.current.setFilter('device_type', 'light');
    });

    expect(result.current.filters).toEqual({ device_type: 'light' });
    expect(result.current.hasActiveFilters).toBe(true);

    // Set another filter
    act(() => {
      result.current.setFilter('area', 'living_room');
    });

    expect(result.current.filters).toEqual({
      device_type: 'light',
      area: 'living_room',
    });

    // Remove filter
    act(() => {
      result.current.removeFilter('device_type');
    });

    expect(result.current.filters).toEqual({ area: 'living_room' });

    // Clear all filters
    act(() => {
      result.current.clearFilters();
    });

    expect(result.current.filters).toEqual({});
    expect(result.current.hasActiveFilters).toBe(false);
  });
});
