"""
Tests for enhanced service dependency resolver.

Part of Phase 2F: Service Dependency Resolution Enhancement
"""

import pytest
from backend.core.service_dependency_resolver import (
    DependencyError,
    DependencyType,
    ServiceDependency,
    ServiceDependencyResolver,
)


class TestServiceDependencyResolver:
    """Test cases for ServiceDependencyResolver."""

    def test_simple_dependency_chain(self):
        """Test resolution of simple A→B→C dependency chain."""
        resolver = ServiceDependencyResolver()

        # C depends on nothing
        resolver.add_service("C", [])

        # B depends on C
        resolver.add_service("B", [ServiceDependency("C")])

        # A depends on B
        resolver.add_service("A", [ServiceDependency("B")])

        stages = resolver.resolve_dependencies()

        assert len(stages) == 3
        assert stages[0] == ["C"]
        assert stages[1] == ["B"]
        assert stages[2] == ["A"]

    def test_parallel_services(self):
        """Test services with no dependencies can start in parallel."""
        resolver = ServiceDependencyResolver()

        # Multiple services with no dependencies
        resolver.add_service("A", [])
        resolver.add_service("B", [])
        resolver.add_service("C", [])

        stages = resolver.resolve_dependencies()

        assert len(stages) == 1
        assert set(stages[0]) == {"A", "B", "C"}

    def test_diamond_dependency(self):
        """Test diamond dependency pattern: A→B,C→D."""
        resolver = ServiceDependencyResolver()

        # D depends on nothing
        resolver.add_service("D", [])

        # B and C depend on D
        resolver.add_service("B", [ServiceDependency("D")])
        resolver.add_service("C", [ServiceDependency("D")])

        # A depends on B and C
        resolver.add_service("A", [
            ServiceDependency("B"),
            ServiceDependency("C"),
        ])

        stages = resolver.resolve_dependencies()

        assert len(stages) == 3
        assert stages[0] == ["D"]
        assert set(stages[1]) == {"B", "C"}
        assert stages[2] == ["A"]

    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies."""
        resolver = ServiceDependencyResolver()

        # A → B → C → A (circular)
        resolver.add_service("A", [ServiceDependency("B")])
        resolver.add_service("B", [ServiceDependency("C")])
        resolver.add_service("C", [ServiceDependency("A")])

        with pytest.raises(DependencyError) as exc_info:
            resolver.resolve_dependencies()

        assert "Circular dependencies detected" in str(exc_info.value)
        assert "A → B → C → A" in str(exc_info.value)

    def test_missing_dependency(self):
        """Test error on missing dependency."""
        resolver = ServiceDependencyResolver()

        # A depends on B, but B is not registered
        resolver.add_service("A", [ServiceDependency("B")])

        with pytest.raises(DependencyError) as exc_info:
            resolver.resolve_dependencies()

        assert "missing required dependencies" in str(exc_info.value)
        assert "B" in str(exc_info.value)
        assert "Available services: A" in str(exc_info.value)

    def test_optional_dependency(self):
        """Test optional dependencies don't fail if missing."""
        resolver = ServiceDependencyResolver()

        # A has optional dependency on B
        resolver.add_service("A", [
            ServiceDependency("B", type=DependencyType.OPTIONAL)
        ])

        stages = resolver.resolve_dependencies()

        assert len(stages) == 1
        assert stages[0] == ["A"]

    def test_fallback_dependency(self):
        """Test fallback dependencies."""
        resolver = ServiceDependencyResolver()

        # A depends on B with fallback to C
        resolver.add_service("A", [
            ServiceDependency("B", fallback="C")
        ])

        # Only C is available
        resolver.add_service("C", [])

        stages = resolver.resolve_dependencies()

        # Should use fallback C
        assert len(stages) == 2
        assert stages[0] == ["C"]
        assert stages[1] == ["A"]

    def test_runtime_dependency_validation(self):
        """Test runtime dependency validation."""
        resolver = ServiceDependencyResolver()

        # A has runtime dependency on B
        resolver.add_service("A", [
            ServiceDependency("B", type=DependencyType.RUNTIME)
        ])

        # B has runtime dependency on C
        resolver.add_service("B", [
            ServiceDependency("C", type=DependencyType.RUNTIME)
        ])

        stages = resolver.resolve_dependencies()

        # Both can start immediately (runtime deps not required for startup)
        assert len(stages) == 1
        assert set(stages[0]) == {"A", "B"}

        # Validate runtime dependencies
        missing = resolver.validate_runtime_dependencies({"A", "B"})
        assert "A" in missing
        assert "B" in missing[0]
        assert "B" in missing
        assert "C" in missing[1]

    def test_dependency_report(self):
        """Test dependency report generation."""
        resolver = ServiceDependencyResolver()

        # Create a small service graph
        resolver.add_service("database", [])
        resolver.add_service("cache", [])
        resolver.add_service("auth", [ServiceDependency("database")])
        resolver.add_service("api", [
            ServiceDependency("auth"),
            ServiceDependency("cache"),
        ])

        resolver.resolve_dependencies()
        report = resolver.get_dependency_report()

        assert "Service Dependency Report" in report
        assert "Startup Stages" in report
        assert "Stage 0: cache, database" in report or "Stage 0: database, cache" in report
        assert "Stage 1: auth" in report
        assert "Stage 2: api" in report
        assert "Parallelization Analysis" in report
        assert "2 services can start in parallel" in report

    def test_impacted_services(self):
        """Test finding services impacted by failure."""
        resolver = ServiceDependencyResolver()

        # Create dependency tree
        resolver.add_service("core", [])
        resolver.add_service("service1", [ServiceDependency("core")])
        resolver.add_service("service2", [ServiceDependency("core")])
        resolver.add_service("app1", [ServiceDependency("service1")])
        resolver.add_service("app2", [
            ServiceDependency("service1"),
            ServiceDependency("service2"),
        ])

        resolver.resolve_dependencies()

        # If core fails, all services are impacted
        impacted = resolver.get_impacted_services("core")
        assert impacted == {"service1", "service2", "app1", "app2"}

        # If service1 fails, only its dependents are impacted
        impacted = resolver.get_impacted_services("service1")
        assert impacted == {"app1", "app2"}

        # If app1 fails, no other services impacted
        impacted = resolver.get_impacted_services("app1")
        assert impacted == set()

    def test_mermaid_export(self):
        """Test Mermaid diagram export."""
        resolver = ServiceDependencyResolver()

        resolver.add_service("A", [])
        resolver.add_service("B", [ServiceDependency("A")])
        resolver.add_service("C", [ServiceDependency("A")])
        resolver.add_service("D", [
            ServiceDependency("B"),
            ServiceDependency("C"),
        ])

        resolver.resolve_dependencies()
        diagram = resolver.export_mermaid_diagram()

        assert "graph TD" in diagram
        assert "subgraph Stage0[Stage 0]" in diagram
        assert "A" in diagram
        assert "A --> B" in diagram
        assert "A --> C" in diagram
        assert "B --> D" in diagram
        assert "C --> D" in diagram

    def test_complex_dependency_optimization(self):
        """Test stage optimization for complex dependencies."""
        resolver = ServiceDependencyResolver()

        # Create a complex graph where optimization matters
        resolver.add_service("config", [])
        resolver.add_service("logger", [])
        resolver.add_service("database", [ServiceDependency("config")])
        resolver.add_service("cache", [ServiceDependency("config")])
        resolver.add_service("auth", [
            ServiceDependency("database"),
            ServiceDependency("logger"),
        ])
        resolver.add_service("api", [
            ServiceDependency("auth"),
            ServiceDependency("cache"),
        ])

        stages = resolver.resolve_dependencies()

        # Verify optimal staging
        assert len(stages) == 4

        # Stage 0: Independent services
        assert set(stages[0]) == {"config", "logger"}

        # Stage 1: Services depending only on stage 0
        assert set(stages[1]) == {"database", "cache"}

        # Stage 2: Auth (depends on database and logger)
        assert stages[2] == ["auth"]

        # Stage 3: API (depends on auth and cache)
        assert stages[3] == ["api"]

    def test_multiple_circular_dependencies(self):
        """Test detection of multiple circular dependency paths."""
        resolver = ServiceDependencyResolver()

        # Create two circular dependencies
        # Circle 1: A → B → A
        resolver.add_service("A", [ServiceDependency("B")])
        resolver.add_service("B", [ServiceDependency("A")])

        # Circle 2: X → Y → Z → X
        resolver.add_service("X", [ServiceDependency("Y")])
        resolver.add_service("Y", [ServiceDependency("Z")])
        resolver.add_service("Z", [ServiceDependency("X")])

        with pytest.raises(DependencyError) as exc_info:
            resolver.resolve_dependencies()

        error_msg = str(exc_info.value)
        assert "Circular dependencies detected" in error_msg
        # Should show at least one circular path
        assert " → " in error_msg
