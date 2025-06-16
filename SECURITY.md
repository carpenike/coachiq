# Security Configuration Guide

## Security Philosophy

CoachIQ implements a **Defense in Depth** security strategy aligned with industry standards including ISO/SAE 21434 (Automotive Cybersecurity) and NIST SP 800-82 (Industrial Control Systems Security). Our security architecture is designed to be **secure by default** while providing flexibility for valid deployment patterns.

## Security Configuration Modes

CoachIQ supports two operational modes for TLS/HTTPS handling:

### 1. Internal TLS Mode (Default - Recommended)

In this mode, the CoachIQ application handles all TLS termination, HTTPS redirection, and security headers directly.

**Configuration:**

```bash
# Default - no configuration needed
# OR explicitly set:
COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL=false
```

**Characteristics:**

- ✅ **Secure by default** - No additional infrastructure required
- ✅ **Simple deployment** - Single application handles everything
- ✅ **Full HTTPS enforcement** - Automatic HTTP to HTTPS redirection
- ✅ **HSTS headers** - HTTP Strict Transport Security enabled
- ✅ **Defense in depth** - Multiple security layers

**Best for:** Single-server deployments, development environments, simple production setups.

### 2. External TLS Mode (Advanced - For Reverse Proxy Deployments)

In this mode, CoachIQ operates behind a trusted reverse proxy (like Nginx, Traefik, or AWS ALB) that handles TLS termination.

**Configuration:**

```bash
COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL=true
```

**⚠️ CRITICAL REQUIREMENTS:**
When enabling external TLS mode, you **MUST** ensure:

1. **Reverse Proxy Configuration:**

   - [ ] Reverse proxy terminates TLS (handles SSL certificates)
   - [ ] Reverse proxy redirects all HTTP traffic to HTTPS
   - [ ] Reverse proxy sends `Strict-Transport-Security` (HSTS) header
   - [ ] Reverse proxy forwards original protocol information via headers

2. **Application Configuration:**
   - [ ] CoachIQ launched with `--proxy-headers` flag (for Uvicorn)
   - [ ] Network path between proxy and application is secure
   - [ ] Application only accessible through the reverse proxy

**Best for:** Containerized deployments, load-balanced environments, enterprise infrastructure.

## Configuration Reference

### Environment Variables

| Variable                                        | Default       | Description                                                      |
| ----------------------------------------------- | ------------- | ---------------------------------------------------------------- |
| `COACHIQ_ENVIRONMENT`                           | `development` | Application environment (`development`, `production`, `testing`) |
| `COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL` | `false`       | Enable external TLS termination mode                             |

### Security Behavior Matrix

| Environment | TLS External | HTTPS Required | HTTPS Redirect | HSTS Headers |
| ----------- | ------------ | -------------- | -------------- | ------------ |
| Development | `false`      | ❌             | ❌             | ❌           |
| Development | `true`       | ❌             | ❌             | ❌           |
| Production  | `false`      | ✅             | ✅             | ✅           |
| Production  | `true`       | ✅             | ❌\*           | ❌\*         |

_\* Handled by reverse proxy_

## External TLS Mode - Operator Checklist

When using `COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL=true`, complete this checklist:

### Infrastructure Requirements

- [ ] **Reverse Proxy Deployed** - Nginx, Traefik, HAProxy, or cloud load balancer
- [ ] **TLS Certificates Installed** - Valid SSL certificates in the reverse proxy
- [ ] **HTTPS Redirection Configured** - All HTTP traffic redirected to HTTPS
- [ ] **Security Headers Configured** - Reverse proxy sends appropriate headers:

  ```
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
  X-Forwarded-Proto: https
  X-Forwarded-For: <client-ip>
  ```

### Application Requirements

- [ ] **Proxy Headers Enabled** - Application started with `--proxy-headers` flag
- [ ] **Network Security** - Application only accessible through reverse proxy
- [ ] **Health Check Validation** - Verify `request.url.scheme` reports `https` correctly

### Example Configurations

#### Nginx Configuration

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    location / {
        proxy_pass http://coachiq-app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Caddy Configuration

```caddyfile
your-domain.com {
    # Automatic HTTPS with Let's Encrypt
    reverse_proxy coachiq-app:8000 {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
    }

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: connect-src 'self' ws: wss:;"
    }
}
```

#### Docker Compose with Traefik

```yaml
version: "3.8"
services:
  coachiq:
    image: coachiq:latest
    command:
      [
        "uvicorn",
        "main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--proxy-headers",
      ]
    environment:
      - COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL=true
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.coachiq.rule=Host(`your-domain.com`)"
      - "traefik.http.routers.coachiq.tls=true"
      - "traefik.http.routers.coachiq.tls.certresolver=letsencrypt"
```

#### Docker Compose with Caddy

```yaml
version: "3.8"
services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - coachiq

  coachiq:
    image: coachiq:latest
    command:
      [
        "uvicorn",
        "main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--proxy-headers",
      ]
    environment:
      - COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL=true
    expose:
      - "8000"

volumes:
  caddy_data:
  caddy_config:
```

#### Application Startup

```bash
# Correct - with proxy headers
uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers

# Incorrect - missing proxy headers support
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Compliance and Standards Alignment

This security configuration approach aligns with:

### ISO/SAE 21434 (Automotive Cybersecurity)

- ✅ **Risk-based approach** - Security decisions based on deployment context
- ✅ **Defense in depth** - Multiple security validation layers
- ✅ **Explicit configuration** - Clear, auditable security settings
- ✅ **Lifecycle coverage** - Security from development through production

### NIST SP 800-82 (Industrial Control Systems)

- ✅ **System integrity** - Prevents unauthorized modifications
- ✅ **Access control** - Strict HTTPS enforcement in production
- ✅ **Explicit configuration** - Deliberate security decisions
- ✅ **Audit trail** - Security configuration logging

## Security Logging and Audit Trail

CoachIQ automatically logs security configuration decisions at startup:

### Internal TLS Mode

```json
{
  "level": "INFO",
  "event": "security_configuration",
  "tls_termination": "internal",
  "https_redirect": "enabled",
  "mode": "production",
  "message": "Application is self-enforcing HTTPS in production mode."
}
```

### External TLS Mode

```json
{
  "level": "WARNING",
  "event": "security_configuration",
  "tls_termination": "external",
  "https_redirect": "disabled",
  "proxy_headers_required": true,
  "message": "External TLS termination enabled. Operator is responsible for HTTPS redirection and HSTS."
}
```

## Security Validation

### Runtime Validation

- **HTTPS Enforcement**: Application validates `request.url.scheme` on every request
- **Proxy Header Validation**: When external TLS is enabled, validates proxy headers are working
- **Defense in Depth**: Multiple validation layers prevent security bypasses

### Testing Security Configuration

```bash
# Test HTTPS enforcement (should redirect or require HTTPS)
curl -v http://your-domain.com/api/auth/status

# Test proxy headers (should show 'https' scheme)
curl -H "X-Forwarded-Proto: https" http://internal-app:8000/api/auth/status

# Verify HSTS headers
curl -D - https://your-domain.com/api/auth/status | grep -i strict-transport
```

## Security Best Practices

1. **Always use HTTPS in production** - Never disable TLS validation in production environments
2. **Monitor security logs** - Watch for security configuration warnings in your logs
3. **Regular security reviews** - Periodically validate your proxy and TLS configuration
4. **Principle of least privilege** - Only enable external TLS mode when necessary
5. **Defense in depth** - Use multiple security layers (proxy + application validation)

## Support and Questions

For security-related questions or concerns:

1. Review this documentation thoroughly
2. Check application logs for security configuration messages
3. Validate your infrastructure meets the requirements checklist
4. Test your configuration using the provided validation commands

Remember: Security is a shared responsibility. When using external TLS mode, the operator assumes responsibility for proper reverse proxy configuration and TLS handling.
