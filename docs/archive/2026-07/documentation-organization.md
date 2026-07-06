# Documentation Organization Guide

The rvc2api documentation is organized into two main sections: **User Guide** and **Developer Guide**. This structure helps different audiences find the information most relevant to their needs.

```mermaid
graph TD
    Root[rvc2api Documentation] --> User[User Guide]
    Root --> Dev[Developer Guide]
    Root --> Updates[Project Updates]
    Root --> Specs[Specifications]

    User --> UserGS[Getting Started]
    User --> UserArch[System Architecture]
    User --> UserAPI[API Reference]
    User --> UserRVC[RV-C Integration]
    User --> UserDeploy[Deployment]

    Dev --> DevArch[Architecture Details]
    Dev --> DevGuides[Development Guides]
    Dev --> DevQA[Quality Assurance]
    Dev --> DevBuild[Build System]
    Dev --> DevContrib[Contributing]

    classDef user fill:#C8E6C9,stroke:#4CAF50
    classDef dev fill:#BBDEFB,stroke:#2196F3
    classDef meta fill:#FFECB3,stroke:#FFC107

    class User,UserGS,UserArch,UserAPI,UserRVC,UserDeploy user
    class Dev,DevArch,DevGuides,DevQA,DevBuild,DevContrib dev
    class Updates,Specs,Root meta
```

## User Guide

The **User Guide** is designed for users who want to deploy, configure, and use rvc2api. It focuses on:

- Getting started with the project
- High-level architecture overview
- API usage and integration
- RV-C protocol integration
- Deployment options

This section answers questions like:

- "How do I set up rvc2api?"
- "What APIs are available?"
- "How do I deploy this to my system?"
- "How does this integrate with my RV's systems?"

## Developer Guide

The **Developer Guide** is for contributors and developers working on extending or modifying rvc2api. It includes:

- Detailed architecture explanations
- Development workflows and practices
- Code quality standards and tools
- Build system details
- Contribution guidelines

This section answers questions like:

- "How is the code structured?"
- "What development tools should I use?"
- "How do I ensure my code meets project standards?"
- "What's the process for submitting changes?"

## Project Updates and Specifications

Additionally, the documentation includes:

- **Project Updates**: Information about recent changes to the project
- **Specifications**: Detailed design specifications for major features

## Target Audience

When adding new documentation, consider your target audience:

| If documenting...     | Add to...       | Focus on...                                 |
| --------------------- | --------------- | ------------------------------------------- |
| API usages            | User Guide      | Clear examples and use cases                |
| Deployment options    | User Guide      | Step-by-step instructions                   |
| Code architecture     | Developer Guide | Design patterns and code organization       |
| Development workflows | Developer Guide | Tools and processes                         |
| Major features        | Specifications  | Design decisions and implementation details |

## Style Guidelines

- **User Guide**: Focus on clarity, examples, and step-by-step instructions
- **Developer Guide**: Include technical details, architecture decisions, and code examples
- **All Documentation**: Use visual diagrams (with Mermaid) to illustrate complex concepts
