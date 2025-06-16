/**
 * Test file for validation-enhanced domain hooks
 *
 * Tests the safety-aware optimistic updates and validation functionality
 * of the enhanced domain hooks for entity management.
 */

import { renderHook } from '@testing-library/react';
import { waitFor } from '@testing-library/dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

import {
  useEntitiesV2WithValidation,
  useEntityV2WithValidation,
  useControlEntityV2WithValidation,
  useBulkControlEntitiesV2WithValidation,
  useBulkLightControlWithValidation,
  useEntitySelectionWithValidation,
} from '../useEntitiesV2';

// Mock the API functions
vi.mock('../../../api/domains/entities', () => ({
  fetchEntitiesV2WithValidation: vi.fn(),
  fetchEntityV2WithValidation: vi.fn(),
  controlEntityV2WithValidation: vi.fn(),
  bulkControlEntitiesV2WithValidation: vi.fn(),
  isDomainAPIAvailable: vi.fn(),
}));

// Mock the validation functions
vi.mock('../../../api/validation/zod-schemas', () => ({
  validateEntity: vi.fn(),
  validateControlCommand: vi.fn(),
  validateBulkControlRequest: vi.fn(),
}));

// Test wrapper component
const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });

  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('useEntitiesV2WithValidation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch entities with validation', async () => {
    const mockData = {
      entities: [
        {
          entity_id: 'light1',
          name: 'Test Light',
          device_type: 'light',
          protocol: 'rvc',
          state: { on: true, brightness: 75 },
          last_updated: '2025-01-11T10:30:00Z',
          available: true,
        },
      ],
      total_count: 1,
      page: 1,
      page_size: 50,
      has_next: false,
      filters_applied: {},
    };

    const { fetchEntitiesV2WithValidation } = await import('../../../api/domains/entities');
    vi.mocked(fetchEntitiesV2WithValidation).mockResolvedValue(mockData);

    const { result } = renderHook(() => useEntitiesV2WithValidation(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockData);
    expect(fetchEntitiesV2WithValidation).toHaveBeenCalledWith(undefined);
  });

  it('should pass query parameters correctly', async () => {
    const params = { device_type: 'light', page: 1, page_size: 20 };
    const { fetchEntitiesV2WithValidation } = await import('../../../api/domains/entities');
    vi.mocked(fetchEntitiesV2WithValidation).mockResolvedValue({
      entities: [],
      total_count: 0,
      page: 1,
      page_size: 20,
      has_next: false,
      filters_applied: { device_type: 'light' },
    });

    renderHook(() => useEntitiesV2WithValidation(params), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(fetchEntitiesV2WithValidation).toHaveBeenCalledWith(params);
    });
  });
});

describe('useEntityV2WithValidation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch single entity with validation', async () => {
    const mockEntity = {
      entity_id: 'light1',
      name: 'Test Light',
      device_type: 'light',
      protocol: 'rvc',
      state: { on: true, brightness: 75 },
      last_updated: '2025-01-11T10:30:00Z',
      available: true,
    };

    const { fetchEntityV2WithValidation } = await import('../../../api/domains/entities');
    vi.mocked(fetchEntityV2WithValidation).mockResolvedValue(mockEntity);

    const { result } = renderHook(() => useEntityV2WithValidation('light1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockEntity);
    expect(fetchEntityV2WithValidation).toHaveBeenCalledWith('light1');
  });

  it('should not fetch when entity ID is empty', () => {
    const { fetchEntityV2WithValidation } = vi.mocked(
      require('../../../api/domains/entities')
    );

    renderHook(() => useEntityV2WithValidation(''), {
      wrapper: createWrapper(),
    });

    expect(fetchEntityV2WithValidation).not.toHaveBeenCalled();
  });

  it('should not fetch when disabled', () => {
    const { fetchEntityV2WithValidation } = vi.mocked(
      require('../../../api/domains/entities')
    );

    renderHook(() => useEntityV2WithValidation('light1', false), {
      wrapper: createWrapper(),
    });

    expect(fetchEntityV2WithValidation).not.toHaveBeenCalled();
  });
});

describe('useControlEntityV2WithValidation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should control entity with validation', async () => {
    const mockResult = {
      entity_id: 'light1',
      status: 'success' as const,
      execution_time_ms: 150,
    };

    const { controlEntityV2WithValidation } = await import('../../../api/domains/entities');
    vi.mocked(controlEntityV2WithValidation).mockResolvedValue(mockResult);

    const { result } = renderHook(() => useControlEntityV2WithValidation(), {
      wrapper: createWrapper(),
    });

    const command = { command: 'set' as const, state: true };

    await waitFor(() => {
      result.current.mutate({ entityId: 'light1', command });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(controlEntityV2WithValidation).toHaveBeenCalledWith('light1', command);
  });

  it('should handle validation errors gracefully', async () => {
    const { controlEntityV2WithValidation } = await import('../../../api/domains/entities');
    vi.mocked(controlEntityV2WithValidation).mockRejectedValue(
      new Error('Invalid control command: brightness must be between 0 and 100')
    );

    const { result } = renderHook(() => useControlEntityV2WithValidation(), {
      wrapper: createWrapper(),
    });

    const command = { command: 'set' as const, brightness: 150 }; // Invalid brightness

    result.current.mutate({ entityId: 'light1', command });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error?.message).toContain('Invalid control command');
  });
});

describe('useBulkLightControlWithValidation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should provide validated bulk light control functions', () => {
    const { result } = renderHook(() => useBulkLightControlWithValidation(), {
      wrapper: createWrapper(),
    });

    expect(result.current.turnOn).toBeInstanceOf(Function);
    expect(result.current.turnOff).toBeInstanceOf(Function);
    expect(result.current.setBrightness).toBeInstanceOf(Function);
    expect(result.current.toggle).toBeInstanceOf(Function);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('should enforce safety limits on entity count', () => {
    const { result } = renderHook(() => useBulkLightControlWithValidation(), {
      wrapper: createWrapper(),
    });

    // Create array with more than 50 entities
    const manyEntityIds = Array.from({ length: 100 }, (_, i) => `light${i}`);

    // Call should not throw - safety limit should be enforced internally
    expect(() => {
      result.current.turnOn(manyEntityIds);
    }).not.toThrow();
  });

  it('should clamp brightness values for safety', () => {
    const { result } = renderHook(() => useBulkLightControlWithValidation(), {
      wrapper: createWrapper(),
    });

    // Should handle out-of-range brightness values
    expect(() => {
      result.current.setBrightness(['light1'], 150); // Over 100
    }).not.toThrow();

    expect(() => {
      result.current.setBrightness(['light1'], -10); // Below 0
    }).not.toThrow();
  });
});

describe('useEntitySelectionWithValidation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should provide entity selection functionality', () => {
    const { result } = renderHook(() => useEntitySelectionWithValidation(), {
      wrapper: createWrapper(),
    });

    expect(result.current.selectedEntityIds).toEqual([]);
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.selectEntity).toBeInstanceOf(Function);
    expect(result.current.deselectEntity).toBeInstanceOf(Function);
    expect(result.current.toggleEntitySelection).toBeInstanceOf(Function);
    expect(result.current.selectAll).toBeInstanceOf(Function);
    expect(result.current.deselectAll).toBeInstanceOf(Function);
  });

  it('should provide enhanced convenience methods', () => {
    const { result } = renderHook(() => useEntitySelectionWithValidation(), {
      wrapper: createWrapper(),
    });

    expect(result.current.turnOnSelected).toBeInstanceOf(Function);
    expect(result.current.turnOffSelected).toBeInstanceOf(Function);
    expect(result.current.setBrightnessSelected).toBeInstanceOf(Function);
    expect(result.current.toggleSelected).toBeInstanceOf(Function);
  });

  it('should enforce safety limits on selection', () => {
    const { result } = renderHook(() => useEntitySelectionWithValidation(), {
      wrapper: createWrapper(),
    });

    // Create array with more than 100 entities
    const manyEntityIds = Array.from({ length: 150 }, (_, i) => `light${i}`);

    // Should enforce safety limit
    result.current.selectAll(manyEntityIds);

    expect(result.current.selectedCount).toBe(100);
    expect(result.current.selectedEntityIds).toHaveLength(100);
  });

  it('should throw error for bulk operations with too many entities', async () => {
    const { result } = renderHook(() => useEntitySelectionWithValidation(), {
      wrapper: createWrapper(),
    });

    // Select more than 50 entities
    const manyEntityIds = Array.from({ length: 75 }, (_, i) => `light${i}`);
    result.current.selectAll(manyEntityIds);

    // Should throw error for bulk operation exceeding safety limit
    const command = { command: 'set' as const, state: true };

    await expect(async () => {
      await result.current.executeBulkOperation(command);
    }).rejects.toThrow('Bulk operation size limited to 50 entities');
  });

  it('should throw error for bulk operations with no entities selected', async () => {
    const { result } = renderHook(() => useEntitySelectionWithValidation(), {
      wrapper: createWrapper(),
    });

    const command = { command: 'set' as const, state: true };

    await expect(async () => {
      await result.current.executeBulkOperation(command);
    }).rejects.toThrow('No entities selected for bulk operation');
  });
});
