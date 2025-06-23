# CoachIQ Project Overview

## Purpose
CoachIQ is an intelligent RV-C network management system with advanced analytics and control. It bridges RV-C networks with modern applications by providing a structured API and real-time data streaming.

## Key Capabilities
- Decodes RV-C messages and manages device states
- Allows sending commands to the RV-C bus
- Provides real-time WebSocket streaming
- Features AI-powered documentation search using FAISS
- Supports multiple protocols: RV-C, J1939, Firefly, Spartan K2

## Architecture
- **Backend**: FastAPI-based service-oriented architecture with ServiceRegistry
- **Frontend**: React SPA with Vite, TypeScript, TailwindCSS, and shadcn/ui
- **Configuration**: Pydantic-based settings with environment variables
- **CAN Integration**: Multiple CAN interface support with protocol decoding

## Version
- Project uses VERSION file as single source of truth
- Managed with release-please for automated releases based on conventional commits
