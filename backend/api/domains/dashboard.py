"""Dashboard domain API for synchronized user customization."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.api.domains import register_domain_router
from backend.core.dependencies import get_authenticated_user, root_service_dependency
from backend.models.dashboard import DashboardPreferencesResponse, DashboardPreferencesUpdate
from backend.services.system.dashboard_service import DashboardService

get_dashboard_service = root_service_dependency("dashboard_service")


def _authenticated_user_id(user: dict[str, Any]) -> str:
    """Return the stable identity supplied by the authentication dependency."""
    user_id = user.get("user_id") or user.get("sub") or user.get("username")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user identity is unavailable")
    return str(user_id)


def _preferences_response(config: dict[str, Any]) -> DashboardPreferencesResponse:
    """Project a dashboard configuration onto the public preference contract."""
    preferences = config.get("preferences")
    home = preferences.get("home") if isinstance(preferences, dict) else None
    return DashboardPreferencesResponse(home=home, updated_at=config["updated_at"])


def create_dashboard_router() -> APIRouter:
    """Create the v1 dashboard domain router."""
    router = APIRouter(tags=["dashboard"])

    @router.get(
        "/preferences",
        response_model=DashboardPreferencesResponse,
        summary="Get Home preferences",
        description="Get synchronized Home customization for the current authenticated user.",
        response_description="Saved Home preferences, or null before the first synchronized update",
    )
    async def get_dashboard_preferences(
        dashboard_service: Annotated[DashboardService, Depends(get_dashboard_service)],
        user: Annotated[dict[str, Any], Depends(get_authenticated_user)],
    ) -> DashboardPreferencesResponse:
        """Get the current user's synchronized Home preferences."""
        config = await dashboard_service.get_dashboard_config(_authenticated_user_id(user))
        return _preferences_response(config)

    @router.put(
        "/preferences",
        response_model=DashboardPreferencesResponse,
        summary="Update Home preferences",
        description="Replace synchronized Home customization for the current authenticated user.",
        response_description="The saved Home preferences and update timestamp",
    )
    async def update_dashboard_preferences(
        update: DashboardPreferencesUpdate,
        dashboard_service: Annotated[DashboardService, Depends(get_dashboard_service)],
        user: Annotated[dict[str, Any], Depends(get_authenticated_user)],
    ) -> DashboardPreferencesResponse:
        """Replace the current user's synchronized Home preferences."""
        config = await dashboard_service.update_dashboard_preferences(
            _authenticated_user_id(user),
            {"home": update.home.model_dump(by_alias=True)},
        )
        return _preferences_response(config)

    return router


@register_domain_router("dashboard")
def register_dashboard_router() -> APIRouter:
    """Register the dashboard domain router."""
    return create_dashboard_router()
