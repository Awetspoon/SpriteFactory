# Sprite Factory V3 Architecture

## Dependency Direction

- `presentation` depends on `application` contracts.
- `application` depends on `domain` and abstract ports.
- `infrastructure` implements application ports.
- `domain` depends on nothing else in the project.

Allowed direction:

`presentation -> application -> domain`

`infrastructure -> application contracts`

Forbidden:

- `domain -> application/presentation/infrastructure`
- `application -> presentation`
- Qt UI imports inside `domain`

## Module Responsibilities

### domain

- Immutable/core entities and value objects
- Validation and pure rules
- No side effects

### application

- Use-case orchestration
- State transition policies
- Port interfaces for persistence, ingest, export, processing

### infrastructure

- Filesystem/session/settings adapters
- Network and ingest adapters
- Adapter wrappers over current engine implementation where needed

### presentation

- Qt widgets and UI interaction logic
- View-model mappers
- Emits commands to application layer only

### app

- Startup wiring and dependency composition
- Runtime config and feature flags

## Initial Contracts To Define

- Session repository contract
- Workspace state service contract
- Preset apply use-case contract
- Export use-case contract
- Ingest use-case contract

## Migration Principle

Build adapters from v3 contracts to existing v2 logic first, then replace implementation internals gradually.

This keeps behavior stable while improving architecture.
