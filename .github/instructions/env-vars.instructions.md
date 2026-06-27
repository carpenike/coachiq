---
applyTo: "**/*.py"
---

# Environment Variables

## MCP Tools for Configuration

### @context7 Use Cases

- Find configuration patterns: `@context7 environment variable loading`
- See settings schemas: `@context7 Pydantic settings model`
- Check YAML structures: `@context7 coach_mapping.default.yml structure`
- Review config access: `@context7 get_canbus_config usage`

### @perplexity Use Cases

- Research configuration best practices: `@perplexity Python environment variables best practices`
- Learn about Pydantic settings: `@perplexity Pydantic vs python-decouple for env vars`

## CANbus Config

- `CAN_CHANNELS`: e.g. `can0,can1`
- `CAN_BUSTYPE`: e.g. `socketcan`
- `CAN_BITRATE`: e.g. `500000`
- `RVC_SPEC_PATH`: Path to RV-C JSON spec
- `RVC_COACH_MAPPING_PATH`: Path to device mapping YAML

## Server Config

- `COACHIQ_TITLE`: Swagger UI title
- `COACHIQ_SERVER_DESCRIPTION`: Description for FastAPI docs
- `COACHIQ_ROOT_PATH`: Mount point if reverse-proxied
- `COACHIQ_USER_COACH_INFO_PATH`: Path to custom coach YAML

## Security Secrets

- In non-development environments, CSRF middleware must fail closed unless `COACHIQ_AUTH__SECRET_KEY` or a real `COACHIQ_SECURITY__SECRET_KEY` is configured. Never add hardcoded production fallbacks for signing secrets; development-only placeholders must stay explicitly labeled and rejected outside development.
- Production and staging settings must reject missing secrets, `development-only-secret-key-do-not-use-in-production`, and copied example placeholders such as `your-secret-key-change-in-production`. Prefer `COACHIQ_SECURITY__SECRET_KEY_FILE` and `COACHIQ_AUTH__SECRET_KEY_FILE` for deployments so secrets come from `/run/secrets` or systemd credentials rather than Nix config, the Nix store, or a checked-in env file.

## Misc

- `LOG_LEVEL`: Logging verbosity

## Usage Example

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # CAN Bus settings
    can_channels: str = "can0"
    can_bustype: str = "socketcan"
    can_bitrate: int = 500000

    # Server settings
    api_title: str = "RV-C API"
    server_description: str = "API for RV-C protocol"

    model_config = SettingsConfigDict(
        env_prefix="COACHIQ_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
```
