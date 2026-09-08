# Frozen Network layout

```text
Network/
├── catalog/                  # workload manifests, schemas, fixtures, golden data
├── ci/                       # active checks, Docker E2E, P2P smoke
├── docs/                     # contracts, security, stability, testbed docs
├── i18n/                     # CLI and shell translations
├── infra/                    # local Solana/node/proxy and optional world testbed
├── networked/                # Rust node, P2P, compute daemon, reputation bridge
├── proto/                    # RPC contracts
├── silicium                  # canonical developer/runtime CLI
├── silicium-cli              # portable CLI wrapper
├── silicium-layer-dashboard/ # Vite network/Solana dashboard
├── solana-layer/             # Anchor program and SDK
├── tests/                    # Python/runtime/integration tests
├── tools/                    # node, RPC, telemetry, update and E2E helpers
└── workloads/raytracer/      # active workload and native Rust implementation
```

The following are not active paths and must remain absent: `demo/`,
`splitter/`, `executor/`, `worker/`, `viewer/`, assembler fixtures, the PE
fixture corpus, C++/DynamoRIO/GUI images, and generated worker/executor
coverage. Their history remains available through Git.
