# ADR-0002: Single `CANFacade` as the only entry point for CAN operations

## Status

**Accepted**, 2026-05-13. Codifies the consolidation that landed in
mid-2025 (see archived plan at
`docs/archive/can-service-consolidation-plan-2025.md` for the original
1272-line implementation roadmap and FMEA-style design rationale).

## Context

In early 2025 the backend had several services touching the CAN bus
without coordinating with each other:

- `CANService` (high-level API operations).
- `CANBusService` (raw message processing).
- `CANInterfaceService` (interface name → device-path mapping).
- `CANMessageInjector` (test-frame injection).
- `CANMessageFilter` (subscription filtering).
- `CANBusRecorder` (recording / replay).
- `CANProtocolAnalyzer` (protocol analysis).
- An inbound anomaly detector (retired in July 2026 after live profiling showed
  only false-positive advisory alerts and no effective API-side protection).

Several of these duplicated state (e.g. multiple components owned an
in-flight statistics counter), and there was no single place where an
emergency-stop request could fan out to "stop everything CAN-related,
right now". Routers reached into different services depending on
historical accident, which made auth and rate-limiting policy
inconsistent across endpoints.

For a system whose CAN frames have physical consequences via Firefly
(see [ADR-0004](ADR-0004-coachiq-is-not-the-safety-system.md)), having
no single coordination point was a real risk -- not because
CAN-related code is "safety-critical" in the certification sense, but
because emergency-stop *coordination* is exactly the kind of
cross-cutting concern a facade pattern is designed for.

## Decision

All CAN operations go through a single **`CANFacade`** service that:

- Implements the `GuardrailParticipant` interface (so it participates in the
  `CommandGuardrailService`'s emergency-stop coordination).
- Has `guardrail_tier = GuardrailTier.CRITICAL` (for
  the audit-trail / shutdown-ordering machinery).
- Owns references to the underlying CAN services (CANBusService,
  CANMessageInjector, CANMessageFilter, CANBusRecorder,
  CANProtocolAnalyzer, etc.) and dispatches through them.
- Is the **only** service that routers and other services depend on
  for CAN access. New code does not import the underlying services
  directly.

Routers receive the facade via:
```python
from typing import Annotated
from fastapi import APIRouter, Depends
from backend.core.dependencies import get_can_facade
from backend.services.can.can_facade import CANFacade

router = APIRouter()

@router.post("/api/can/send")
async def send_can_frame(
    facade: Annotated[CANFacade, Depends(get_can_facade)],
    ...
):
    return await facade.send_message(...)
```

## Consequences

### Becomes easier
- **Emergency-stop coordination**: one method on `CANFacade` halts
  every CAN-side operation in a consistent order. Before, that fan-out
  was implicit and incomplete.
- **Auth / rate-limit policy uniformity**: every CAN endpoint goes
  through the facade, so policy lives in one place.
- **Discoverability**: someone exploring the codebase looks at
  `CANFacade` once and sees the whole CAN surface area.
- **Testing**: mock one `CANFacade` instead of stitching together
  mocks for 6+ underlying services.

### Becomes harder
- **Adding a new CAN-side capability**: requires adding a method on
  the facade (and the underlying service it delegates to). That's a
  small extra step compared to "just create a new service and import
  it from a router".
- **The facade itself can become a god-object** if we don't push back
  on bloat. Mitigation: keep the facade interface focused on the
  public CAN operations; let the underlying services own their own
  internal state. The facade is a coordinator, not a re-implementer.

### Cannot do anymore
- Have routers reach directly into `CANBusService` or other
  underlying services. (Existing test code that does this is being
  cleaned up; new code is reviewed against this rule.)

## Alternatives considered

### Keep the per-service status quo
Already painful when this consolidation was proposed. Adding more
CAN-side features would have made it worse.

### Use a dependency-injected event bus
Some teams solve this with a pub/sub event bus where any service can
publish CAN events and any service can subscribe. Considered and
rejected for two reasons:

1. Async event-bus patterns make causality hard to reason about.
   When a CAN frame is rejected, you want a stack trace that goes
   from the API call to the rejection -- not "frame published to
   bus, eventually filtered, eventually denied".
2. Emergency-stop coordination is a *synchronous* thing. The facade
   pattern's "single ordered shutdown" is exactly what we need.

### Inheritance hierarchy (CANBusService extends CANService extends ...)
Fragile and obscures intent. Composition (facade delegates to
focused services) is clearer.

## See also

- `backend/services/can_facade.py` -- the implementation.
- `backend/services/can_bus_service.py` -- the largest underlying
  service that the facade delegates to.
- `backend/integrations/can/` -- the lower-level integrations (message
  factories, interface adapters, multi-network manager) that the
  underlying services in turn use.
- `backend/services/command_guardrail_service.py` -- the consumer of the
  `GuardrailParticipant` interface, which the facade implements for
  emergency-stop coordination.
- `docs/archive/can-service-consolidation-plan-2025.md` -- the
  original implementation plan (preserved for the FMEA-style rationale).
- [ADR-0004](ADR-0004-coachiq-is-not-the-safety-system.md) -- the
  framing that explains why "CRITICAL safety classification" here means
  "important for the audit log and shutdown ordering", not "certified
  safety-critical software".
