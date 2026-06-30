# ADR-0013: Add PocketID OIDC login and an embedded MCP OAuth AS

## Status

**Accepted**, 2026-06-30. Graduates the HOF-046 auth architecture umbrella.

## Context

CoachIQ is preparing to be reachable at a public origin while preserving the
offline-first behavior required by an RV appliance. The existing local auth
system supports local admin password login, refresh tokens, MFA/TOTP,
magic-link login, invitations, PIN auth, and local JWT sessions. That local
system is the break-glass path when the coach has no internet.

The public deployment also needs two federation surfaces:

- Human web login through PocketID at `https://id.holthome.net`.
- An embedded OAuth 2.1 Authorization Server for MCP clients, protecting the
  future CoachIQ MCP resource mounted at `/api/mcp`.

The live PocketID discovery document is the source of truth for the upstream
IdP. It reports issuer `https://id.holthome.net`, authorization endpoint
`https://id.holthome.net/authorize`, token endpoint
`https://id.holthome.net/api/oidc/token`, userinfo endpoint
`https://id.holthome.net/api/oidc/userinfo`, JWKS endpoint
`https://id.holthome.net/.well-known/jwks.json`, and end-session endpoint
`https://id.holthome.net/api/oidc/end-session`. PocketID supports auth-code
flow, PKCE `S256`, RS256 ID tokens, confidential clients with
`client_secret_basic` or `client_secret_post`, RFC 9207 authorization response
issuer validation, and the `openid profile email groups` scopes.

The MCP AS must conform to `carpenike/mcp-as-contract` v1.1.0. The public
CoachIQ origin is `https://iq.holtel.io`, and the MCP resource path is
`/api/mcp`.

## Decision

Add PocketID as an additive OIDC login capability over the existing local auth
modes. Do not add a fourth exclusive `AuthMode`. `AuthMode` remains the local
user-population mode (`none`, `single`, `multi`); PocketID is represented as an
enabled federated-login capability with provider metadata. A CoachIQ local
session can be established by either local auth or OIDC, and both yield the same
local JWT session shape consumed by the current API and SPA.

Use PocketID `sub` as the stable federated identity key. Phase 1 adds an OIDC
provider value, provider-binding lookup/upsert helpers, and a uniqueness
guarantee for `(provider, provider_user_id)`. Email, username, display name,
and groups are mutable claims refreshed at login.

Make PocketID group membership the access-control gate for OIDC login. The
configuration maps PocketID group names to CoachIQ roles. A user must belong to
at least one mapped group to log in. If multiple mapped groups match, choose the
highest privilege: `admin` > `user` > `readonly`. Do not infer admin or user
privilege from email or any unmapped claim. The canonical mapped role set is
`admin`, `user`, and `readonly`; OIDC does not mint an `operator` role unless a
future ADR redefines the public role vocabulary.

Remove the dead GitHub/Google/Microsoft OAuth scaffolding in the same phase that
adds PocketID. Replace the generic `oauth_enabled` vocabulary with
PocketID/OIDC-specific settings, status fields, frontend types, and docs.

Add named public URL settings instead of overloading the magic-link `base_url`:

- `COACHIQ_SERVER__PUBLIC_ORIGIN=https://iq.holtel.io`
- `COACHIQ_MCP__PATH=/api/mcp`

Startup must validate that the public origin is an absolute origin only
(scheme, host, optional port; no path and no trailing slash) whenever OIDC or
the MCP AS is enabled. The same configured origin and MCP path derive the OAuth
issuer, metadata URLs, protected-resource metadata `resource`, and
`WWW-Authenticate` `resource_metadata` hint.

For the MCP AS, implement the `pocketid-mcp-as` v1.1.0 contract with:

- Token profile `opaque-no-refresh`.
- Scope posture `mcp-only`.
- Opaque PAT-shaped access tokens prefixed `ciqpat_`.
- SHA-256 hashed token handles at rest, revocation, and a 90-day TTL.
- No refresh tokens and no `jwks_uri` in AS metadata.
- Dynamic client registration with allowlist-filtered redirect URIs.
- Two independent PKCE legs: MCP client to CoachIQ AS, and CoachIQ AS to
  PocketID.

Expose new human OIDC endpoints under `/api/v1`. The OAuth AS contract-fixed
paths (`/.well-known/*` and `/oauth/*`) are explicit exceptions to the `/api/v1`
rule because MCP clients require those exact discovery locations.

## Consequences

### Becomes easier

- Public users can authenticate with PocketID without weakening the local
  offline login path.
- MCP clients get a standard OAuth 2.1 flow and can discover the AS through RFC
  8414 and RFC 9728 metadata.
- Group membership in PocketID becomes the single deploy-time access-control
  source for federated users.
- CoachIQ avoids carrying unused GitHub/Google/Microsoft OAuth settings into its
  first public release.

### Becomes harder

- Auth mode is no longer enough to describe login choices; callers must also
  understand OIDC capability/status fields.
- OIDC login requires provider-binding schema and repository work, not only an
  endpoint and token exchange.
- Public endpoint middleware, CSRF exemptions, rate limits, and audit logging
  must be updated deliberately for OIDC and OAuth protocol endpoints.
- The public-origin byte-match requirement turns URL configuration mistakes into
  startup failures.

### Cannot do anymore

- Treat PocketID as a replacement for local auth or require internet access for
  break-glass login.
- Use email as the stable federated identity key.
- Accept OIDC users that do not belong to a configured mapped group.
- Reuse the dormant GitHub/Google/Microsoft OAuth provider scaffolding as the
  public API shape.
- Publish an MCP AS metadata document that omits the path-suffixed protected
  resource metadata or advertises a `resource` that does not byte-match the MCP
  URL.

## Alternatives considered

- **Add a `FEDERATED` auth mode**: rejected because the current code treats
  `AuthMode` as a mutually-exclusive gate. A fourth mode would disable local
  password/MFA/magic-link paths unless many local guards and frontend unions
  were rewritten around composite semantics.
- **Use PocketID email as the local user key**: rejected because email can
  change. PocketID `sub` is stable and must be bound through the provider table.
- **Allow any authenticated PocketID user as readonly**: rejected by host
  decision. Login is group-gated and fail-closed.
- **Shared PAT token posture for MCP**: rejected because CoachIQ has no general
  user-facing PAT system to reuse. `mcp-only` gives the smallest blast radius.
- **JWT+refresh token MCP profile**: rejected because MCP clients can rerun the
  OAuth flow on expiry, and opaque no-refresh tokens avoid JWKS/key-rotation
  surface for this appliance.

## Revisit conditions

- CoachIQ introduces a general user-facing PAT system before the MCP AS ships.
- MCP client requirements change in a new `pocketid-mcp-as` contract version.
- PocketID changes discovery, token signing, group-claim behavior, or upstream
  OIDC endpoint paths.
- The public deployment origin changes from `https://iq.holtel.io`.

## See also

- `docs/specs/AUTH_OIDC_MCP_PLAN.md`
- [ADR-0004](ADR-0004-coachiq-is-not-the-safety-system.md) -- API guardrails,
  not vehicle safety.
- [ADR-0007](ADR-0007-auth-service-namespace.md) -- Auth service namespace and
  AuthManager/AuthService split.
- [ADR-0010](ADR-0010-pre-1.0-no-backward-compat.md) -- decisive cleanup before
  public release.
- [ADR-0011](ADR-0011-public-api-v1-naming.md) -- public `/api/v1` naming.
- HOF-046 in the CoachIQ handoff channel.
