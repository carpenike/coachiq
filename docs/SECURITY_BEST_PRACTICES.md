# Security Best Practices for CoachIQ RV-C Control System

## Overview

This document outlines security best practices for the CoachIQ RV-C control system. These practices protect the API surface from unauthorized access and keep CoachIQ a polite citizen on the shared CAN bus.

## Threat model (read first)

CoachIQ is a soft control surface that talks to a **Firefly MIRA** multiplex
panel over RV-C / J1939. Firefly owns the physical-safety case (brake,
slides, leveling, etc.) and will refuse or fail-safe any command it
considers unsafe. CoachIQ cannot bypass it.

That shifts what "security" means here:

| Realistic threat | Mitigation |
|---|---|
| Unauth'd API access → attacker controls lights/HVAC/etc via our endpoints | JWT auth + CSRF + role-based authorization on every state-changing route |
| Credential compromise → same as above | Short token TTLs, refresh rotation, MFA for admin |
| Bus flooding from a buggy loop or malicious request | Outbound CAN-message rate limiting (token-bucket), backpressure on websocket / dispatcher loops |
| Malformed RV-C / J1939 frames confusing Firefly | Validate before encoding (Pydantic models, `input_validation.py`), encode via the message-factory layer, never raw-write user payloads |
| Web XSS / template injection | Jinja sandbox + autoescape; “safe notification manager” uses sandboxed env |
| Persistent log / audit tampering | Server-side audit log, no client-controlled identifiers in audit fields |

Not in CoachIQ's threat model:

- "Attacker releases the brake" — Firefly enforces brake interlocks; we cannot bypass them by sending a CAN frame.
- "Attacker overrides physical safety interlocks" — same; the interlocks live on Firefly, not in CoachIQ.
- "Failure of CoachIQ kills the user" — the OEM controller fails safe with or without us.

## Architecture Overview

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Internet  │───▶│    Caddy    │───▶│   FastAPI   │
│             │    │ (Edge Layer)│    │(App Layer)  │
└─────────────┘    └─────────────┘    └─────────────┘
                         │                    │
                   SSL Termination      Application Logic
                   IP Rate Limiting     User Rate Limiting
                   CORS Headers         CSRF Protection
                   Security Headers     Authentication
```

## 1. Authentication & Authorization

### JWT Token Security
- **Secret Key**: Use a cryptographically secure random key of at least 256 bits
- **Token Expiry**: Set appropriate expiration times (15-30 minutes for access tokens)
- **HttpOnly Cookies**: Store tokens in HttpOnly cookies to prevent XSS attacks
- **Secure Flag**: Always set the Secure flag for production (HTTPS only)

### Role-Based Access Control (RBAC)
```python
from backend.core.auth_decorators import require_role, require_admin

@router.post("/dangerous-operation")
@require_admin
async def dangerous_operation(current_user: Annotated[User, Depends(get_current_user)]):
    """Only admins can perform this operation."""
    pass

@router.post("/control-entity")
@require_role("operator", "admin")
async def control_entity(current_user: Annotated[User, Depends(get_current_user)]):
    """Operators and admins can control entities."""
    pass
```

### Multi-Factor Authentication
- Enable MFA for admin accounts
- Use TOTP (Time-based One-Time Password) for second factor
- Provide backup codes for account recovery

## 2. Input Validation & Sanitization

### Always Validate Inputs
```python
from backend.core.input_validation import (
    validate_entity_id,
    validate_can_id,
    validate_pin,
    sanitize_string
)

# Validate entity IDs
entity_id = validate_entity_id(request.entity_id)

# Validate CAN IDs
can_id = validate_can_id(request.can_id)

# Validate safety PINs
pin = validate_pin(request.pin)

# Sanitize user input
description = sanitize_string(request.description, max_length=200)
```

### Pydantic Models for Complex Validation
```python
from backend.core.input_validation import SafetyOperationRequest

@router.post("/safety-operation")
async def perform_safety_operation(
    request: SafetyOperationRequest,  # Automatically validated
    current_user: Annotated[User, Depends(get_current_user)]
):
    pass
```

## 3. CSRF Protection

### Double Submit Cookie Pattern
- Enabled automatically for production deployments
- Token rotation on authentication
- Exemptions only for authentication endpoints

### Frontend Integration
```javascript
// Get CSRF token from cookie
const csrfToken = getCookie('_csrf');

// Include in API requests
fetch('/api/control', {
    method: 'POST',
    headers: {
        'X-CSRF-Token': csrfToken,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
});
```

## 4. Rate Limiting

### Hybrid Architecture
- **Caddy (Edge)**: IP-based rate limiting for DDoS protection
- **FastAPI (App)**: User-aware rate limiting for API abuse prevention

### Configuration
```python
# Per-user limits
@router.get("/api/data")
@limiter.limit("100/minute")
async def get_data(request: Request):
    pass

# Stricter limits for sensitive operations
@router.post("/api/control")
@limiter.limit("10/minute")
async def control_entity(request: Request):
    pass
```

## 5. Security Headers

### Automatic Security Headers
The following headers are automatically added in production:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`
- `Content-Security-Policy: default-src 'self'`

### HSTS (via Caddy)
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

## 6. CAN Bus Security

### Message Validation
```python
# Always validate CAN messages before transmission
from backend.integrations.can.message_injector import CANMessageInjector, SafetyLevel

injector = CANMessageInjector(can_service)
result = await injector.inject_message(
    can_id=0x123,
    data=[0x01, 0x02],
    safety_level=SafetyLevel.CRITICAL,
    pin="1234"  # Required for critical operations
)
```

### Entity Control Security
- Validate entity ownership before allowing control
- Implement command rate limiting per entity
- Log all control operations for audit trail

## 7. Database Security

### Connection Security
- Use SSL/TLS for database connections
- Implement connection pooling with secure defaults
- Regular credential rotation

### Query Security
- Always use parameterized queries (SQLAlchemy handles this)
- Validate all user inputs before database operations
- Implement row-level security where appropriate

## 8. API Security

### API Key Management
- Use secure random generation for API keys
- Implement key rotation policies
- Scope keys to specific permissions

### Endpoint Security
```python
# Secure sensitive endpoints
@router.get("/api/admin/users")
@require_admin
@limiter.limit("10/minute")
async def list_users(
    current_user: Annotated[User, Depends(get_current_user)],
    _: Annotated[None, Depends(verify_api_key)]  # Double authentication
):
    pass
```

## 9. Logging & Monitoring

### Security Event Logging
```python
from backend.services.security.security_audit_service import SecurityAuditService

# Log security events
await security_audit.log_event(
    event_type="failed_login",
    user_id=username,
    ip_address=request.client.host,
    details={"reason": "invalid_password"}
)
```

### Monitor for Anomalies
- Track failed authentication attempts
- Monitor unusual API usage patterns
- Alert on security configuration changes

## 10. Emergency Response

### Emergency Stop Implementation
```python
from backend.core.safety_registry import SafetyServiceRegistry

# Emergency stop affects all safety-critical services
async def emergency_stop():
    safety_registry = SafetyServiceRegistry.get_instance()
    await safety_registry.execute_emergency_stop()
```

### Incident Response Plan
1. **Detection**: Monitor security logs and alerts
2. **Containment**: Isolate affected systems
3. **Investigation**: Analyze logs and audit trails
4. **Recovery**: Restore from secure backups
5. **Post-Mortem**: Document and improve

## 11. Development Security

### Secure Development Practices
- Never commit secrets to version control
- Use environment variables for sensitive configuration
- Regular dependency updates and security scanning

### Pre-commit Security Checks
```bash
# Run security checks before committing
poetry run bandit -r backend
poetry run safety check
pre-commit run --all-files
```

## 12. Deployment Security

### Production Hardening Checklist
- [ ] SSL/TLS configured (via Caddy)
- [ ] Debug mode disabled
- [ ] Strong secret keys generated
- [ ] Database credentials secured
- [ ] Rate limiting configured
- [ ] CORS properly configured
- [ ] Security headers enabled
- [ ] Logging configured
- [ ] Monitoring enabled
- [ ] Backup strategy in place

### Configuration Validation
```python
# Automatic security validation on startup
from backend.core.security_config_validator import validate_security_config

if not validate_security_config(settings):
    logger.error("Security configuration validation failed!")
    sys.exit(1)
```

## Quick Reference

### Essential Security Decorators
```python
@require_authenticated  # User must be logged in
@require_role("role")   # User must have specific role
@require_admin          # User must be admin
@require_permission("perm")  # User must have permission
```

### Essential Validation Functions
```python
validate_email(email)           # Email validation
validate_username(username)     # Username validation
validate_entity_id(entity_id)   # Entity ID validation
validate_can_id(can_id)        # CAN ID validation
validate_pin(pin)              # PIN validation
validate_ip_address(ip)        # IP address validation
validate_url(url)              # URL validation
sanitize_string(text)          # String sanitization
```

### Security Testing Commands
```bash
# Run all security tests
poetry run pytest tests/test_security_validation.py -v

# Check for security issues
poetry run bandit -r backend -ll

# Validate security configuration
poetry run python -c "from backend.core.security_config_validator import validate_security_config; from backend.core.config import get_settings; validate_security_config(get_settings())"
```

## Conclusion

Security is not a one-time implementation but an ongoing process. Regular security audits, updates, and monitoring are essential for maintaining a secure RV-C control system. Always follow the principle of least privilege and defense in depth.

For questions or security concerns, contact the security team immediately.
