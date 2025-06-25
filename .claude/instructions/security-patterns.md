# Security Patterns and Best Practices

## 🔒 Critical Security Requirements

This is a safety-critical RV-C vehicle control system. Security failures can result in physical harm. All security patterns MUST be followed without exception.

## Authentication & Authorization

### JWT Token Security
```python
# ✅ CORRECT: JWT secret from environment variable only
from backend.core.config import get_settings

settings = get_settings()
if not settings.authentication.secret_key:
    raise ValueError("JWT secret must be set via COACHIQ_AUTH__SECRET_KEY")

# ❌ WRONG: Never use fallback secrets
secret = settings.authentication.secret_key or "insecure-default"  # NEVER DO THIS
```

### Session Security
```python
# ✅ CORRECT: Session fingerprinting for hijacking protection
async def create_session(user_id: str, request: Request):
    # Calculate fingerprint from user agent and IP subnet
    fingerprint = calculate_session_fingerprint(request)

    session_data = {
        "user_id": user_id,
        "device_info": {
            "fingerprint": fingerprint,
            "user_agent": request.headers.get("User-Agent"),
            "ip_address": request.client.host
        }
    }

    # Validate fingerprint on each request
    if stored_fingerprint != current_fingerprint:
        await invalidate_session(session_id)
        raise SecurityException("Session fingerprint mismatch")
```

## Rate Limiting

### 🔄 SPLIT ARCHITECTURE (New Pattern)

**IMPORTANT**: Rate limiting now uses a split architecture for optimal performance and security:

#### Caddy Edge Layer (IP-based)
- **First line of defense** - processes at network edge before hitting Python
- **IP-based rate limiting** only - no application context required
- **Configured in**: `config/Caddyfile.example`
- **Protects against**: Basic DoS attacks, brute force by IP

```caddyfile
# Example Caddy rate limiting (IP-based)
rate_limit {
    zone auth {
        key {http.request.remote.host}
        window 1m
        events 5  # 5 auth attempts per minute per IP
    }
}
```

#### FastAPI Application Layer (User-aware)
- **Context-aware rate limiting** - understands users, sessions, safety contexts
- **Business logic dependent** - safety-critical operation limits
- **Configured via**: SecurityConfigService
- **Protects against**: User-specific abuse, safety-critical operation flooding

```python
# ✅ CORRECT: Use SecurityConfigService for user-aware rate limits
from backend.core.dependencies import get_security_config_service

async def get_rate_limit(
    endpoint: str,
    config_service: Annotated[Any, Depends(get_security_config_service)]
):
    # User-aware rate limits from centralized configuration
    limits = await config_service.get_rate_limit_for_endpoint(endpoint)
    return limits  # {"requests": 100, "window": 60}

# ❌ WRONG: Never hardcode rate limits
RATE_LIMIT = 100  # NEVER DO THIS
```

### Rate Limit Categories (Application Layer)
- **Authentication**: User/username-specific limits via SlowAPI
- **Safety Operations**: Per-user safety operation limits
- **Emergency Operations**: Per-user emergency operation limits
- **API General**: Authenticated user rate limits

### Architectural Guidelines
1. **Edge Layer (Caddy)**: Handle transport-level, IP-based limits
2. **Application Layer (FastAPI)**: Handle business-logic-aware limits
3. **Never duplicate**: Each layer handles what it does best
4. **Security-first**: Application layer rate limits are safety-critical

## Sensitive Data Protection

### Audit Log Filtering
```python
# ✅ CORRECT: Filter sensitive data before logging
from backend.core.sensitive_data_filter import SensitiveDataFilter

filter = SensitiveDataFilter()

@audit_event(category="user_action")
async def sensitive_operation(**kwargs):
    # Sensitive data is automatically filtered
    # Passwords, tokens, API keys are masked
    pass

# ❌ WRONG: Never log raw sensitive data
logger.info(f"Login attempt: {username}, {password}")  # NEVER DO THIS
```

### Value Detection Patterns
The SensitiveDataFilter now detects:
- JWT tokens (eyJ...)
- API keys (base64-like strings)
- Credit card numbers
- Email addresses (partially masked)
- IP addresses (last octet masked)
- Hex strings (potential keys/hashes)
- UUIDs

## Database Security

### Efficient Aggregation Queries
```python
# ✅ CORRECT: Use repository aggregation methods
summary = await auth_repository.get_auth_events_summary(
    user_id=user_id,
    since=since
)
# Returns counts only, not full records

# ❌ WRONG: Never fetch all records for counting
events = await auth_repository.get_auth_events_for_user(user_id)
count = len(events)  # NEVER DO THIS - potential DoS
```

## IP Security

### Threat Response
```python
# ✅ CORRECT: Proper IP blocking implementation
async def _execute_threat_response(
    self,
    analysis: AttemptAnalysis,
    summary: AttemptSummary,
    ip_address: str | None = None  # Must pass IP address
):
    if analysis.threat_level == "critical" and summary.unique_ips == 1 and ip_address:
        await self._audit_service.block_ip(
            ip_address,
            duration_minutes=60,
            reason="Critical security threat detected"
        )

# ❌ WRONG: Never try to extract IP from count
if len(summary.unique_ips) == 1:  # TypeError - unique_ips is an int!
    ip = list(summary.unique_ips)[0]  # CRASH
```

## Configuration Security

### Environment-Specific Validation
```python
# ✅ CORRECT: Validate security settings in production
@model_validator(mode='after')
def validate_secret_key(self) -> 'SecuritySettings':
    env = os.environ.get("COACHIQ_ENV", "development").lower()

    if env in ["production", "prod", "staging"] and not self.secret_key:
        raise ValueError(
            "Security secret key is required in production. "
            "Set COACHIQ_SECURITY__SECRET_KEY environment variable."
        )

    # Development-only default
    if not self.secret_key:
        self.secret_key = SecretStr("development-only-secret")
```

## Service Access Security

### Dependency Injection Only
```python
# ✅ CORRECT: Use dependency injection
async def secure_endpoint(
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
    security_config: Annotated[Any, Depends(get_security_config_service)]
):
    # Services are injected with proper lifecycle management
    pass

# ❌ WRONG: Never use service locator pattern
def bad_endpoint():
    registry = get_service_registry()  # Anti-pattern
    auth = registry.get_service("auth_manager")  # NEVER DO THIS
```

## Security Event Monitoring

### Comprehensive Audit Trail
```python
# ✅ CORRECT: Log all security-relevant events
await audit_service.log_security_event(
    event_type="failed_login",
    severity="warning",
    user_id=user_id,
    ip_address=ip_address,
    metadata={
        "attempt_count": attempts,
        "lockout_applied": lockout_active
    }
)

# Track patterns for threat detection
analysis = await attempt_tracker.analyze_patterns(summary)
if analysis.threat_level in ["high", "critical"]:
    await execute_threat_response(analysis, summary, ip_address)
```

## Content Security Policy

### Headers Configuration
```python
# ✅ CORRECT: Strict CSP without unsafe-eval
CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "  # unsafe-inline required for React
    "style-src 'self' 'unsafe-inline'; "
    # NO unsafe-eval - removed for security
)

# ❌ WRONG: Never use unsafe-eval
"script-src 'self' 'unsafe-inline' 'unsafe-eval'"  # NEVER DO THIS
```

## Security Checklist for Code Reviews

Before any commit or PR:

1. **Authentication**
   - [ ] No hardcoded secrets or fallback values
   - [ ] JWT secrets from environment variables only
   - [ ] Session fingerprinting implemented

2. **Rate Limiting**
   - [ ] Use centralized SecurityConfigService
   - [ ] No hardcoded rate limits
   - [ ] Appropriate limits for endpoint category

3. **Data Protection**
   - [ ] Sensitive data filtered in logs
   - [ ] No passwords/tokens in error messages
   - [ ] Aggregation queries instead of full fetches

4. **Input Validation**
   - [ ] All user inputs validated
   - [ ] SQL injection prevention
   - [ ] XSS protection in place

5. **Error Handling**
   - [ ] Generic error messages to users
   - [ ] Detailed errors only in secure logs
   - [ ] No stack traces exposed

## Security Testing Commands

```bash
# Run security audit
poetry run bandit -c pyproject.toml -r backend

# Check for dependency vulnerabilities
poetry run pip-audit

# Frontend security audit
cd frontend && npm run security:audit

# Run security-focused tests
poetry run pytest tests/security/ -v
```

## Incident Response

If a security issue is discovered:

1. **Immediate Actions**
   - Assess impact and severity
   - Apply temporary mitigation if possible
   - Document the issue thoroughly

2. **Fix Implementation**
   - Follow security patterns strictly
   - Add tests for the vulnerability
   - Update this documentation

3. **Post-Fix Validation**
   - Run all security tests
   - Perform code review with security focus
   - Update security monitoring rules

Remember: This is a safety-critical system. When in doubt, choose the more secure option.
