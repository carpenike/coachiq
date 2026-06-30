# Auth OIDC and MCP OAuth AS Plan

**Status:** approved umbrella architecture, HOF-046
**Author:** Claude (HQ), graduated by Copilot
**Date:** 2026-06-30
**Component:** both (backend + frontend), plus the embedded MCP AS

This is the durable implementation plan for adding PocketID OIDC login and an
embedded MCP OAuth 2.1 Authorization Server to CoachIQ. ADR-0013 records the
architecture decision; this plan defines the phase boundaries and checklists.

---

## 1. Goals

CoachIQ must support two related but distinct auth workflows:

1. Human web users can sign in with PocketID while the existing local auth
   system remains available offline.
2. MCP clients can authenticate through an embedded OAuth 2.1 AS that federates
   login to PocketID and protects the MCP resource at `/api/mcp`.

Offline-first is non-negotiable. The existing local admin password, MFA,
magic-link, refresh-token, and invitation machinery remains the break-glass path
when the RV appliance has no internet.

## 2. Resolved architecture

### 2.1 Public origins and endpoints

- CoachIQ public origin: `https://iq.holtel.io`.
- PocketID issuer: `https://id.holthome.net`.
- MCP resource path: `/api/mcp`.
- PocketID redirect URI: `https://iq.holtel.io/api/v1/auth/oidc/callback`.

Add explicit settings:

- `COACHIQ_SERVER__PUBLIC_ORIGIN`
- `COACHIQ_MCP__PATH`

Do not overload auth `base_url`; that setting exists for local magic-link URL
generation. When OIDC or MCP AS is enabled, startup validates that
`PUBLIC_ORIGIN` is an absolute origin with no path or trailing slash and that
`MCP__PATH` is a non-root absolute path with no trailing slash.

### 2.2 PocketID discovery values

The host-provided live discovery document for `https://id.holthome.net` is the
ground truth:

- Authorization endpoint: `https://id.holthome.net/authorize`
- Token endpoint: `https://id.holthome.net/api/oidc/token`
- Userinfo endpoint: `https://id.holthome.net/api/oidc/userinfo`
- JWKS endpoint: `https://id.holthome.net/.well-known/jwks.json`
- End-session endpoint: `https://id.holthome.net/api/oidc/end-session`
- Introspection endpoint: `https://id.holthome.net/api/oidc/introspect`
- PAR endpoint: `https://id.holthome.net/api/oidc/par`

PocketID supports `code` response type, PKCE `plain` and `S256` (CoachIQ must
use `S256`), RS256 ID tokens, confidential clients via `client_secret_basic` or
`client_secret_post`, and RFC 9207 authorization response issuer validation.
Request `openid profile email groups`. Do not request `offline_access`; PocketID
advertises `refresh_token` grant support, but CoachIQ issues its own local
session after validating the ID token.

### 2.3 Auth model

PocketID is an additive login capability, not a fourth exclusive `AuthMode`.
`AuthMode` remains `none`, `single`, or `multi` and describes local auth/user
population. New status/config fields describe OIDC capability, such as
`oidc_enabled` and provider metadata.

Both local auth and OIDC callbacks issue the existing CoachIQ local JWT session
shape. Existing `/api/auth/*` local endpoints remain available for the offline
path until a later approved migration moves the local auth surface to `/api/v1`.

### 2.4 Provider binding

PocketID `sub` is the stable federated key. Email, preferred username, display
name, and groups are mutable attributes refreshed on every OIDC login.

Phase 1 adds:

- A PocketID/OIDC provider value in the auth provider vocabulary.
- A unique `(provider, provider_user_id)` constraint.
- Repository helpers for provider lookup and JIT upsert/linking.
- Tests for first login, repeat login, email mutation, and duplicate provider
  binding rejection.

### 2.5 Group-gated role mapping

OIDC login is fail-closed. A PocketID user must belong to at least one mapped
group to log in. The group-role map is configurable, for example:

```json
{
  "CoachIQ Admins": "admin",
  "CoachIQ Operators": "user",
  "CoachIQ Viewers": "readonly"
}
```

The union of mapped groups is the login allowlist. If multiple mapped groups
match, the highest privilege wins: `admin` > `user` > `readonly`. No admin,
control, or readonly access is inferred from email or an unmapped group.

The canonical mapped roles are `admin`, `user`, and `readonly`. Phase 1 must
reconcile the current service-level `operator` reference before exposing OIDC
roles; OIDC should not mint `operator` as a separate role.

### 2.6 MCP AS contract posture

CoachIQ declares:

- Contract: `pocketid-mcp-as` v1.1.0.
- Profile: `opaque-no-refresh`.
- Scope posture: `mcp-only`.
- Token prefix: `ciqpat_`.
- TTL: 90 days.

Conformance command:

```bash
conformance/check.sh https://iq.holtel.io opaque-no-refresh mcp-only --mcp-path /api/mcp
```

The contract conformance script validates discovery metadata, both protected
resource metadata variants, byte-match, token-profile `jwks_uri` rules, and DCR.
It does not drive the interactive PocketID login or prove the minted-token scope
posture; CoachIQ integration tests must cover those.

## 3. Phase 1 - PocketID OIDC RP login

Phase 1 adds human OIDC login and removes dead generic OAuth scaffolding.

### Backend scope

- Add OIDC settings under `AuthenticationSettings` for PocketID issuer,
  client ID/secret, requested scopes, callback path, and group-role mapping.
- Add public-origin and MCP-path settings in the appropriate settings sections.
- Keep `AuthMode` unchanged; add additive OIDC capability/status fields.
- Add `/api/v1/auth/oidc/login` and `/api/v1/auth/oidc/callback`.
- Generate `state`, nonce, and PKCE verifier/challenge for the PocketID leg.
- Exchange the PocketID code at the live token endpoint.
- Validate the auth response `iss`, ID token signature through JWKS, issuer,
  audience, expiration, nonce, and required claims.
- JIT-upsert the local user through provider binding keyed on `(pocketid, sub)`.
- Apply group-role mapping; reject users with no mapped group.
- Issue the existing local JWT/refresh session after successful OIDC login.
- Optionally route logout through PocketID `end_session_endpoint` after local
  logout succeeds.

### Provider binding and schema scope

- Add the PocketID provider value.
- Add repository methods:
  - `get_user_by_auth_provider(provider, provider_user_id)`
  - `upsert_federated_user(...)`
  - `link_auth_provider(...)`
- Add an Alembic migration for the provider uniqueness guarantee and any new
  mutable provider/user fields required by implementation.

### Scaffold removal checklist

Generate the final target list with `rg` at implementation time. Known targets:

- `AuthenticationSettings.enable_oauth`
- `oauth_github_*`, `oauth_google_*`, `oauth_microsoft_*`
- `SecurityConfigValidator.OAUTH_PROVIDER_FIELDS`
- GitHub/Google/Microsoft auth-provider enum values
- `AuthStatus.oauth_enabled`
- Frontend auth types/status handling and generated OpenAPI types
- Any UI or settings text that says generic OAuth
- `.env.example` and configuration docs

Replace the old surface with PocketID/OIDC-specific status and config fields.

### Middleware, CSRF, rate limits, and audit

- Add the OIDC login and callback paths to auth-public endpoint lists.
- Exempt protocol endpoints from CSRF where clients cannot present CoachIQ's
  CSRF token. The OIDC callback relies on `state`, nonce, and PKCE validation.
- Rate-limit and audit OIDC login/callback failures.
- Keep local login/MFA/magic-link endpoints working.

### Frontend scope

- Show PocketID sign-in as an additional option when `oidc_enabled` is true.
- Preserve username/password and magic-link UI where their local modes are
  enabled.
- Update auth status types to include OIDC capability fields.
- Handle callback completion by storing the same local token shape already used
  by local login.
- Regenerate OpenAPI types if response models change.

### Phase 1 tests and quality

- Unit tests for ID-token validation, nonce/state failure, PKCE verifier use,
  JWKS cache behavior, group-role mapping, provider lookup/upsert, and local JWT
  issuance after OIDC.
- API tests for login redirect and callback success/failure cases.
- Frontend tests for local plus PocketID sign-in choices.
- Touched files clean against the repo quality gate; `pyright backend` at or
  below baseline; relevant auth/security pytest markers pass; OpenAPI and
  frontend generated types updated when schemas change.

## 4. Phase 2 - MCP OAuth 2.1 Authorization Server

Phase 2 implements the MCP AS contract and the protected MCP resource boundary.

### Discovery and protected resource metadata

Serve:

- `/.well-known/oauth-authorization-server`
- `/.well-known/oauth-protected-resource`
- `/.well-known/oauth-protected-resource/api/mcp`

Metadata values derive from `COACHIQ_SERVER__PUBLIC_ORIGIN` and
`COACHIQ_MCP__PATH`. The root PRM advertises resource `https://iq.holtel.io`.
The path-suffixed PRM advertises resource `https://iq.holtel.io/api/mcp`.

Opaque profile metadata must omit `jwks_uri` and list only
`authorization_code` in `grant_types_supported`.

### Authorization flow

- `/oauth/register`: DCR with allowlist-filtered redirect URIs, rate-limited at
  10/hour/source IP, hashed client secrets, and `client_secret_expires_at: 0`.
- `/oauth/authorize`: validate client, redirect URI, response type, scope, and
  client PKCE challenge; create AS transaction state; redirect to PocketID using
  a separate AS-to-PocketID PKCE verifier.
- `/oauth/callback`: consume AS transaction state, exchange the PocketID code,
  validate ID token and nonce, resolve the local user through Phase 1 provider
  binding, issue a single-use authorization code bound to client, redirect URI,
  user, and client PKCE challenge.
- `/oauth/token`: accept `client_secret_basic`, `client_secret_post`, and public
  clients as required by the contract; consume auth code once; verify client,
  redirect URI, and PKCE; mint opaque `ciqpat_` token.

### Token storage and MCP-only enforcement

- Store DCR client secrets hashed, compared constant-time.
- Store access-token handles hashed with SHA-256, never plaintext.
- Track expiry and revocation.
- Accept MCP OAuth tokens only on the configured MCP resource path.
- Reject MCP OAuth tokens on broader REST API routes.
- Return `401 WWW-Authenticate: Bearer` with
  `resource_metadata="https://iq.holtel.io/.well-known/oauth-protected-resource/api/mcp"`
  from the MCP resource when no valid token is present.

### Middleware, CSRF, rate limits, and audit

- Add AS discovery, DCR, authorize, callback, and token paths to auth-public
  endpoint lists.
- CSRF-exempt OAuth protocol endpoints that non-browser MCP clients call.
- Rate-limit DCR, token, and authorization initiation.
- Audit DCR, token issuance, invalid client, invalid grant, and token revocation
  events without logging secrets or token values.

### Phase 2 tests and quality

- Unit tests for metadata field names, PRM byte-match, DCR allowlist filtering,
  PKCE verification, single-use auth codes, hashed secret comparison, token hash
  lookup, revocation, expiry, and `mcp-only` enforcement.
- Integration tests for the two-leg federation up to the PocketID callback seam
  using mocked PocketID responses.
- Live conformance check:

```bash
conformance/check.sh https://iq.holtel.io opaque-no-refresh mcp-only --mcp-path /api/mcp
```

- Touched files clean against the repo quality gate; `pyright backend` at or
  below baseline; relevant auth/security pytest markers pass; OpenAPI updated
  for any documented non-contract API response shapes.

## 5. Out of scope for HOF-046 graduation

- Implementing OIDC or MCP AS code.
- Creating the MCP tool surface itself. The AS protects `/api/mcp`; the actual
  tools are tied to the Knowledge & Maintenance MCP work.
- Replacing all legacy `/api/auth/*` local auth endpoints with `/api/v1` local
  endpoints.
- Adding a general personal-access-token system for non-MCP REST API use.

## 6. Success criteria for phase HOFs

Per-phase implementation handoffs must cite `scripts/ci-quality-gate.sh` and
measure success against the real gate:

- Touched Python/TypeScript files are lint-clean.
- `pyright backend` is at or below the current baseline and ratchets down if the
  phase reduces errors.
- ESLint is diff-clean on touched frontend lines.
- Relevant auth/security pytest markers pass.
- Frontend tests pass for touched auth UI.
- OpenAPI is re-exported and frontend types regenerated when schemas change.
- Alembic migrations are included when models change.
- The `pocketid-mcp-as` conformance check passes for Phase 2.
