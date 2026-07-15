"""Root-owned composition order drift guards."""

# ruff: noqa: PLR2004, S101, SLF001

from backend.core.composition_root import CompositionRoot


def test_root_baked_order_contains_expected_services_once() -> None:
    """Baked root construction order contains every expected service once."""
    root = CompositionRoot()
    service_order = root._root_service_order

    assert len(service_order) == len(set(service_order))
    assert set(service_order) == root._service_catalog
    assert "can_anomaly_detector" not in service_order


def test_root_baked_order_preserves_required_edges() -> None:
    """Baked construction order preserves key dependency edges."""
    root = CompositionRoot()
    order = {name: index for index, name in enumerate(root._root_service_order)}

    must_precede = [
        ("database_manager", "database_connection_repository"),
        ("database_manager", "entity_manager_service"),
        ("rvc_config_repository", "rvc_config_facade"),
        ("persistence_repository", "persistence_service"),
        ("can_bus_service", "can_facade"),
        ("can_message_injector", "can_facade"),
        ("can_message_filter", "can_facade"),
        ("can_bus_recorder", "can_facade"),
        ("can_protocol_analyzer", "can_facade"),
        ("can_interface_service", "can_facade"),
        ("credential_repository", "auth_manager"),
        ("session_repository", "auth_manager"),
        ("token_service", "auth_manager"),
        ("session_service", "auth_manager"),
        ("lockout_service", "auth_manager"),
        ("event_broker", "entity_domain_service"),
        ("entity_service", "entity_domain_service"),
        ("entity_manager_service", "entity_domain_service"),
    ]

    for before, after in must_precede:
        assert order[before] < order[after]
