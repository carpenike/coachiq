# RouterOS Sidecar Plan

**Status:** approved for implementation via HOF-073
**Date:** 2026-07-02
**Component:** backend + NixOS module

## Purpose

The RouterOS sidecar is a tiny LAN-only HTTP surface for the RV MikroTik router.
RouterOS polls bare text endpoints every minute and uses the tokens to decide
home/away behavior and Starlink-to-cellular failover.

This surface is intentionally separate from the main CoachIQ API. It is not a
domain API, not mounted under `/api/v1`, not served through Caddy, and not behind
CoachIQ auth, TLS, CSRF, or the SPA fallback. The router is the only intended
client, on the RV LAN.

## Listener Model

CoachIQ still starts the main FastAPI app normally. When
`COACHIQ_ROUTER_SIDECAR__ENABLED=true`, the main app lifespan starts a second
`uvicorn.Server(...).serve()` task for a standalone FastAPI app bound to
`COACHIQ_ROUTER_SIDECAR__HOST` and `COACHIQ_ROUTER_SIDECAR__PORT` (default
`0.0.0.0:8100`). Shutdown sets `server.should_exit` and awaits the task before
the composition root is torn down.

The sidecar app must never be included on the main app with `include_router`.
Keeping the listener distinct is the deliberate ADR-0003/auth-model exception.

## Token Endpoints

All endpoints return HTTP 200 `text/plain` with a single lowercase token and a
trailing newline. Requests never perform live gpsd or Starlink reads; they only
return cached values from background pollers.

- `GET /healthz` -> `ok`
- `GET /location-state` -> `home`, `away`, or `unknown`
- `GET /starlink/verdict` -> `healthy`, `degraded`, `down`, or `unknown`
- `GET /starlink/raw` -> compact `key=value` diagnostics

`unknown` is the safe sentinel. Stale or absent GPS must never report `home`.
Unreachable Starlink must never guess a failover state.

## Starlink Telemetry JSON

The sidecar also exposes cached whole-message Starlink telemetry as JSON for
debugging and local automation. These endpoints are still LAN-only and unauth'd,
but they are not RouterOS token endpoints:

- `GET /starlink/status`
- `GET /starlink/history?window=N`
- `GET /starlink/diagnostics`
- `GET /starlink/device-info`

Each response is wrapped as `{ fetched_at, age_s, stale, error, data }`. A never
polled source returns `stale: true` and `data: null`; a poll failure keeps the
last-good `data` but marks it stale. The Starlink client serializes protobufs
with `preserving_proto_field_name=True`, so the JSON payload uses proto-native
snake_case keys.

## Starlink Verdict State Machine

`/starlink/verdict` is still a single plain-text token, but it is backed by a
state machine so transient dish telemetry does not flap RouterOS failover:

- Immediate `down` is limited to a current Starlink `outage` or
  `disablement_code != OKAY`.
- `ready_states.cady` is excluded everywhere because it is false on the healthy
  live dish.
- Continuous signals use hysteresis: enter degraded at the configured high
  threshold and recover only below the configured lower threshold. This applies
  to obstruction fraction and windowed PoP ping drop/latency averages.
- Boolean signals use time dwell, not thresholds. This includes
  `currently_obstructed`, direct `alerts{}` booleans, non-cady ready states,
  and SNR booleans.
- Recovery from `down` and transitions between `healthy` and `degraded` must
  persist for the configured dwell interval before the published token changes.
- Obstruction values with companion `*valid` flags are ignored when invalid;
  string `"NaN"` is treated as no signal for verdict math.

## Grounded Hardware Facts

The implementation was grounded against the RV LAN before coding:

- gpsd is active on `nixpi` and listens on `127.0.0.1:2947`.
- Live gpsd TPV fixes include `mode=3`, `status=2`, `time`, `lat`, `lon`, and
  accuracy fields.
- The Starlink dish at `192.168.100.1:9200` supports gRPC reflection for
  `SpaceX.API.Device.Device/Handle`.
- Dish status/history fields are verified from reflection and live calls. The
  protobuf names are snake_case; the sidecar telemetry JSON preserves those
  names. grpcurl's default JSON uses lowerCamel, but CoachIQ intentionally uses
  proto-native casing for this surface.
- `readyStates.cady` is false on the working dish, so it is not a `down` signal.
  The `down` rule is active outage or unreachable only.

## NixOS Exposure

The NixOS module exposes first-class `services.coachiq.routerSidecar.*` options.
Opening the firewall requires explicit LAN interface names:

```nix
services.coachiq.routerSidecar = {
  enable = true;
  host = "0.0.0.0";
  port = 8100;
  openFirewall = true;
  lanInterfaces = [ "br-lan" ];
};
```

Do not expose port 8100 through the Cloudflare tunnel or WAN firewall.
