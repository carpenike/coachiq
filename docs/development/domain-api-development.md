# Domain API v1 Development Guide

This guide provides comprehensive information for developers working on the Domain API v1 implementation, including architecture decisions, development patterns, and contribution guidelines.

## Architecture Overview

### Domain-Driven Design (DDD)

The Domain API v1 follows Domain-Driven Design principles:

```
backend/
├── api/domains/           # Domain-specific API routers
│   ├── entities.py       # Entity domain endpoints
│   ├── diagnostics.py    # Diagnostics domain (future)
│   └── analytics.py      # Analytics domain (future)
├── services/domains/     # Domain business logic
│   ├── entity_domain_service.py
│   └── domain_base.py
├── schemas/              # Pydantic schemas with Zod export
│   ├── entities.py
│   └── common.py
├── middleware/           # Domain-specific middleware
│   ├── domain_middleware.py
│   ├── domain_auth.py
│   └── rate_limiting.py
└── monitoring/           # Observability
    └── domain_monitoring.py
```

### Key Design Principles

1. **Domain Isolation**: Each domain is self-contained with its own models, services, and endpoints
2. **Progressive Enhancement**: New domain APIs complement existing functionality
3. **Type Safety**: TypeScript-first design with runtime validation
4. **Performance**: Built-in caching, rate limiting, and monitoring
5. **Observability**: Comprehensive logging, metrics, and alerting

## Development Workflow

### Adding a New Domain

1. **Create Domain Schema**
```python
# backend/schemas/new_domain.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class NewDomainItemSchema(BaseModel):
    """Schema for new domain items."""

    item_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Human-readable name")
    status: str = Field(..., description="Current status")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    @classmethod
    def to_zod_schema(cls) -> dict:
        """Export Zod-compatible schema for frontend."""
        return {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "name": {"type": "string"},
                "status": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"}
            },
            "required": ["item_id", "name", "status", "created_at"]
        }
```

2. **Create Domain Service**
```python
# backend/services/domains/new_domain_service.py
from typing import List, Optional
from backend.schemas.new_domain import NewDomainItemSchema
from backend.services.domains.domain_base import DomainServiceBase

class NewDomainService(DomainServiceBase):
    """Service for new domain business logic."""

    def __init__(self, app_state):
        super().__init__("new_domain", app_state)

    async def list_items(
        self,
        filters: Optional[dict] = None,
        page: int = 1,
        page_size: int = 50
    ) -> List[NewDomainItemSchema]:
        """List domain items with filtering and pagination."""
        # Implementation here
        pass

    async def get_item(self, item_id: str) -> Optional[NewDomainItemSchema]:
        """Get specific domain item."""
        # Implementation here
        pass

    async def create_item(self, item_data: dict) -> NewDomainItemSchema:
        """Create new domain item."""
        # Implementation here
        pass
```

3. **Create Domain Router**
```python
# backend/api/domains/new_domain.py
from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
from backend.schemas.new_domain import NewDomainItemSchema
from backend.core.domain_dependencies import (
    NewDomainServiceDep,
    UserContextDep,
    NewDomainAPIFeature
)

def create_new_domain_router() -> APIRouter:
    """Create router for new domain API endpoints."""

    router = APIRouter(prefix="/new-domain", tags=["new-domain"])

    @router.get(
        "/",
        response_model=List[NewDomainItemSchema],
        summary="List domain items",
        dependencies=[NewDomainAPIFeature],
    )
    async def list_items(
        service: NewDomainServiceDep,
        user_context: UserContextDep,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    ) -> List[NewDomainItemSchema]:
        """List domain items with pagination."""
        try:
            return await service.list_items(
                page=page,
                page_size=page_size
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list items: {e}"
            )

    @router.get("/health")
    async def health_check() -> dict:
        """Health check for new domain."""
        return {"status": "healthy", "domain": "new_domain"}

    return router
```

4. **Add Domain Dependencies**
```python
# backend/core/domain_dependencies.py
from fastapi import Depends, HTTPException
from backend.services.domains.new_domain_service import NewDomainService

async def get_new_domain_service(
    app_state = Depends(get_app_state)
) -> NewDomainService:
    """Get new domain service instance."""
    return NewDomainService(app_state)

# Type alias for dependency injection
NewDomainServiceDep = Annotated[NewDomainService, Depends(get_new_domain_service)]
```

5. **Register Domain Router**
```python
# backend/api/router_config.py
from backend.api.domains.new_domain import create_new_domain_router

def register_domain_routers(app: FastAPI, feature_manager):
    """Register all domain routers."""

    # Check if new domain is enabled
    if feature_manager.is_enabled("new_domain_api"):
        new_domain_router = create_new_domain_router()
        app.include_router(
            new_domain_router,
            prefix="/api/v1",
            tags=["domains", "new-domain"]
        )
```

### Frontend Integration

1. **Generate TypeScript Types**
```typescript
// frontend/src/api/types/domains.ts
export interface NewDomainItemSchema {
  item_id: string;
  name: string;
  status: string;
  created_at: string;
}

export interface NewDomainCollectionSchema {
  items: NewDomainItemSchema[];
  total_count: number;
  page: number;
  page_size: number;
  has_next: boolean;
}
```

2. **Create API Client**
```typescript
// frontend/src/api/domains/newDomain.ts
import { apiGet, apiPost } from '../client';
import type { NewDomainItemSchema, NewDomainCollectionSchema } from '../types/domains';

export async function fetchNewDomainItems(
  params?: { page?: number; page_size?: number }
): Promise<NewDomainCollectionSchema> {
  const queryString = params ? buildQueryString(params) : '';
  const url = queryString ? `/api/v1/new-domain?${queryString}` : '/api/v1/new-domain';
  return apiGet<NewDomainCollectionSchema>(url);
}

export async function fetchNewDomainItem(itemId: string): Promise<NewDomainItemSchema> {
  return apiGet<NewDomainItemSchema>(`/api/v1/new-domain/${itemId}`);
}
```

3. **Create React Hooks**
```typescript
// frontend/src/hooks/domains/useNewDomain.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchNewDomainItems, fetchNewDomainItem } from '../../api/domains/newDomain';

export const newDomainQueryKeys = {
  all: ['new-domain-v2'] as const,
  items: () => [...newDomainQueryKeys.all, 'items'] as const,
  item: (id: string) => [...newDomainQueryKeys.items(), id] as const,
};

export function useNewDomainItems(params?: { page?: number; page_size?: number }) {
  return useQuery({
    queryKey: newDomainQueryKeys.items(),
    queryFn: () => fetchNewDomainItems(params),
    staleTime: 30000,
  });
}

export function useNewDomainItem(itemId: string, enabled = true) {
  return useQuery({
    queryKey: newDomainQueryKeys.item(itemId),
    queryFn: () => fetchNewDomainItem(itemId),
    enabled: enabled && !!itemId,
    staleTime: 30000,
  });
}
```

## Testing Patterns

### Backend Testing

```python
# tests/api/test_domain_new_domain.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock

from backend.main import app
from backend.schemas.new_domain import NewDomainItemSchema

class TestNewDomainAPI:
    """Test new domain API endpoints."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        """Set up mocks for testing."""
        # Mock domain service
        mock_service = AsyncMock()
        mock_service.list_items.return_value = [
            NewDomainItemSchema(
                item_id="item_001",
                name="Test Item",
                status="active",
                created_at="2024-01-01T00:00:00Z"
            )
        ]

        # Set up app state
        app.state.new_domain_service = mock_service

    def test_list_items_success(self):
        """Test successful item listing."""
        with TestClient(app) as client:
            response = client.get("/api/v1/new-domain")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["item_id"] == "item_001"

    def test_list_items_with_pagination(self):
        """Test item listing with pagination."""
        with TestClient(app) as client:
            response = client.get("/api/v1/new-domain?page=1&page_size=10")

            assert response.status_code == 200
```

### Frontend Testing

```typescript
// frontend/src/hooks/domains/__tests__/useNewDomain.test.tsx
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

import { useNewDomainItems } from '../useNewDomain';

// Mock API client
vi.mock('../../api/domains/newDomain', () => ({
  fetchNewDomainItems: vi.fn(),
}));

describe('useNewDomainItems', () => {
  const createWrapper = () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    return ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch items successfully', async () => {
    const { fetchNewDomainItems } = await import('../../api/domains/newDomain');
    vi.mocked(fetchNewDomainItems).mockResolvedValue({
      items: [{ item_id: 'test', name: 'Test', status: 'active', created_at: '2024-01-01T00:00:00Z' }],
      total_count: 1,
      page: 1,
      page_size: 50,
      has_next: false,
    });

    const { result } = renderHook(() => useNewDomainItems(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.items).toHaveLength(1);
  });
});
```

## Performance Optimization

### Caching Strategy

1. **Response Caching**
```python
# Configure cache TTL based on data volatility
CACHE_TTL_CONFIG = {
    "health": 60,           # Health checks - 1 minute
    "schemas": 600,         # Schemas - 10 minutes
    "list_items": 120,      # Item lists - 2 minutes
    "get_item": 300,        # Individual items - 5 minutes
}
```

2. **Cache Invalidation**
```python
# Automatic cache invalidation on writes
async def create_item(self, item_data: dict) -> NewDomainItemSchema:
    """Create item with cache invalidation."""
    result = await self._create_item_impl(item_data)

    # Invalidate related cache entries
    cache_patterns = [
        f"new-domain:list:*",
        f"new-domain:item:{result.item_id}",
    ]

    for pattern in cache_patterns:
        await invalidate_cache_pattern(pattern)

    return result
```

### Database Optimization

1. **Query Optimization**
```python
# Use efficient database queries
async def list_items_optimized(
    self,
    filters: Optional[dict] = None,
    page: int = 1,
    page_size: int = 50
) -> NewDomainCollectionSchema:
    """Optimized item listing with proper indexing."""

    # Build efficient query with indexes
    query = self.build_filtered_query(filters)

    # Use pagination with LIMIT/OFFSET
    offset = (page - 1) * page_size
    items = await query.offset(offset).limit(page_size).all()

    # Get total count efficiently
    total_count = await query.count()

    return NewDomainCollectionSchema(
        items=items,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_next=total_count > offset + page_size
    )
```

2. **Connection Pooling**
```python
# Configure database connection pooling
DATABASE_CONFIG = {
    "pool_size": 20,
    "max_overflow": 30,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}
```

## Security Considerations

### Authentication & Authorization

1. **Domain Permissions**
```python
# Define domain-specific permissions
class NewDomainPermissions:
    READ = "new_domain:read"
    WRITE = "new_domain:write"
    ADMIN = "new_domain:admin"

# Check permissions in endpoints
@require_domain_permission(NewDomainPermissions.WRITE)
async def create_item(
    item_data: dict,
    user_context: UserContextDep
) -> NewDomainItemSchema:
    """Create item with permission check."""
    pass
```

2. **Input Validation**
```python
# Comprehensive input validation
class CreateItemRequest(BaseModel):
    """Request schema for creating items."""

    name: str = Field(..., min_length=1, max_length=100, description="Item name")
    description: Optional[str] = Field(None, max_length=500, description="Item description")
    tags: List[str] = Field(default_factory=list, max_items=10, description="Item tags")

    @validator('name')
    def validate_name(cls, v):
        """Validate item name."""
        if not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()

    @validator('tags')
    def validate_tags(cls, v):
        """Validate tags."""
        return [tag.strip().lower() for tag in v if tag.strip()]
```

### Data Protection

1. **Sensitive Data Handling**
```python
# Exclude sensitive fields from responses
class PublicItemSchema(BaseModel):
    """Public item schema without sensitive data."""

    item_id: str
    name: str
    status: str

    class Config:
        # Exclude sensitive fields
        fields = {"internal_notes": {"write_only": True}}

# Use different schemas for different access levels
@router.get("/", response_model=List[PublicItemSchema])
async def list_items_public():
    """Public item listing without sensitive data."""
    pass

@router.get("/admin", response_model=List[DetailedItemSchema])
@require_domain_permission(NewDomainPermissions.ADMIN)
async def list_items_admin():
    """Admin item listing with full data."""
    pass
```

## Monitoring & Observability

### Metrics Collection

1. **Custom Metrics**
```python
# Domain-specific metrics
from backend.monitoring.domain_monitoring import domain_metrics

# Record domain-specific metrics
domain_metrics.domain_requests.labels(
    domain="new_domain",
    operation="create_item",
    method="POST",
    status_code=201,
    auth_method="jwt"
).inc()

domain_metrics.domain_request_duration.labels(
    domain="new_domain",
    operation="create_item",
    method="POST"
).observe(response_time)
```

2. **Health Checks**
```python
@router.get("/health")
async def health_check(service: NewDomainServiceDep) -> dict:
    """Comprehensive health check."""
    try:
        # Check database connectivity
        await service.health_check_db()

        # Check external dependencies
        await service.health_check_external_services()

        return {
            "status": "healthy",
            "domain": "new_domain",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "database": "healthy",
                "external_services": "healthy"
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "domain": "new_domain",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
```

### Logging

1. **Structured Logging**
```python
import structlog

logger = structlog.get_logger("new_domain")

async def create_item(self, item_data: dict) -> NewDomainItemSchema:
    """Create item with structured logging."""
    logger.info(
        "Creating new domain item",
        extra={
            "domain": "new_domain",
            "operation": "create_item",
            "user_id": self.get_current_user_id(),
            "item_name": item_data.get("name"),
        }
    )

    try:
        result = await self._create_item_impl(item_data)

        logger.info(
            "Successfully created domain item",
            extra={
                "domain": "new_domain",
                "operation": "create_item",
                "item_id": result.item_id,
                "execution_time_ms": self.get_execution_time(),
            }
        )

        return result

    except Exception as e:
        logger.error(
            "Failed to create domain item",
            extra={
                "domain": "new_domain",
                "operation": "create_item",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        raise
```

## Configuration Management

### Feature Flags

```yaml
# backend/services/feature_flags.yaml
new_domain_api:
  enabled: false
  core: false
  depends_on: [can_interface]
  description: "New domain API functionality"
  config:
    enable_bulk_operations: true
    max_items_per_request: 100
    enable_caching: true
    cache_ttl_seconds: 300
    enable_monitoring: true
```

### Environment Configuration

```python
# backend/core/config.py
class NewDomainSettings(BaseSettings):
    """Configuration for new domain."""

    enable_new_domain: bool = Field(False, env="COACHIQ_NEW_DOMAIN__ENABLED")
    max_items_per_page: int = Field(50, env="COACHIQ_NEW_DOMAIN__MAX_ITEMS_PER_PAGE")
    cache_ttl: int = Field(300, env="COACHIQ_NEW_DOMAIN__CACHE_TTL")

    class Config:
        env_prefix = "COACHIQ_NEW_DOMAIN__"
```

## Deployment Considerations

### Database Migrations

```python
# alembic/versions/001_add_new_domain_tables.py
def upgrade():
    """Add new domain tables."""
    op.create_table(
        'new_domain_items',
        sa.Column('item_id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Add indexes for performance
    op.create_index('idx_new_domain_items_status', 'new_domain_items', ['status'])
    op.create_index('idx_new_domain_items_created_at', 'new_domain_items', ['created_at'])
```

### Monitoring Alerts

```yaml
# monitoring/alerts/new_domain.yaml
alerts:
  - name: NewDomainHighErrorRate
    condition: rate(domain_api_errors_total{domain="new_domain"}[5m]) > 0.1
    severity: warning
    description: "High error rate in new domain API"

  - name: NewDomainSlowResponse
    condition: histogram_quantile(0.95, domain_api_request_duration_seconds{domain="new_domain"}) > 2
    severity: warning
    description: "Slow response times in new domain API"
```

## Best Practices Summary

1. **Code Organization**: Follow domain-driven structure consistently
2. **Type Safety**: Use Pydantic + TypeScript for end-to-end type safety
3. **Error Handling**: Implement comprehensive error handling with proper HTTP status codes
4. **Performance**: Implement caching, pagination, and monitoring from the start
5. **Security**: Apply authentication, authorization, and input validation
6. **Testing**: Write comprehensive tests for all components
7. **Documentation**: Document APIs, schemas, and usage patterns
8. **Monitoring**: Add metrics, logging, and health checks
9. **Configuration**: Use feature flags and environment-based configuration
10. **Migration**: Provide compatibility layers and migration paths

This development guide ensures consistent implementation patterns across all domain APIs while maintaining high quality, performance, and security standards.
