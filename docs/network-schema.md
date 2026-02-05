# Network schema

This document provides a high-level schema of the Silicium Network stack and its main execution flows.

## Global architecture (Mermaid)

```mermaid
flowchart TD
    %% Clients and orchestration
    Client[Client / CLI] -->|job, workload| Orchestrator[Silicium CLI]

    %% Compute pipeline
    Orchestrator --> Splitter[splitter]
    Splitter -->|summary.json + fragments| Executor[executor]
    Executor --> Worker[worker]
    Worker --> Results[Results / proofs]

    %% Viewer
    Splitter --> Viewer[viewer (Qt)]
    Worker --> Viewer

    %% Catalog
    Catalog[workloads catalog] --> Orchestrator

    %% Infra / network stack
    Orchestrator --> Compose[docker compose]
    Compose --> Solana[Silicium node (Solana)]
    Compose --> Proxy[Caddy TLS proxy]
    Compose --> WG[WireGuard secure stack]

    %% RPC exposure
    Proxy --> RPC[RPC endpoint]
    WG --> RPC

    %% Notes
    Results --> RPC
```

## Execution flow (compute)

```mermaid
sequenceDiagram
    participant C as Client / CLI
    participant S as splitter
    participant E as executor
    participant W as worker
    participant R as Results

    C->>S: binary + config
    S-->>C: summary.json + fragments
    C->>E: run fragments (emu/native)
    E->>W: execution reports
    W-->>R: results / proofs
```

## Execution flow (network)

```mermaid
sequenceDiagram
    participant C as Client
    participant D as docker compose
    participant N as Silicium node
    participant P as Caddy proxy
    participant W as WireGuard

    C->>D: start localnet/devnet/testnet/mainnet
    D->>N: run validator/test-validator
    D->>P: start TLS proxy
    D->>W: start VPN stack
    P-->>C: HTTPS RPC
    W-->>C: Private RPC
```