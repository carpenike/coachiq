# Testing Mermaid Diagrams

This file is for testing that mermaid diagrams render correctly with the updated YAML configuration.

## Sample Diagram

Here's a diagram showing the main components of our application:

```mermaid
graph TD
    A[FastAPI Backend] --> B[WebSocket Connection]
    A --> C[REST API]
    B --> D[RV-C Decoder]
    C --> D
    D --> E[CANbus Interface]

    classDef backend fill:#009688,stroke:#00796B,color:#FFFFFF;
    classDef api fill:#FF5722,stroke:#E64A19,color:#FFFFFF;
    classDef decoder fill:#3F51B5,stroke:#303F9F,color:#FFFFFF;
    classDef interface fill:#FFC107,stroke:#FFA000,color:#000000;

    class A backend;
    class B,C api;
    class D decoder;
    class E interface;
```

## Simple Flowchart

A simple process flowchart:

```mermaid
graph LR
    Start([Start]) --> Process[Process Data]
    Process --> Decision{Decision}
    Decision -->|Yes| End([End])
    Decision -->|No| Process

    style Start fill:#C8E6C9,stroke:#4CAF50
    style Process fill:#BBDEFB,stroke:#2196F3
    style Decision fill:#FFECB3,stroke:#FFC107
    style End fill:#FFCDD2,stroke:#F44336
```

## Sequence Diagram

A sample interaction sequence:

```mermaid
sequenceDiagram
    participant User
    participant API
    participant Database

    User->>API: Request data
    API->>Database: Query
    Database-->>API: Results
    API-->>User: Response

    Note over User,API: Authentication required
```

This should render as proper diagrams if the configuration is correct.
