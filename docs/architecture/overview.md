# Project Overview

The CoachIQ project provides a modern API and WebSocket service for RV-C (Recreational Vehicle Controller Area Network) systems, allowing you to monitor and control various devices in your RV.

## System Architecture

The system consists of several major components with clear separation of concerns:

```mermaid
graph TD
    User[User] --> WebUI[Web UI]
    User --> MobileApp[Mobile Apps]

    subgraph "Frontend Layer"
        WebUI --> REST[REST API Client]
        WebUI --> WS[WebSocket Client]
        MobileApp --> REST
        MobileApp --> WS
    end

    subgraph "API Layer"
        REST --> FastAPI[FastAPI Server]
        WS --> WSServer[WebSocket Server]
        FastAPI --> AppState[Application State]
        WSServer --> AppState
    end

    subgraph "Business Logic"
        AppState --> EntityManager[Entity Manager]
        AppState --> HistoryManager[History Manager]
        EntityManager --> Decoder[RV-C Decoder]
        HistoryManager --> Storage[State Storage]
    end

    subgraph "Device Layer"
        Decoder --> CanManager[CAN Manager]
        CanManager --> CanInterface[CAN Bus Interface]
        CanInterface --> RVCBus[RV-C CAN Bus]
    end

    classDef user fill:#f5f5f5,stroke:#bdbdbd,color:#212121;
    classDef frontend fill:#bbdefb,stroke:#1976d2,color:#212121;
    classDef api fill:#c8e6c9,stroke:#388e3c,color:#212121;
    classDef logic fill:#fff9c4,stroke:#fbc02d,color:#212121;
    classDef device fill:#ffccbc,stroke:#e64a19,color:#212121;

    class User user;
    class WebUI,MobileApp,REST,WS frontend;
    class FastAPI,WSServer,AppState api;
    class EntityManager,HistoryManager,Decoder,Storage logic;
    class CanManager,CanInterface,RVCBus device;
```

### Backend Components

The backend is built with Python and FastAPI:

- **FastAPI Application**: Provides RESTful API and WebSocket endpoints
- **RV-C Decoder**: Translates CAN messages to/from human-readable formats
- **State Management**: Maintains entity states and histories
- **WebSocket Server**: Provides real-time updates to clients

### Frontend Components

The frontend is built with React, TypeScript, and Vite:

- **React Application**: Single-page application with modern UI
- **TypeScript**: Provides type safety and better developer experience
- **API Client**: Communicates with the backend API
- **WebSocket Client**: Receives real-time updates

## Directory Structure

The project follows a monorepo structure:

```text
coachiq/
├── backend/              # Python backend application
│   ├── api/              # FastAPI routers and endpoints
│   ├── core/             # Core configuration and utilities
│   ├── services/         # Business logic services
│   ├── integrations/     # External integrations (CAN, etc.)
│   ├── websocket/        # WebSocket handlers
│   └── models/           # Data models and schemas
├── src/                  # Shared components
│   ├── common/           # Shared models and utilities
│   └── rvc_decoder/      # RV-C protocol decoder
├── frontend/               # React frontend
│   ├── src/              # Frontend source code
│   └── docs/             # Frontend-specific documentation
├── docs/                 # Project documentation
└── scripts/              # Utility scripts
```

## Key Features

- **Entity Management**: Monitor and control RV entities like lights, tanks, thermostats
- **Real-time Updates**: WebSocket for instant updates on entity state changes
- **Unified API**: Consistent endpoint structure for all entity types
- **Type Safety**: Strong typing in both backend and frontend
- **Interactive Documentation**: Auto-generated API docs via OpenAPI/Swagger

## Development and Deployment

### Development

Development workflows are streamlined with:

- **Poetry**: Python dependency management
- **npm**: JavaScript dependency management
- **VS Code Tasks**: Common tasks for building, testing, and running
- **Pre-commit Hooks**: Code quality checks

### Deployment

The system can be deployed in various ways:

- **Docker**: Containerized deployment
- **NixOS**: Native integration with NixOS
- **Direct Installation**: On compatible Linux systems

## API Design Decision

All light-related API operations are consolidated under `/api/entities` endpoints (e.g., `/api/entities?device_type=light`). The legacy `/api/lights` endpoint is not used. This ensures a unified, type-safe, and extensible API surface for all entity types.

### Entity Control Command Structure

When controlling entities via the `/api/entities/{id}/control` endpoint, the request body must use the standardized command format:

```json
// Turn light on
{ "command": "set", "state": "on" }

// Set light brightness
{ "command": "set", "state": "on", "brightness": 75 }

// Toggle light state
{ "command": "toggle" }

// Adjust brightness
{ "command": "brightness_up" }
{ "command": "brightness_down" }
```
