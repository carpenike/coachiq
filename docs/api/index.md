# API Documentation

Welcome to the CoachIQ API documentation. This documentation provides comprehensive information about the API endpoints, request/response formats, and data models.

## API Overview

The CoachIQ server provides a RESTful API for interacting with RV-C devices and systems. The primary surface is the Domain API v1 under `/api/v1/*`; legacy `/api/*` routers remain for surfaces that have not yet been migrated. The API is organized into the following categories:

- [Entity API](/api/entities): Endpoints for managing and controlling entities (devices like lights, temperature sensors, etc.) at `/api/v1/entities`
- [CAN Bus API](/api/can): Endpoints for interacting directly with the CAN bus
- [Configuration API](/api/config): Endpoints for retrieving and modifying system configuration at `/api/config`
- [Realtime API](/api/websocket): Server-Sent Events stream at `GET /api/events` for real-time state updates, plus diagnostic WebSocket endpoints for logs and CAN tools

All API requests require authentication (JWT bearer tokens issued via `/api/auth`, with optional MFA, magic-link, and PIN flows); only a small set of paths such as health checks, the OpenAPI docs, and the login endpoints themselves are excluded. See the [API Overview](/api/overview) for details.

## API Specification

The API is fully documented using the OpenAPI specification. You can:

- Browse the [OpenAPI Specification](/api/openapi) for details on how to use the API
- Access interactive API documentation at [http://localhost:8000/docs](http://localhost:8000/docs) when the server is running
- Use the raw OpenAPI schema to generate API clients for various programming languages

## Frontend Integration

The CoachIQ project includes a React frontend that consumes the API. For information about how the frontend integrates with the API, see the [Frontend API Integration](/api/frontend-integration) page.
