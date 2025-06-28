#!/usr/bin/env python3
"""Generate simple API documentation from OpenAPI spec."""

import json
import subprocess
from pathlib import Path


def generate_api_docs():
    """Generate API reference documentation from OpenAPI spec."""
    print("Generating API documentation...")

    # Ensure api directory exists
    api_dir = Path("docs/api")
    api_dir.mkdir(parents=True, exist_ok=True)

    # First, export the OpenAPI spec
    print("Exporting OpenAPI spec...")
    try:
        subprocess.run(["poetry", "run", "python", "scripts/export_openapi.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to export OpenAPI spec: {e}")
        print("Continuing with existing spec if available...")

    # Check if spec exists
    spec_path = api_dir / "openapi.json"
    if not spec_path.exists():
        print("Warning: OpenAPI spec not found at docs/api/openapi.json")
        print("Creating placeholder API documentation...")

        placeholder_content = """# API Reference

The API documentation will be automatically generated from the OpenAPI specification.

To generate the documentation:
1. Ensure the backend is running
2. Run: `poetry run python scripts/export_openapi.py`
3. Run: `poetry run python scripts/generate_simple_api_docs.py`

## Available Endpoints

The CoachIQ API provides RESTful endpoints for:
- Entity management (lights, HVAC, sensors)
- CAN bus monitoring
- System configuration
- WebSocket real-time updates

Base URL: `http://raspberrypi.local:8080`

See the OpenAPI specification for detailed endpoint documentation.
"""
        (api_dir / "reference.md").write_text(placeholder_content)
        print("✓ Created placeholder API documentation")
        return

    # Read the OpenAPI spec
    with spec_path.open() as f:
        spec = json.load(f)

    # Generate markdown documentation
    content = ["# API Reference\n\n"]
    content.append(f"**Version**: {spec.get('info', {}).get('version', 'Unknown')}\n\n")
    content.append(f"{spec.get('info', {}).get('description', '')}\n\n")
    content.append("**Base URL**: `http://raspberrypi.local:8080`\n\n")

    # Group endpoints by tag
    endpoints_by_tag = {}

    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                tags = details.get("tags", ["Other"])
                for tag in tags:
                    if tag not in endpoints_by_tag:
                        endpoints_by_tag[tag] = []
                    endpoints_by_tag[tag].append(
                        {
                            "path": path,
                            "method": method.upper(),
                            "summary": details.get("summary", ""),
                            "description": details.get("description", ""),
                            "parameters": details.get("parameters", []),
                            "requestBody": details.get("requestBody", {}),
                            "responses": details.get("responses", {}),
                        }
                    )

    # Generate documentation by tag
    for tag in sorted(endpoints_by_tag.keys()):
        content.append(f"## {tag}\n\n")

        for endpoint in endpoints_by_tag[tag]:
            # Endpoint header
            content.append(f"### {endpoint['method']} {endpoint['path']}\n\n")

            # Summary and description
            if endpoint["summary"]:
                content.append(f"**{endpoint['summary']}**\n\n")
            if endpoint["description"]:
                content.append(f"{endpoint['description']}\n\n")

            # Parameters
            if endpoint["parameters"]:
                content.append("**Parameters:**\n\n")
                for param in endpoint["parameters"]:
                    required = "required" if param.get("required", False) else "optional"
                    content.append(
                        f"- `{param['name']}` ({param.get('in', 'query')}, {required}): {param.get('description', 'No description')}\n"
                    )
                content.append("\n")

            # Request body
            if endpoint["requestBody"]:
                content.append("**Request Body:**\n\n")
                if "content" in endpoint["requestBody"]:
                    for content_type, schema_info in endpoint["requestBody"]["content"].items():
                        content.append(f"Content-Type: `{content_type}`\n\n")
                        # Add example if available
                        if "example" in schema_info:
                            content.append("Example:\n```json\n")
                            content.append(json.dumps(schema_info["example"], indent=2))
                            content.append("\n```\n\n")

            # Responses
            content.append("**Responses:**\n\n")
            for status_code, response in endpoint["responses"].items():
                desc = response.get("description", "No description")
                content.append(f"- `{status_code}`: {desc}\n")
            content.append("\n---\n\n")

    # Add WebSocket section
    content.append("""## WebSocket API

CoachIQ provides real-time updates via WebSocket connection.

**Endpoint**: `ws://raspberrypi.local:8080/ws`

### Connection
```javascript
const ws = new WebSocket('ws://raspberrypi.local:8080/ws');
```

### Message Types

**Entity Updates**
```json
{
  "type": "entity_update",
  "data": {
    "id": "light_1",
    "state": true,
    "brightness": 75
  }
}
```

**Status Messages**
```json
{
  "type": "status",
  "message": "Connected to CAN bus"
}
```

### Client Commands

**Subscribe to Updates**
```json
{
  "type": "subscribe",
  "entities": ["light_1", "hvac_1"]
}
```

**Control Entity**
```json
{
  "type": "control",
  "entity_id": "light_1",
  "command": {
    "state": false
  }
}
```
""")

    # Write the documentation
    output_path = api_dir / "reference.md"
    output_path.write_text("".join(content))

    print(f"✓ API documentation generated at {output_path}")


if __name__ == "__main__":
    generate_api_docs()
