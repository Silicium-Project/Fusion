# Network schema

This document provides a high-level schema of the Silicium Network stack and its main execution flows.

## Global architecture (Mermaid)

```mermaid
flowchart TD
    %% Clients and orchestration
    Client[Client / CLI] -->|job, workload| Emitter[Silicium CLI]

    %% Compute pipeline
    Emitter --> Splitter[splitter]
    Splitter -->|summary.json + fragments| Executor[executor]
    Executor --> Worker[worker]
    Worker --> Results[Results / proofs]

    %% Viewer
    Splitter --> Viewer[viewer (Qt)]
    Worker --> Viewer

    %% Catalog
    Catalog[workloads catalog] --> Emitter

    %% Infra / network stack
    Emitter --> Compose[docker compose]
    Compose --> Solana[Silicium node (Solana)]
    Compose --> Proxy[Caddy TLS proxy]
    Compose --> WG[WireGuard secure stack]

    %% RPC exposure
    Proxy --> Site
    MCP --> RPC[Authenticated control endpoint]

    %% Notes
    Results --> RPC
```

## MCP bridge extension

See `docs/mcp-connector-spec.md` for the MCP connector architecture, contracts, and rollout plan.

## P2P direct transport extension

See `docs/p2p-direct-transport-contract.md` for the target control-plane and
data-plane contract for NAT traversal, direct peer sessions, relay fallback, and
legacy HTTP compatibility.

## Execution flow (compute)

```mermaid
sequenceDiagram
    participant C as Client / CLI
    participant N as network scheduler
    participant W as compute/verify node
    participant R as Results

    C->>N: workload manifest + inputs
    N->>W: signed task envelope
    W-->>N: result + receipt
    N->>W: verification task
    W-->>R: accepted result / attestation
```

## Execution flow (network)

```mermaid
sequenceDiagram
    participant C as Client
    participant D as Docker Compose
    participant N as Network node
    participant P as Reverse proxy
    participant M as MCP/RPC control plane

    C->>D: start localnet/devnet/testnet/mainnet
    D->>N: start application and ledger services
    D->>P: start TLS proxy
    P-->>C: HTTPS RPC
    M-->>N: authenticated task/control events
```
