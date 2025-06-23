"""
Documentation API Router

FastAPI router for documentation search and API schema operations.
This router delegates business logic to the DocsService.

Routes:
- GET /docs/status: Get status of the vector search service
- GET /docs/search: Search RV-C documentation using vector embeddings
- GET /docs/openapi: Get the OpenAPI schema for the API
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.dependencies import (
    create_service_dependency,
)

# Create service dependencies
get_docs_service = create_service_dependency("docs_service")
get_vector_service = create_service_dependency("vector_service")

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(prefix="/api/docs", tags=["documentation"])


@router.get(
    "/status",
    response_model=dict[str, Any],
    summary="Get documentation search status",
    description="Returns the status of the vector search service and its configuration.",
)
async def get_search_status(
    vector_service: Annotated[Any, Depends(get_vector_service)],
) -> dict[str, Any]:
    """Get the status of the vector search service."""
    logger.debug("GET /docs/status - Retrieving documentation search status")

    try:
        status = vector_service.get_status()
        is_available = vector_service.is_available()

        result = {
            "vector_search": {
                "available": is_available,
                **status,
            }
        }

        if is_available:
            logger.info("Documentation search service is available and operational")
        else:
            logger.warning(
                f"Documentation search service is not available: {status.get('error', 'Unknown error')}"
            )

        return result
    except Exception as e:
        logger.error(f"Error retrieving documentation search status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/search",
    response_model=list[dict[str, Any]],
    summary="Search RV-C documentation",
    description="Search the RV-C documentation using vector-based semantic search.",
)
async def search_documentation(
    vector_service: Annotated[Any, Depends(get_vector_service)],
    query: str = Query(..., description="Search query string"),
    k: int = Query(3, description="Number of results to return", ge=1, le=10),
) -> list[dict[str, Any]]:
    """
    Search the RV-C documentation using vector-based semantic search.

    Args:
        query: Natural language search query
        k: Number of results to return (between 1 and 10)

    Returns:
        List of search results with content and metadata

    Raises:
        HTTPException: If search fails or service is unavailable
    """
    logger.info(f"GET /docs/search - Searching documentation with query: '{query}' (k={k})")

    try:
        if not vector_service.is_available():
            status = vector_service.get_status()
            error_detail = status.get("error", "Unknown error")
            logger.error(f"Vector search service is not available: {error_detail}")
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Vector search service is not available: {error_detail}. "
                    "Run 'python scripts/setup_faiss.py --setup' to configure the search feature."
                ),
            )

        results = vector_service.similarity_search(query, k=k)
        logger.info(
            f"Documentation search completed: found {len(results)} results for query '{query}'"
        )
        return results

    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error(f"Runtime error in vector search for query '{query}': {e}")
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error in vector search for query '{query}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during the search.",
        ) from e


@router.get(
    "/openapi",
    response_model=dict[str, Any],
    summary="Get OpenAPI schema",
    description="Returns the complete OpenAPI schema for the API.",
)
async def get_openapi_schema(
    docs_service: Annotated[Any, Depends(get_docs_service)],
) -> dict[str, Any]:
    """Get the complete OpenAPI schema for the API."""
    logger.debug("GET /docs/openapi - Retrieving OpenAPI schema")

    try:
        schema = await docs_service.get_openapi_schema()

        # Count schema elements for logging
        paths_count = len(schema.get("paths", {}))
        components_count = len(schema.get("components", {}).get("schemas", {}))
        logger.info(f"Retrieved OpenAPI schema: {paths_count} paths, {components_count} components")
        return schema
    except Exception as e:
        logger.error(f"Error generating OpenAPI schema: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error generating OpenAPI schema",
        ) from e
